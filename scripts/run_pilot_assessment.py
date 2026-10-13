import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from database.init import engine
from logs import logger
from populate.speaker_resolution_constants import (
    CHIEF_MINISTER_CUTOFF,
    COLONIAL_PARLIAMENT_FALLBACKS,
    NON_SPEAKERS,
    PRESIDING_OFFICERS,
    ROLE_ONLY_SPEAKERS,
)
from services.attendance import (
    SpeakerLookups,
    build_speaker_lookups,
    resolve_canonical_name,
)
from utils.names import (
    normalize_name,
    strip_title,
)

_SAMPLE_PATH = Path(__file__).parent.parent / "docs" / "speech-speaker" / "sample.json"
_COLONIAL_PARLIAMENT_NUMBER = 0
_CHIEF_MINISTER_PARLIAMENTS = (0, 1, 2, 3)
_EARLY_CHIEF_MINISTER = "David Marshall"
_LATER_CHIEF_MINISTER = "Lim Yew Hock"
_PERCENT = 100
_TOP_UNMATCHED_COUNT = 20
_SEPARATOR_WIDTH = 50


def _has_title(match: re.Match) -> bool:
    inner = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", match.group(1).strip())
    return strip_title(inner) != inner


def _get_presiding_officer_role(raw: str) -> Optional[str]:
    if raw in ("Mr Speaker", "Mdm Speaker"):
        return "SPEAKER"
    if raw.startswith("Mr Deputy Speaker") or raw.startswith("The Deputy Speaker"):
        return "DEPUTY SPEAKER"
    return None


def _preprocess(speaker: str) -> Optional[str]:
    if speaker in NON_SPEAKERS or speaker.startswith("(") or speaker.startswith("_"):
        return None
    raw = speaker.rstrip(":").strip()
    parentheticals = list(re.finditer(r"\(([^)]+)\)", raw))
    if parentheticals:
        titled_parenthetical = next(
            (match for match in reversed(parentheticals) if _has_title(match)),
            None,
        )
        if titled_parenthetical is not None:
            raw = titled_parenthetical.group(1).strip()
        else:
            raw = raw[: parentheticals[0].start()].strip()
    raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
    name = normalize_name(strip_title(raw))
    return name or None


def _resolve(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    name_and_parliament_to_speaker_id: dict[tuple[str, int], int],
) -> tuple[Optional[str], int]:
    canonical = resolve_canonical_name(name, parliament, lookups)
    if canonical is not None or parliament != _COLONIAL_PARLIAMENT_NUMBER:
        return canonical, parliament
    for fallback in COLONIAL_PARLIAMENT_FALLBACKS:
        candidate = resolve_canonical_name(name, fallback, lookups)
        if candidate is not None and (candidate, fallback) in name_and_parliament_to_speaker_id:
            return candidate, fallback
    return None, parliament


def _get_role_key(raw: str, parliament: int) -> Optional[tuple[str, int]]:
    if parliament != _COLONIAL_PARLIAMENT_NUMBER:
        return (raw, parliament)
    for fallback_parliament in COLONIAL_PARLIAMENT_FALLBACKS:
        if (raw, fallback_parliament) in ROLE_ONLY_SPEAKERS:
            return (raw, fallback_parliament)
    return None


def main() -> None:
    sample = json.loads(_SAMPLE_PATH.read_text())
    pilot_ids: list[int] = sample["pilot"]

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        rows = CRUDSpeech(session).get_speaker_rows_by_ids(pilot_ids)

    name_and_parliament_to_speaker_id = {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None}
    lookups = build_speaker_lookups(speakers)

    speech_id_to_row = {row.id: row for row in rows}

    bucket_to_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"matched": 0, "total": 0})
    unmatched: list[tuple[str, int, str]] = []

    for speech_id in pilot_ids:
        if speech_id not in speech_id_to_row:
            continue
        row = speech_id_to_row[speech_id]
        speaker, parliament, sitting_date = row.speaker, row.parliament_number, row.sitting_date
        if not speaker:
            continue

        bucket = "colonial(parl=0)" if parliament == _COLONIAL_PARLIAMENT_NUMBER else f"parl={parliament}"

        raw = speaker.rstrip(":").strip()
        presiding_officer_role = _get_presiding_officer_role(raw)
        if presiding_officer_role is not None:
            presiding_officer_parliament = parliament if parliament != _COLONIAL_PARLIAMENT_NUMBER else next(
                (fallback_parliament for fallback_parliament in COLONIAL_PARLIAMENT_FALLBACKS if (presiding_officer_role, fallback_parliament) in PRESIDING_OFFICERS),
                parliament,
            )
            presiding_officer_name = PRESIDING_OFFICERS.get((presiding_officer_role, presiding_officer_parliament))
            bucket_to_stats[bucket]["total"] += 1
            if presiding_officer_name is not None:
                presiding_officer_canonical, presiding_officer_resolved_parliament = _resolve(presiding_officer_name, presiding_officer_parliament, lookups, name_and_parliament_to_speaker_id)
                presiding_officer_speaker_id = name_and_parliament_to_speaker_id.get((presiding_officer_canonical, presiding_officer_resolved_parliament)) if presiding_officer_canonical is not None else None
                if presiding_officer_speaker_id is not None:
                    bucket_to_stats[bucket]["matched"] += 1
                else:
                    unmatched.append((speaker, parliament, presiding_officer_canonical or "<unresolved>"))
            else:
                unmatched.append((speaker, parliament, "<no presiding officer mapping>"))
            continue

        if raw == "The Chief Minister" and parliament in _CHIEF_MINISTER_PARLIAMENTS:
            chief_minister_name = (
                _EARLY_CHIEF_MINISTER
                if sitting_date is not None and sitting_date < CHIEF_MINISTER_CUTOFF
                else _LATER_CHIEF_MINISTER
            )
            chief_minister_canonical, chief_minister_parliament = _resolve(chief_minister_name, _COLONIAL_PARLIAMENT_NUMBER, lookups, name_and_parliament_to_speaker_id)
            chief_minister_speaker_id = name_and_parliament_to_speaker_id.get((chief_minister_canonical, chief_minister_parliament)) if chief_minister_canonical is not None else None
            bucket_to_stats[bucket]["total"] += 1
            if chief_minister_speaker_id is not None:
                bucket_to_stats[bucket]["matched"] += 1
            else:
                unmatched.append((speaker, parliament, chief_minister_canonical or "<unresolved>"))
            continue

        role_key = _get_role_key(raw, parliament)
        if role_key is not None and role_key in ROLE_ONLY_SPEAKERS:
            role_name = ROLE_ONLY_SPEAKERS[role_key]
            role_canonical, role_parliament = _resolve(role_name, role_key[1], lookups, name_and_parliament_to_speaker_id)
            role_speaker_id = name_and_parliament_to_speaker_id.get((role_canonical, role_parliament)) if role_canonical is not None else None
            bucket_to_stats[bucket]["total"] += 1
            if role_speaker_id is not None:
                bucket_to_stats[bucket]["matched"] += 1
            else:
                unmatched.append((speaker, parliament, role_canonical or "<unresolved>"))
            continue

        name = _preprocess(speaker)
        if name is None:
            unmatched.append((speaker, parliament, "<excluded/empty>"))
            continue

        canonical, resolved_parliament = _resolve(name, parliament, lookups, name_and_parliament_to_speaker_id)
        speaker_id = name_and_parliament_to_speaker_id.get((canonical, resolved_parliament)) if canonical is not None else None

        bucket_to_stats[bucket]["total"] += 1
        if speaker_id is not None:
            bucket_to_stats[bucket]["matched"] += 1
        else:
            unmatched.append((speaker, parliament, canonical or "<unresolved>"))

    total = sum(stats["total"] for stats in bucket_to_stats.values())
    matched = sum(stats["matched"] for stats in bucket_to_stats.values())
    logger.info(f"\nPilot ({len(pilot_ids)} IDs): {matched}/{total} = {matched/total*_PERCENT:.1f}%\n")
    logger.info(f"{'Group':<25} {'Matched':>8} {'Total':>7} {'Rate':>7}")
    logger.info("-" * _SEPARATOR_WIDTH)
    for bucket, stats in sorted(bucket_to_stats.items()):
        matched_count, total_count = stats["matched"], stats["total"]
        rate = matched_count / total_count * _PERCENT if total_count else 0.0
        logger.info(f"{bucket:<25} {matched_count:>8} {total_count:>7} {rate:>6.1f}%")

    logger.info(f"\nTop unmatched speaker strings ({len(unmatched)} total):")
    from collections import Counter
    top = Counter(unmatched_speaker for unmatched_speaker, _, _ in unmatched).most_common(_TOP_UNMATCHED_COUNT)
    for speaker, count in top:
        logger.info(f"  {count:>3}x  {speaker!r}")


if __name__ == "__main__":
    main()

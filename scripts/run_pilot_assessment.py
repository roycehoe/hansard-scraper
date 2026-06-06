"""
Run the full resolution pipeline against the fixed pilot set in sample.json
and report match rates by report_type.

Unlike speech_speaker_match_rate.py (random sampling), this uses the fixed
pilot IDs so results are comparable across iterations.

Usage:
    PYTHONPATH=. poetry run python3 scripts/run_pilot_assessment.py
"""
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from database.init import engine
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
    normalize_name,
    resolve_canonical_name,
    strip_title,
)

_SAMPLE_PATH = Path(__file__).parent.parent / "docs" / "speech-speaker" / "sample.json"


def _has_title(m: re.Match) -> bool:
    inner = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", m.group(1).strip())
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
    parens = list(re.finditer(r"\(([^)]+)\)", raw))
    if parens:
        title_paren = next(
            (m for m in reversed(parens) if _has_title(m)),
            None,
        )
        if title_paren:
            raw = title_paren.group(1).strip()
        else:
            raw = raw[: parens[0].start()].strip()
    raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
    name = normalize_name(strip_title(raw))
    return name or None


def _resolve(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> tuple[Optional[str], int]:
    canonical = resolve_canonical_name(name, parliament, lookups)
    if canonical is not None or parliament != 0:
        return canonical, parliament
    for fallback in COLONIAL_PARLIAMENT_FALLBACKS:
        candidate = resolve_canonical_name(name, fallback, lookups)
        if candidate and (candidate, fallback) in speaker_id_lookup:
            return candidate, fallback
    return None, parliament


def main() -> None:
    sample = json.loads(_SAMPLE_PATH.read_text())
    pilot_ids: list[int] = sample["pilot"]

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        rows = CRUDSpeech(session).get_speaker_info_by_ids(pilot_ids)

    speaker_id_lookup = {(s.name, s.parliament_number): s.id for s in speakers if s.id is not None}
    lookups = build_speaker_lookups(speakers)

    rows_by_id: dict[int, tuple[str, int, object]] = {
        speech_id: (speaker, parliament, sitting_date)
        for speech_id, speaker, parliament, sitting_date in rows
    }

    type_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"matched": 0, "total": 0})
    unmatched: list[tuple[str, int, str]] = []

    for speech_id in pilot_ids:
        if speech_id not in rows_by_id:
            continue
        speaker, parliament, sitting_date = rows_by_id[speech_id]
        if not speaker:
            continue

        # Derive report_type from rows — need it for stats
        # We only have (speaker, parliament) here; get report_type via a separate lookup
        # Fall back to grouping by parliament bucket instead
        bucket = "colonial(parl=0)" if parliament == 0 else f"parl={parliament}"

        raw = speaker.rstrip(":").strip()
        po_role = _get_presiding_officer_role(raw)
        if po_role is not None:
            po_parl = parliament if parliament != 0 else next(
                (p for p in COLONIAL_PARLIAMENT_FALLBACKS if (po_role, p) in PRESIDING_OFFICERS),
                parliament,
            )
            po_name = PRESIDING_OFFICERS.get((po_role, po_parl))
            type_stats[bucket]["total"] += 1
            if po_name:
                po_canonical, po_resolved_parl = _resolve(po_name, po_parl, lookups, speaker_id_lookup)
                po_sid = speaker_id_lookup.get((po_canonical, po_resolved_parl)) if po_canonical else None
                if po_sid:
                    type_stats[bucket]["matched"] += 1
                else:
                    unmatched.append((speaker, parliament, po_canonical or "<unresolved>"))
            else:
                unmatched.append((speaker, parliament, "<no presiding officer mapping>"))
            continue

        # Chief Minister (colonial era): date-based dispatch between Marshall and Lim.
        if raw == "The Chief Minister" and parliament in (0, 1, 2, 3):
            _cm_name = (
                "David Marshall"
                if sitting_date and sitting_date < CHIEF_MINISTER_CUTOFF
                else "Lim Yew Hock"
            )
            _cm_canonical, _cm_parl = _resolve(_cm_name, 0, lookups, speaker_id_lookup)
            _cm_sid = speaker_id_lookup.get((_cm_canonical, _cm_parl)) if _cm_canonical else None
            type_stats[bucket]["total"] += 1
            if _cm_sid:
                type_stats[bucket]["matched"] += 1
            else:
                unmatched.append((speaker, parliament, _cm_canonical or "<unresolved>"))
            continue

        # Role-only strings — resolve by parliament→person mapping.
        _role_key: Optional[tuple[str, int]] = (raw, parliament) if parliament != 0 else None
        if _role_key is None:
            for _fb in COLONIAL_PARLIAMENT_FALLBACKS:
                if (raw, _fb) in ROLE_ONLY_SPEAKERS:
                    _role_key = (raw, _fb)
                    break
        if _role_key and _role_key in ROLE_ONLY_SPEAKERS:
            _role_name = ROLE_ONLY_SPEAKERS[_role_key]
            _role_canonical, _role_parl = _resolve(_role_name, _role_key[1], lookups, speaker_id_lookup)
            _role_sid = speaker_id_lookup.get((_role_canonical, _role_parl)) if _role_canonical else None
            type_stats[bucket]["total"] += 1
            if _role_sid:
                type_stats[bucket]["matched"] += 1
            else:
                unmatched.append((speaker, parliament, _role_canonical or "<unresolved>"))
            continue  # role-only strings are never resolvable via the name cascade

        name = _preprocess(speaker)
        if not name:
            # Structural exclusion: artifact or collective reference — not in denominator.
            unmatched.append((speaker, parliament, "<excluded/empty>"))
            continue

        canonical, resolved_parl = _resolve(name, parliament, lookups, speaker_id_lookup)
        speaker_id = speaker_id_lookup.get((canonical, resolved_parl)) if canonical else None

        type_stats[bucket]["total"] += 1
        if speaker_id:
            type_stats[bucket]["matched"] += 1
        else:
            unmatched.append((speaker, parliament, canonical or "<unresolved>"))

    total = sum(s["total"] for s in type_stats.values())
    matched = sum(s["matched"] for s in type_stats.values())
    print(f"\nPilot ({len(pilot_ids)} IDs): {matched}/{total} = {matched/total*100:.1f}%\n")
    print(f"{'Group':<25} {'Matched':>8} {'Total':>7} {'Rate':>7}")
    print("-" * 50)
    for bucket, stats in sorted(type_stats.items()):
        m, t = stats["matched"], stats["total"]
        rate = m / t * 100 if t else 0.0
        print(f"{bucket:<25} {m:>8} {t:>7} {rate:>6.1f}%")

    print(f"\nTop unmatched speaker strings ({len(unmatched)} total):")
    from collections import Counter
    top = Counter(s for s, _, _ in unmatched).most_common(20)
    for speaker, count in top:
        print(f"  {count:>3}x  {speaker!r}")


if __name__ == "__main__":
    main()

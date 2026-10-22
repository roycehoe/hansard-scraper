import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechParliamentRow
from database.init import engine
from logs import logger
from services.attendance import build_speaker_lookups
from utils.names import (
    normalize_name,
    strip_title,
)
from utils.speaker_resolution import SpeakerLookups, resolve_canonical_name

_SAMPLE_PATH = Path(__file__).parent.parent / "docs" / "speech-mp" / "sample.json"
_SEED = 42
_PILOT_COUNT_PER_TYPE = 5
_HELD_OUT_COUNT_PER_TYPE = 3
_COLONIAL_PARLIAMENT_FALLBACKS = (1, 2, 3)
_COLONIAL_PARLIAMENT_NUMBER = 0
_PILOT_TO_REGRESSION_RATIO = 5
_MIN_REGRESSION_COUNT = 1
_JSON_INDENT = 2

_STRUCTURAL_EXCLUSIONS = frozenset({
    "An hon. Member", "Some hon. Members", "Non-Residents",
    "Tributes by Leader of the House and Opposition Leaders",
    "Mr Speaker", "Mr Deputy Speaker", "The Clerk", "Hon. Members",
    "Several Members", "Members",
})
_SECTION_HEADER_RE = re.compile(r"^[A-Z][A-Z0-9 /(),.\-]+$")


def _is_excluded(speaker: str) -> bool:
    if speaker in _STRUCTURAL_EXCLUSIONS:
        return True
    if speaker.startswith("Mr Deputy Speaker (") or speaker.startswith("The Deputy Speaker ("):
        return True
    if _SECTION_HEADER_RE.match(speaker):
        return True
    return False


def _preprocess(speaker: str) -> Optional[str]:
    if _is_excluded(speaker) or speaker.startswith("(") or speaker.startswith("_"):
        return None
    raw = speaker.rstrip(":").strip()
    parenthetical_match = re.search(r"\s*\(([^)]+)\)\s*$", raw)
    if parenthetical_match is not None:
        inner = parenthetical_match.group(1).strip()
        if strip_title(inner) != inner:
            raw = inner
        else:
            raw = raw[: parenthetical_match.start()]
    raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
    name = normalize_name(strip_title(raw))
    return name or None


def _is_resolved(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    name_and_parliament_to_speaker_id: dict[tuple[str, int], int],
) -> bool:
    canonical = resolve_canonical_name(name, parliament, lookups)
    if canonical is not None:
        return (canonical, parliament) in name_and_parliament_to_speaker_id
    if parliament == _COLONIAL_PARLIAMENT_NUMBER:
        for fallback in _COLONIAL_PARLIAMENT_FALLBACKS:
            candidate = resolve_canonical_name(name, fallback, lookups)
            if candidate is not None and (candidate, fallback) in name_and_parliament_to_speaker_id:
                return True
    return False


def main() -> None:
    random.seed(_SEED)

    sample = json.loads(_SAMPLE_PATH.read_text())
    existing_ids = set(sample["pilot"] + sample["held_out"] + sample["regression"])

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        rows = CRUDSpeech(session).get_parliament_rows_by_speaker_not_null_and_parliament_number(_COLONIAL_PARLIAMENT_NUMBER)

    name_and_parliament_to_speaker_id = {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None}
    lookups = build_speaker_lookups(speakers)

    eligible: list[SpeechParliamentRow] = []
    for row in rows:
        if not row.speaker:
            continue
        if row.id in existing_ids:
            continue
        if _is_excluded(row.speaker) or row.speaker.startswith("(") or row.speaker.startswith("_"):
            continue
        eligible.append(row)

    speech_id_to_row = {row.id: row for row in eligible}

    report_type_to_rows: dict[str, list[SpeechParliamentRow]] = defaultdict(list)
    for row in eligible:
        report_type_to_rows[row.report_type].append(row)

    new_pilot: list[int] = []
    new_held_out: list[int] = []

    logger.info(f"Eligible parliament=0 speeches (excluding existing sample): {len(eligible)}")
    logger.info("\nSampling per report_type:")
    for report_type, items in sorted(report_type_to_rows.items()):
        random.shuffle(items)
        pilot_slice = items[:_PILOT_COUNT_PER_TYPE]
        held_out_slice = items[_PILOT_COUNT_PER_TYPE : _PILOT_COUNT_PER_TYPE + _HELD_OUT_COUNT_PER_TYPE]
        new_pilot.extend(row.id for row in pilot_slice)
        new_held_out.extend(row.id for row in held_out_slice)
        logger.info(f"  {report_type:<30} {len(pilot_slice)} pilot + {len(held_out_slice)} held-out")

    passing_pilot: list[int] = []
    for speech_id in new_pilot:
        if speech_id not in speech_id_to_row:
            continue
        eligible_row = speech_id_to_row[speech_id]
        name = _preprocess(eligible_row.speaker)
        if name is not None and _is_resolved(name, eligible_row.parliament_number, lookups, name_and_parliament_to_speaker_id):
            passing_pilot.append(speech_id)

    regression_count = max(_MIN_REGRESSION_COUNT, len(new_pilot) // _PILOT_TO_REGRESSION_RATIO)
    new_regression = random.sample(passing_pilot, min(regression_count, len(passing_pilot)))

    sample["pilot"].extend(new_pilot)
    sample["held_out"].extend(new_held_out)
    sample["regression"].extend(new_regression)

    _SAMPLE_PATH.write_text(json.dumps(sample, indent=_JSON_INDENT))

    logger.info("\nExpansion summary:")
    logger.info(f"  Added pilot:      {len(new_pilot)}")
    logger.info(f"  Added held-out:   {len(new_held_out)}")
    logger.info(f"  Added regression: {len(new_regression)} (from {len(passing_pilot)} passing new pilot)")
    logger.info(f"  New totals — pilot: {len(sample['pilot'])}, held_out: {len(sample['held_out'])}, regression: {len(sample['regression'])}")


if __name__ == "__main__":
    main()

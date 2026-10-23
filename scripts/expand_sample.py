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
from schemas.sample_sets import SampleSets
from services.attendance import build_speaker_lookups
from utils.names import (
    normalize_name,
    strip_title,
)
from utils.speaker_resolution import SpeakerLookups, resolve_canonical_name
from utils.speaker_resolution_constants import (
    COLONIAL_PARLIAMENT_FALLBACKS,
    COLONIAL_PARLIAMENT_NUMBER,
)

_SAMPLE_PATH = Path(__file__).parent.parent / "docs" / "speech-speaker" / "sample.json"
_SEED = 42
_PILOT_COUNT_PER_TYPE = 5
_HELD_OUT_COUNT_PER_TYPE = 3
_PILOT_TO_REGRESSION_RATIO = 5
_MIN_REGRESSION_COUNT = 1

_STRUCTURAL_EXCLUSIONS = frozenset({
    "An hon. Member", "Some hon. Members", "Non-Residents",
    "Tributes by Leader of the House and Opposition Leaders",
    "Mr Speaker", "Mr Deputy Speaker", "The Clerk", "Hon. Members",
    "Several Members", "Members",
})
_SECTION_HEADER_RE = re.compile(r"^[A-Z][A-Z0-9 /(),.\-]+$")
_TRAILING_PARENTHETICAL_RE = re.compile(r"\s*\(([^)]+)\)\s*$")
_TITLE_WITH_PERIOD_RE = re.compile(r"^(Mr|Mrs|Dr|Ms)\.\s+")


def _is_excluded(speaker: str) -> bool:
    if speaker in _STRUCTURAL_EXCLUSIONS:
        return True
    if speaker.startswith("Mr Deputy Speaker (") or speaker.startswith("The Deputy Speaker ("):
        return True
    if _SECTION_HEADER_RE.match(speaker):
        return True
    return False


def _clean_speaker_label(speaker: str) -> Optional[str]:
    if _is_excluded(speaker) or speaker.startswith("(") or speaker.startswith("_"):
        return None
    raw = speaker.rstrip(":").strip()
    parenthetical_match = _TRAILING_PARENTHETICAL_RE.search(raw)
    if parenthetical_match is not None:
        inner = parenthetical_match.group(1).strip()
        if strip_title(inner) != inner:
            raw = inner
        else:
            raw = raw[: parenthetical_match.start()]
    raw = _TITLE_WITH_PERIOD_RE.sub(r"\1 ", raw)
    name = normalize_name(strip_title(raw))
    return name or None


def _is_resolved(
    name: str,
    parliament_number: int,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> bool:
    canonical_name = resolve_canonical_name(name, parliament_number, lookups)
    if canonical_name is not None:
        return (canonical_name, parliament_number) in name_parliament_number_to_speaker_id
    if parliament_number == COLONIAL_PARLIAMENT_NUMBER:
        for fallback in COLONIAL_PARLIAMENT_FALLBACKS:
            candidate = resolve_canonical_name(name, fallback, lookups)
            if candidate is not None and (candidate, fallback) in name_parliament_number_to_speaker_id:
                return True
    return False


def expand_sample() -> None:
    random.seed(_SEED)

    sample_sets = SampleSets.model_validate_json(_SAMPLE_PATH.read_text())
    existing_ids = set(sample_sets.pilot + sample_sets.held_out + sample_sets.regression)

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        speech_rows = CRUDSpeech(session).get_parliament_rows_by_speaker_not_null_and_parliament_number(COLONIAL_PARLIAMENT_NUMBER)

    name_parliament_number_to_speaker_id = {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None}
    lookups = build_speaker_lookups(speakers)

    eligible: list[SpeechParliamentRow] = []
    for speech_row in speech_rows:
        if not speech_row.speaker:
            continue
        if speech_row.id in existing_ids:
            continue
        if _is_excluded(speech_row.speaker) or speech_row.speaker.startswith("(") or speech_row.speaker.startswith("_"):
            continue
        eligible.append(speech_row)

    speech_id_to_speech_row = {speech_row.id: speech_row for speech_row in eligible}

    report_type_to_speech_rows: dict[str, list[SpeechParliamentRow]] = defaultdict(list)
    for speech_row in eligible:
        report_type_to_speech_rows[speech_row.report_type].append(speech_row)

    new_pilot: list[int] = []
    new_held_out: list[int] = []

    logger.info(f"Eligible parliament=0 speeches (excluding existing sample): {len(eligible)}")
    logger.info("\nSampling per report_type:")
    for report_type, report_type_speech_rows in sorted(report_type_to_speech_rows.items()):
        random.shuffle(report_type_speech_rows)
        pilot_slice = report_type_speech_rows[:_PILOT_COUNT_PER_TYPE]
        held_out_slice = report_type_speech_rows[_PILOT_COUNT_PER_TYPE : _PILOT_COUNT_PER_TYPE + _HELD_OUT_COUNT_PER_TYPE]
        new_pilot.extend(speech_row.id for speech_row in pilot_slice)
        new_held_out.extend(speech_row.id for speech_row in held_out_slice)
        logger.info(f"  {report_type:<30} {len(pilot_slice)} pilot + {len(held_out_slice)} held-out")

    passing_pilot: list[int] = []
    for speech_id in new_pilot:
        if speech_id not in speech_id_to_speech_row:
            continue
        eligible_row = speech_id_to_speech_row[speech_id]
        name = _clean_speaker_label(eligible_row.speaker)
        if name is not None and _is_resolved(name, eligible_row.parliament_number, lookups, name_parliament_number_to_speaker_id):
            passing_pilot.append(speech_id)

    regression_count = max(_MIN_REGRESSION_COUNT, len(new_pilot) // _PILOT_TO_REGRESSION_RATIO)
    new_regression = random.sample(passing_pilot, min(regression_count, len(passing_pilot)))

    sample_sets.pilot.extend(new_pilot)
    sample_sets.held_out.extend(new_held_out)
    sample_sets.regression.extend(new_regression)

    _SAMPLE_PATH.write_text(json.dumps(sample_sets.model_dump(), indent=2))

    logger.info("\nExpansion summary:")
    logger.info(f"  Added pilot:      {len(new_pilot)}")
    logger.info(f"  Added held-out:   {len(new_held_out)}")
    logger.info(f"  Added regression: {len(new_regression)} (from {len(passing_pilot)} passing new pilot)")
    logger.info(f"  New totals — pilot: {len(sample_sets.pilot)}, held_out: {len(sample_sets.held_out)}, regression: {len(sample_sets.regression)}")


if __name__ == "__main__":
    expand_sample()

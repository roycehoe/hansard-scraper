import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from crud.report import CRUDReport
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from database.init import engine
from logs import logger
from populate.speaker_links import REPORT_BATCH
from services.attendance import build_speaker_lookups
from services.attribution import HEADLINE_MAX_PARLIAMENT
from services.speaker_link import (
    BARE_DEPUTY_RE,
    CARRIED_ROLES,
    CHAIRMAN_RE,
    DATE_DEPENDENT_ROLES,
    resolve_speech_speaker_id,
)
from utils.speaker_resolution_constants import HEAD_OF_STATE_TERMS

_STALE_EXIT_CODE = 1
_CLEAN_EXIT_CODE = 0

Key = tuple[str, int, Optional[datetime]]


def _is_context_linked(speaker: str) -> bool:
    return bool(
        CHAIRMAN_RE.match(speaker)
        or speaker in CARRIED_ROLES
        or speaker in HEAD_OF_STATE_TERMS
        or BARE_DEPUTY_RE.match(speaker.strip())
    )


@dataclass(frozen=True)
class StaleLink:
    bad_row_count: int
    speaker: str
    parliament_number: int
    sitting_date: Optional[datetime]
    speaker_id_to_row_count: Counter[int]
    resolved_speaker_id: Optional[int]


def trace_speaker_links() -> None:
    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        reports = [
            (report.id, report.parliament_number, report.sitting_date)
            for report in CRUDReport(session).get_all()
            if report.parliament_number is not None and report.parliament_number <= HEADLINE_MAX_PARLIAMENT
        ]
        name_parliament_number_to_speaker_id = {
            (speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None
        }
        speaker_id_to_name = {speaker.id: speaker.name for speaker in speakers}
        lookups = build_speaker_lookups(speakers)

        key_to_speaker_id_counts: dict[Key, Counter[int]] = {}
        for start in range(0, len(reports), REPORT_BATCH):
            batch = reports[start : start + REPORT_BATCH]
            report_id_to_parliament_number_and_sitting_date = {report_id: (parliament_number, sitting_date) for report_id, parliament_number, sitting_date in batch}
            for speech_row in CRUDSpeech(session).get_rows_by_report_ids(list(report_id_to_parliament_number_and_sitting_date)):
                if not speech_row.speaker or speech_row.speaker_id is None:
                    continue
                parliament_number, sitting_date = report_id_to_parliament_number_and_sitting_date[speech_row.report_id]
                date_key = sitting_date if speech_row.speaker.startswith(DATE_DEPENDENT_ROLES) else None
                key_to_speaker_id_counts.setdefault((speech_row.speaker, parliament_number, date_key), Counter())[speech_row.speaker_id] += 1

    total_rows = sum(sum(counter.values()) for counter in key_to_speaker_id_counts.values())
    agree_key_count = 0
    agree_row_count = 0
    context_key_count = 0
    context_row_count = 0
    stale: list[StaleLink] = []
    for (speaker, parliament_number, sitting_date), counts in key_to_speaker_id_counts.items():
        key_row_count = sum(counts.values())
        resolved = resolve_speech_speaker_id(speaker, parliament_number, sitting_date, lookups, name_parliament_number_to_speaker_id)
        if resolved is None and _is_context_linked(speaker):
            context_key_count += 1
            context_row_count += key_row_count
        elif set(counts) == {resolved}:
            agree_key_count += 1
            agree_row_count += key_row_count
        else:
            bad_rows = sum(row_count for speaker_id, row_count in counts.items() if speaker_id != resolved)
            stale.append(StaleLink(bad_rows, speaker, parliament_number, sitting_date, counts, resolved))

    stale_rows = sum(stale_link.bad_row_count for stale_link in stale)
    logger.info(f"Total: {len(key_to_speaker_id_counts)} keys, {total_rows} rows")
    logger.info(f"Agree: {agree_key_count} keys, {agree_row_count} rows")
    logger.info(f"Context-linked, not re-evaluated: {context_key_count} keys, {context_row_count} rows")
    logger.info(f"Stale: {len(stale)} keys, {stale_rows} rows")
    for stale_link in sorted(stale, key=lambda stale_link: (-stale_link.bad_row_count, stale_link.speaker, stale_link.parliament_number)):
        stored_text = ", ".join(
            f"{speaker_id} {speaker_id_to_name.get(speaker_id)!r} x{row_count}" for speaker_id, row_count in sorted(stale_link.speaker_id_to_row_count.items())
        )
        logger.info(
            f"{stale_link.bad_row_count:>6}  {stale_link.speaker!r}  P{stale_link.parliament_number}  "
            f"{stale_link.sitting_date.date() if stale_link.sitting_date is not None else '-'}  "
            f"stored [{stored_text}]  resolved {stale_link.resolved_speaker_id} {speaker_id_to_name.get(stale_link.resolved_speaker_id)!r}"
        )
    sys.exit(_STALE_EXIT_CODE if stale_rows else _CLEAN_EXIT_CODE)


if __name__ == "__main__":
    trace_speaker_links()

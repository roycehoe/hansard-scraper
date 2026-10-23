import argparse
from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session

import database.speaker  # noqa: F401 registers Speaker so the speech.speaker_id foreign key resolves
from crud.report import CRUDReport
from crud.speech import CRUDSpeech, SpeechRow
from database.init import engine
from database.report import Report
from database.speech import Speech
from exceptions import HansardWriteCheckError
from logs import logger
from populate.column_numbers import get_column_number_plan, write_column_number_plan
from populate.written_tables import vacuum_analyze_written_tables
from schemas.unattributed_speech import UnattributedSpeechRange
from services.speech import build_report_speeches
from settings import settings
from utils.data_files import get_unattributed_speech_ranges
from utils.text import TextChange
from utils.write_target import validate_can_write

_LEADING_UNDERSCORE_PATTERN = "^_"
_REPORT_BATCH = 200


@dataclass
class LanguageNoteCloseMarkPlan:
    report_count: int
    transcript_changes: list[TextChange] = field(default_factory=list)
    report_ids: list[int] = field(default_factory=list)
    other_difference_row_count: int = 0
    unaligned_report_ids: list[int] = field(default_factory=list)


def _is_close_mark_change(stored_transcript: str, parsed_transcript: str) -> bool:
    return stored_transcript.startswith("_") and stored_transcript[1:].lstrip() == parsed_transcript


def _add_report(plan: LanguageNoteCloseMarkPlan, report: Report, speech_rows: list[SpeechRow], report_id_to_unattributed_range: dict[int, UnattributedSpeechRange]) -> None:
    parsed_speeches = build_report_speeches(report, report_id_to_unattributed_range).speeches
    if len(parsed_speeches) != len(speech_rows):
        plan.unaligned_report_ids.append(report.id)
        return
    transcript_changes = [
        TextChange(speech_row.id, speech_row.transcript, parsed_speech.transcript)
        for speech_row, parsed_speech in zip(speech_rows, parsed_speeches, strict=True)
        if speech_row.speaker == parsed_speech.speaker and _is_close_mark_change(speech_row.transcript, parsed_speech.transcript)
    ]
    different_row_count = sum(
        speech_row.speaker != parsed_speech.speaker or speech_row.transcript != parsed_speech.transcript
        for speech_row, parsed_speech in zip(speech_rows, parsed_speeches, strict=True)
    )
    plan.other_difference_row_count += different_row_count - len(transcript_changes)
    if transcript_changes:
        plan.transcript_changes.extend(transcript_changes)
        plan.report_ids.append(report.id)


def _get_language_note_close_mark_plan(session: Session) -> LanguageNoteCloseMarkPlan:
    report_id_to_unattributed_range = {speech_range.report_id: speech_range for speech_range in get_unattributed_speech_ranges()}
    report_ids = sorted(CRUDSpeech(session).get_report_ids_by_transcript_regex(_LEADING_UNDERSCORE_PATTERN))
    plan = LanguageNoteCloseMarkPlan(len(report_ids))
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch_report_ids = report_ids[start : start + _REPORT_BATCH]
        report_id_to_speech_rows = defaultdict(list)
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(batch_report_ids):
            report_id_to_speech_rows[speech_row.report_id].append(speech_row)
        for report in CRUDReport(session).get_by_ids(batch_report_ids):
            _add_report(plan, report, report_id_to_speech_rows[report.id], report_id_to_unattributed_range)
        session.expunge_all()
    return plan


def _write_language_note_close_marks(session: Session, plan: LanguageNoteCloseMarkPlan) -> None:
    written_count = CRUDSpeech(session).set_transcripts_bulk_by_transcript(plan.transcript_changes)
    if written_count != len(plan.transcript_changes):
        raise HansardWriteCheckError(f"Rows changed since the plan was made: planned {len(plan.transcript_changes)}, written {written_count}")
    if _get_language_note_close_mark_plan(session).transcript_changes:
        raise HansardWriteCheckError("Rows the close mark rule rewrites remain after the update")


def apply_language_note_close_marks(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = _get_language_note_close_mark_plan(session)
        logger.info(
            f"Plan: {len(plan.transcript_changes):,} transcripts in {len(plan.report_ids):,} reports lose the close mark a language note left open."
            f" Read {plan.report_count:,} reports with a transcript that starts with an underscore."
            f" Not written: {plan.other_difference_row_count:,} rows that differ from the parse in another way,"
            f" and {len(plan.unaligned_report_ids):,} reports whose parse has another row count ({', '.join(map(str, plan.unaligned_report_ids)) or 'none'})"
        )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _write_language_note_close_marks(session, plan)
        column_number_plan = get_column_number_plan(session, plan.report_ids)
        write_column_number_plan(session, column_number_plan)
        session.commit()
        logger.info(
            f"Committed: {len(plan.transcript_changes):,} transcripts. Column pass over their reports: {len(column_number_plan.report_column_ranges):,} report column ranges,"
            f" {len(column_number_plan.speech_id_to_column_start):,} speech start columns and {len(column_number_plan.speech_column_notes):,} speech column notes rewritten"
        )
        vacuum_analyze_written_tables(session, [Speech.__tablename__, Report.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drop the italic close mark a language note left open at the start of stored transcripts, as the parser now does")
    parser.add_argument("--commit", action="store_true", help="write, then set the column numbers of the reports written again; without it the script only reports the plan")
    arguments = parser.parse_args()
    apply_language_note_close_marks(arguments.commit)

import argparse
import os
import re
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
from utils.markdown_parser import get_cleaned_report_markdown
from utils.text import TextChange
from utils.write_target import validate_can_write

_SUPERSCRIPT_TAG_PATTERN = "<[Ss][Uu][Pp]"
_FORMER_EXPONENT_MARKER_PATTERN = r"((?<![A-Za-z])(?:[A-Za-z]|CO|NO|SO|km|cm|mm))\[(\d{1,3}(?:,\d{1,3})*)\]"
_REPORT_BATCH = 200
_CHANGE_CONTEXT_LENGTH = 40


@dataclass
class FootnoteMarkerPlan:
    report_count: int
    markdown_changes: list[TextChange] = field(default_factory=list)
    transcript_changes: list[TextChange] = field(default_factory=list)
    report_ids: list[int] = field(default_factory=list)
    other_markdown_report_ids: list[int] = field(default_factory=list)
    other_difference_row_count: int = 0
    unaligned_report_ids: list[int] = field(default_factory=list)


def _is_footnote_marker_change(stored_text: str, parsed_text: str) -> bool:
    return stored_text != parsed_text and re.sub(_FORMER_EXPONENT_MARKER_PATTERN, r"\1\2", parsed_text) == stored_text


def _add_report_rows(plan: FootnoteMarkerPlan, report: Report, speech_rows: list[SpeechRow], report_id_to_unattributed_range: dict[int, UnattributedSpeechRange]) -> None:
    parsed_speeches = build_report_speeches(report, report_id_to_unattributed_range).speeches
    if len(parsed_speeches) != len(speech_rows):
        plan.unaligned_report_ids.append(report.id)
        return
    transcript_changes = [
        TextChange(speech_row.id, speech_row.transcript, parsed_speech.transcript)
        for speech_row, parsed_speech in zip(speech_rows, parsed_speeches, strict=True)
        if speech_row.speaker == parsed_speech.speaker and _is_footnote_marker_change(speech_row.transcript, parsed_speech.transcript)
    ]
    different_row_count = sum(
        speech_row.speaker != parsed_speech.speaker or speech_row.transcript != parsed_speech.transcript
        for speech_row, parsed_speech in zip(speech_rows, parsed_speeches, strict=True)
    )
    plan.other_difference_row_count += different_row_count - len(transcript_changes)
    if transcript_changes:
        plan.transcript_changes.extend(transcript_changes)
        plan.report_ids.append(report.id)


def _add_report(plan: FootnoteMarkerPlan, report: Report, speech_rows: list[SpeechRow], report_id_to_unattributed_range: dict[int, UnattributedSpeechRange]) -> None:
    markdown = get_cleaned_report_markdown(report.content, report.report_version)
    if markdown == report.markdown_content:
        return
    if report.markdown_content is None or not _is_footnote_marker_change(report.markdown_content, markdown):
        plan.other_markdown_report_ids.append(report.id)
        return
    plan.markdown_changes.append(TextChange(report.id, report.markdown_content, markdown))
    report.markdown_content = markdown
    _add_report_rows(plan, report, speech_rows, report_id_to_unattributed_range)


def _get_footnote_marker_plan(session: Session) -> FootnoteMarkerPlan:
    report_id_to_unattributed_range = {speech_range.report_id: speech_range for speech_range in get_unattributed_speech_ranges()}
    report_ids = CRUDReport(session).get_ids_by_content_regex(_SUPERSCRIPT_TAG_PATTERN)
    plan = FootnoteMarkerPlan(len(report_ids))
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch_report_ids = report_ids[start : start + _REPORT_BATCH]
        report_id_to_speech_rows = defaultdict(list)
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(batch_report_ids):
            report_id_to_speech_rows[speech_row.report_id].append(speech_row)
        reports = CRUDReport(session).get_by_ids(batch_report_ids)
        # NOTE: the reports are detached before their markdown is replaced in memory, so the session never writes it.
        session.expunge_all()
        for report in reports:
            _add_report(plan, report, report_id_to_speech_rows[report.id], report_id_to_unattributed_range)
    return plan


def _write_footnote_markers(session: Session, plan: FootnoteMarkerPlan) -> None:
    written_markdown_count = CRUDReport(session).set_markdown_contents_bulk_by_markdown_content(plan.markdown_changes)
    if written_markdown_count != len(plan.markdown_changes):
        raise HansardWriteCheckError(f"Reports changed since the plan was made: planned {len(plan.markdown_changes)}, written {written_markdown_count}")
    written_transcript_count = CRUDSpeech(session).set_transcripts_bulk_by_transcript(plan.transcript_changes)
    if written_transcript_count != len(plan.transcript_changes):
        raise HansardWriteCheckError(f"Rows changed since the plan was made: planned {len(plan.transcript_changes)}, written {written_transcript_count}")
    if _get_footnote_marker_plan(session).markdown_changes:
        raise HansardWriteCheckError("Reports the footnote marker rule rewrites remain after the update")


def apply_footnote_markers(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = _get_footnote_marker_plan(session)
        logger.info(
            f"Plan: {len(plan.markdown_changes):,} report markdowns and {len(plan.transcript_changes):,} transcripts in {len(plan.report_ids):,} reports"
            f" gain a footnote marker after a unit letter or a possessive. Read {plan.report_count:,} reports whose raw HTML holds a superscript."
            f" Not written: {len(plan.other_markdown_report_ids):,} reports whose markdown differs from the parse in another way ({', '.join(map(str, plan.other_markdown_report_ids)) or 'none'}),"
            f" {plan.other_difference_row_count:,} rows that differ from the parse in another way,"
            f" and {len(plan.unaligned_report_ids):,} reports whose parse has another row count ({', '.join(map(str, plan.unaligned_report_ids)) or 'none'})"
        )
        for transcript_change in plan.transcript_changes:
            change_start = len(os.path.commonprefix([transcript_change.before, transcript_change.after]))
            logger.info(f"Speech {transcript_change.id}: ...{transcript_change.after[max(0, change_start - _CHANGE_CONTEXT_LENGTH) : change_start + _CHANGE_CONTEXT_LENGTH]}...")
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _write_footnote_markers(session, plan)
        column_number_plan = get_column_number_plan(session, plan.report_ids)
        write_column_number_plan(session, column_number_plan)
        session.commit()
        logger.info(
            f"Committed: {len(plan.markdown_changes):,} report markdowns and {len(plan.transcript_changes):,} transcripts. Column pass over their reports:"
            f" {len(column_number_plan.report_column_ranges):,} report column ranges, {len(column_number_plan.speech_id_to_column_start):,} speech start columns"
            f" and {len(column_number_plan.speech_column_notes):,} speech column notes rewritten"
        )
        vacuum_analyze_written_tables(session, [Speech.__tablename__, Report.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write the footnote markers the parser now sets after a unit letter or a possessive to stored markdown and transcripts")
    parser.add_argument("--commit", action="store_true", help="write, then set the column numbers of the reports written again; without it the script only reports the plan")
    arguments = parser.parse_args()
    apply_footnote_markers(arguments.commit)

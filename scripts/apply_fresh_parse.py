import argparse
import difflib
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

import database.speaker  # noqa: F401 registers Speaker so the speech.speaker_id foreign key resolves
from crud.report import CRUDReport
from crud.speech import CRUDSpeech, SpeechParseRow
from database.init import engine
from database.report import Report
from database.speech import Speech
from exceptions import HansardWriteCheckError
from logs import logger
from populate.column_numbers import get_column_number_plan, write_column_number_plan
from populate.speaker_links import link_speakers_by_report_ids_and_sitting_ids
from populate.written_tables import vacuum_analyze_written_tables
from schemas.fresh_parse_plan import (
    FreshParsePlan,
    HeldReports,
    ReportFreshParsePlan,
    SpeechRowInsert,
    SpeechRowUpdate,
)
from schemas.unattributed_speech import UnattributedSpeechRange
from services.speech import (
    ParsedSpeech,
    apply_unattributed_speech_range,
    get_speeches,
    get_start_of_speech_line,
)
from settings import settings
from utils.data_files import get_unattributed_speech_ranges
from utils.markdown_parser import get_cleaned_report_markdown
from utils.speech_update import SpeechUpdate
from utils.text import TextChange
from utils.write_target import validate_can_write

_REPORT_BATCH = 200


def _get_parsed_speeches(report: Report, markdown: str, unattributed_range: Optional[UnattributedSpeechRange]) -> Optional[list[ParsedSpeech]]:
    start_of_speech_line = get_start_of_speech_line(markdown, report.title, report.subtitle, report.original_title, report.report_type, report.report_version)
    if start_of_speech_line is None:
        return None
    speeches = get_speeches(markdown, start_of_speech_line, report.report_type, report.report_version)
    if unattributed_range is None:
        return speeches
    return apply_unattributed_speech_range(speeches, unattributed_range)


def _get_stored_digest(markdown_content: Optional[str], speech_rows: list[SpeechParseRow]) -> str:
    stored_state = [
        markdown_content,
        [[speech_row.id, speech_row.ordinal, speech_row.speaker, speech_row.transcript, speech_row.kind, speech_row.speaker_id] for speech_row in speech_rows],
    ]
    return hashlib.sha256(json.dumps(stored_state).encode("utf-8")).hexdigest()


def _get_report_plan(report: Report, markdown: str, speech_rows: list[SpeechParseRow], parsed_speeches: list[ParsedSpeech]) -> ReportFreshParsePlan:
    updates = []
    deletes = []
    inserts = []
    stored_pairs = [(speech_row.speaker, speech_row.transcript) for speech_row in speech_rows]
    parsed_pairs = [(parsed_speech.speaker, parsed_speech.transcript) for parsed_speech in parsed_speeches]
    for _tag, stored_start, stored_end, parsed_start, parsed_end in difflib.SequenceMatcher(a=stored_pairs, b=parsed_pairs, autojunk=False).get_opcodes():
        paired_count = min(stored_end - stored_start, parsed_end - parsed_start)
        for offset in range(paired_count):
            speech_row = speech_rows[stored_start + offset]
            parsed_speech = parsed_speeches[parsed_start + offset]
            ordinal = parsed_start + offset + 1
            is_speaker_changed = speech_row.speaker != parsed_speech.speaker
            is_transcript_changed = speech_row.transcript != parsed_speech.transcript
            is_ordinal_changed = speech_row.ordinal != ordinal
            if not is_speaker_changed and not is_transcript_changed and not is_ordinal_changed:
                continue
            updates.append(
                SpeechRowUpdate(
                    id=speech_row.id,
                    ordinal=ordinal,
                    speaker=parsed_speech.speaker,
                    transcript=parsed_speech.transcript,
                    kind=parsed_speech.kind if is_speaker_changed or is_transcript_changed else speech_row.kind,
                    is_speaker_changed=is_speaker_changed,
                    is_transcript_changed=is_transcript_changed,
                    is_ordinal_changed=is_ordinal_changed,
                )
            )
        deletes.extend(speech_row.id for speech_row in speech_rows[stored_start + paired_count : stored_end])
        inserts.extend(
            SpeechRowInsert(ordinal=index + 1, speaker=parsed_speeches[index].speaker, transcript=parsed_speeches[index].transcript, kind=parsed_speeches[index].kind)
            for index in range(parsed_start + paired_count, parsed_end)
        )
    return ReportFreshParsePlan(
        report_id=report.id,
        stored_digest=_get_stored_digest(report.markdown_content, speech_rows),
        stored_row_count=len(speech_rows),
        parsed_row_count=len(parsed_speeches),
        markdown_content=None if markdown == report.markdown_content else markdown,
        updates=tuple(updates),
        deletes=tuple(deletes),
        inserts=tuple(inserts),
    )


def _is_report_plan_empty(report_plan: ReportFreshParsePlan) -> bool:
    return report_plan.markdown_content is None and not report_plan.updates and not report_plan.deletes and not report_plan.inserts


def _is_kind_changed(speech_rows: list[SpeechParseRow], parsed_speeches: list[ParsedSpeech]) -> bool:
    return [speech_row.kind for speech_row in speech_rows] != [parsed_speech.kind for parsed_speech in parsed_speeches]


def _get_plan(session: Session, report_ids: list[int], held_report_ids: frozenset[int]) -> FreshParsePlan:
    report_id_to_unattributed_range = {speech_range.report_id: speech_range for speech_range in get_unattributed_speech_ranges()}
    report_plans = []
    planned_held_report_ids = []
    kind_only_report_ids = []
    unparsed_report_ids_with_rows = []
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch_report_ids = report_ids[start : start + _REPORT_BATCH]
        report_id_to_speech_rows = defaultdict(list)
        for speech_row in CRUDSpeech(session).get_parse_rows_by_report_ids(batch_report_ids):
            report_id_to_speech_rows[speech_row.report_id].append(speech_row)
        for report in CRUDReport(session).get_by_ids(batch_report_ids):
            speech_rows = report_id_to_speech_rows[report.id]
            markdown = get_cleaned_report_markdown(report.content, report.report_version)
            parsed_speeches = _get_parsed_speeches(report, markdown, report_id_to_unattributed_range.get(report.id))
            if parsed_speeches is None:
                if speech_rows:
                    unparsed_report_ids_with_rows.append(report.id)
                continue
            report_plan = _get_report_plan(report, markdown, speech_rows, parsed_speeches)
            if _is_report_plan_empty(report_plan) and not _is_kind_changed(speech_rows, parsed_speeches):
                continue
            if report.id in held_report_ids:
                planned_held_report_ids.append(report.id)
                continue
            if _is_report_plan_empty(report_plan):
                kind_only_report_ids.append(report.id)
                continue
            report_plans.append(report_plan)
        session.expunge_all()
        logger.info(f"Read {min(start + _REPORT_BATCH, len(report_ids)):,}/{len(report_ids):,} reports, {len(report_plans):,} to write")
    return FreshParsePlan(
        report_plans=tuple(report_plans),
        held_report_ids=tuple(planned_held_report_ids),
        kind_only_report_ids=tuple(kind_only_report_ids),
        unparsed_report_ids_with_rows=tuple(unparsed_report_ids_with_rows),
    )


def _log_plan(plan: FreshParsePlan) -> None:
    updates = [update for report_plan in plan.report_plans for update in report_plan.updates]
    delete_count = sum(len(report_plan.deletes) for report_plan in plan.report_plans)
    logger.info(
        f"Plan: {len(plan.report_plans):,} reports, {sum(report_plan.stored_row_count for report_plan in plan.report_plans):,} stored rows become"
        f" {sum(report_plan.parsed_row_count for report_plan in plan.report_plans):,}. {len(updates):,} updates"
        f" ({sum(update.is_speaker_changed for update in updates):,} change speaker, {sum(update.is_ordinal_changed for update in updates):,} change ordinal),"
        f" {delete_count:,} deletes, {sum(len(report_plan.inserts) for report_plan in plan.report_plans):,} inserts,"
        f" {sum(report_plan.markdown_content is not None for report_plan in plan.report_plans):,} report markdowns."
        f" Stored (report, ordinal) pairs that move: {sum(update.is_ordinal_changed for update in updates) + delete_count:,}"
        f" ({sum(update.is_ordinal_changed for update in updates):,} rows take another ordinal, {delete_count:,} rows go)."
        f" Not written: {len(plan.held_report_ids):,} held reports that differ, {len(plan.kind_only_report_ids):,} reports that differ in kind only,"
        f" {len(plan.unparsed_report_ids_with_rows):,} reports with rows that do not parse"
    )


def _get_speech_updates(report_plan: ReportFreshParsePlan, speech_rows: list[SpeechParseRow]) -> list[SpeechUpdate]:
    id_to_speaker_id = {speech_row.id: speech_row.speaker_id for speech_row in speech_rows}
    return [
        SpeechUpdate(
            id=update.id,
            ordinal=update.ordinal,
            speaker=update.speaker,
            transcript=update.transcript,
            kind=update.kind,
            speaker_id=None if update.is_speaker_changed else id_to_speaker_id[update.id],
        )
        for update in report_plan.updates
    ]


def _write_report_plans(session: Session, plan: FreshParsePlan) -> None:
    report_ids = [report_plan.report_id for report_plan in plan.report_plans]
    report_id_to_speech_rows = defaultdict(list)
    for speech_row in CRUDSpeech(session).get_parse_rows_by_report_ids(report_ids):
        report_id_to_speech_rows[speech_row.report_id].append(speech_row)
    report_id_to_report = {report.id: report for report in CRUDReport(session).get_by_ids(report_ids)}
    speech_updates = [
        speech_update for report_plan in plan.report_plans for speech_update in _get_speech_updates(report_plan, report_id_to_speech_rows[report_plan.report_id])
    ]
    speech_ids_to_delete = [speech_id for report_plan in plan.report_plans for speech_id in report_plan.deletes]
    markdown_changes = [
        TextChange(report_plan.report_id, report_id_to_report[report_plan.report_id].markdown_content, report_plan.markdown_content)
        for report_plan in plan.report_plans
        if report_plan.markdown_content is not None
    ]
    speeches_to_insert = [
        Speech(
            ordinal=insert.ordinal,
            speaker=insert.speaker,
            transcript=insert.transcript,
            kind=insert.kind,
            sitting_date=report_id_to_report[report_plan.report_id].sitting_date,
            report_id=report_plan.report_id,
        )
        for report_plan in plan.report_plans
        for insert in report_plan.inserts
    ]

    updated_count = CRUDSpeech(session).update_many(speech_updates)
    if updated_count != len(speech_updates):
        raise HansardWriteCheckError(f"Updated {updated_count:,} speech rows, planned {len(speech_updates):,}")
    deleted_count = CRUDSpeech(session).delete_by_ids(speech_ids_to_delete)
    if deleted_count != len(speech_ids_to_delete):
        raise HansardWriteCheckError(f"Deleted {deleted_count:,} speech rows, planned {len(speech_ids_to_delete):,}")
    CRUDSpeech(session).add_many(speeches_to_insert)
    markdown_count = CRUDReport(session).set_markdown_contents_bulk_by_markdown_content(markdown_changes)
    if markdown_count != len(markdown_changes):
        raise HansardWriteCheckError(f"Updated {markdown_count:,} report markdowns, planned {len(markdown_changes):,}")


def _validate_can_commit_fresh_parse(session: Session, report_ids: list[int]) -> None:
    plan = _get_plan(session, report_ids, frozenset())
    if plan.report_plans:
        raise HansardWriteCheckError(f"{len(plan.report_plans):,} written reports still differ from the parse after the write")


def apply_fresh_parse(plan_path: Path, held_path: Path, is_commit: bool) -> None:
    held_report_ids = frozenset(held_report.report_id for held_report in HeldReports.model_validate_json(held_path.read_text()).root)
    if not is_commit:
        with Session(engine) as session:
            plan = _get_plan(session, CRUDReport(session).get_ids_by_markdown_content_not_null(), held_report_ids)
        plan_path.write_text(plan.model_dump_json(indent=1))
        _log_plan(plan)
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = FreshParsePlan.model_validate_json(plan_path.read_text())
    report_ids = [report_plan.report_id for report_plan in reviewed_plan.report_plans]
    with Session(engine) as session:
        CRUDReport(session).get_by_ids_for_update(report_ids)
        plan = _get_plan(session, CRUDReport(session).get_ids_by_markdown_content_not_null(), held_report_ids)
        if plan != reviewed_plan:
            raise HansardWriteCheckError("The plan differs from the reviewed plan")
        _log_plan(plan)
        _write_report_plans(session, plan)
        _validate_can_commit_fresh_parse(session, report_ids)
        link_speakers_by_report_ids_and_sitting_ids(session, report_ids, [])
        column_number_plan = get_column_number_plan(session, report_ids)
        write_column_number_plan(session, column_number_plan)
        session.commit()
        logger.info(
            f"Committed: {len(report_ids):,} reports. Column pass over them: {len(column_number_plan.report_column_ranges):,} report column ranges,"
            f" {len(column_number_plan.speech_id_to_column_start):,} speech start columns and {len(column_number_plan.speech_column_notes):,} speech column notes rewritten"
        )
        vacuum_analyze_written_tables(session, [Speech.__tablename__, Report.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rewrite the stored speech rows of every report whose fresh parse differs, checked against a reviewed plan")
    parser.add_argument("plan", type=Path, help="the plan file: written by a dry run, read by --commit")
    parser.add_argument("--held", type=Path, required=True, help="a JSON list of {report_id, reason}: reports the write leaves as stored")
    parser.add_argument("--commit", action="store_true", help="lock the planned reports, check the plan is unchanged, write it, link and set column numbers")
    arguments = parser.parse_args()
    apply_fresh_parse(arguments.plan, arguments.held, arguments.commit)

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Union

from sqlmodel import Session

from crud.bill_key import BillKeyRow, CRUDBillKey
from crud.bill_report_speaker import BillReportSpeakerRow, CRUDBillReportSpeaker
from crud.bill_stage_line import BillStageLineRow, CRUDBillStageLine
from database.bill_key import BillKey
from database.bill_report_speaker import BillReportSpeaker
from database.bill_stage_line import BillStageLine
from database.init import engine
from logs import logger
from populate.bill_speakers import (
    BillSpeakerCounts,
    get_bill_speaker_counts,
    get_bill_speaker_plan,
    get_report_bill_speaker_plan,
    write_bill_speaker_plan,
    write_report_bill_speaker_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write

_LOGGED_INVOLVED_LIMIT = 20
_KEY_TO_VALUE = dict[tuple[object, ...], tuple[object, ...]]


@dataclass(frozen=True)
class _TableDifference:
    added_count: int
    removed_count: int
    changed_count: int
    involved_ids: list[str]


def _get_table_difference(
    stored_key_to_value: _KEY_TO_VALUE, planned_key_to_value: _KEY_TO_VALUE
) -> _TableDifference:
    added_keys = planned_key_to_value.keys() - stored_key_to_value.keys()
    removed_keys = stored_key_to_value.keys() - planned_key_to_value.keys()
    changed_keys = {
        key
        for key in planned_key_to_value.keys() & stored_key_to_value.keys()
        if planned_key_to_value[key] != stored_key_to_value[key]
    }
    return _TableDifference(
        len(added_keys),
        len(removed_keys),
        len(changed_keys),
        sorted(
            {
                str(involved_id)
                for involved_id, *_ in added_keys | removed_keys | changed_keys
            }
        ),
    )


def _log_table_difference(label: str, difference: _TableDifference) -> None:
    shown_ids = difference.involved_ids[:_LOGGED_INVOLVED_LIMIT]
    hidden_count = len(difference.involved_ids) - len(shown_ids)
    involved = ", ".join(shown_ids) or "none"
    if hidden_count > 0:
        involved = f"{involved} and {hidden_count:,} more"
    logger.info(
        f"{label}: {difference.added_count:,} to add, {difference.removed_count:,} to remove, {difference.changed_count:,} to change; involved: {involved}"
    )


def _get_bill_key_map(
    bill_keys: Sequence[Union[BillKey, BillKeyRow]],
) -> _KEY_TO_VALUE:
    return {
        (bill_key.bill_id,): (bill_key.bill_key, bill_key.act_count)
        for bill_key in bill_keys
    }


def _get_bill_report_speaker_map(
    bill_report_speakers: Sequence[Union[BillReportSpeaker, BillReportSpeakerRow]],
) -> _KEY_TO_VALUE:
    return {
        (bill_report_speaker.sprs_report_id, bill_report_speaker.speaker_id): (
            bill_report_speaker.speech_count,
            bill_report_speaker.first_ordinal,
            bill_report_speaker.printed_speaker,
        )
        for bill_report_speaker in bill_report_speakers
    }


def _get_bill_stage_line_map(
    bill_stage_lines: Sequence[Union[BillStageLine, BillStageLineRow]],
) -> _KEY_TO_VALUE:
    return {
        (
            bill_stage_line.sprs_report_id,
            bill_stage_line.ordinal,
            bill_stage_line.stage,
        ): (bill_stage_line.printed_text,)
        for bill_stage_line in bill_stage_lines
    }


def _log_counts(counts: BillSpeakerCounts) -> None:
    for group, row_count in sorted(counts.group_to_member_row_count.items()):
        logger.info(f"{group}: {row_count:,} bill report speakers")
    for stage, line_count in sorted(counts.stage_to_line_count.items()):
        logger.info(f"{stage}: {line_count:,} bill stage lines")


def _apply_corpus_plan(session: Session, is_commit: bool) -> None:
    plan = get_bill_speaker_plan(session)
    _log_counts(
        get_bill_speaker_counts(
            session, plan.bill_report_speakers, plan.bill_stage_lines
        )
    )
    logger.info(
        f"Plan: {len(plan.bill_keys):,} bill keys, {len(plan.bill_report_speakers):,} bill report speakers and {len(plan.bill_stage_lines):,} bill stage lines for {len(plan.bill_keys):,} bills"
    )
    _log_table_difference(
        "Bill keys",
        _get_table_difference(
            _get_bill_key_map(CRUDBillKey(session).get_rows()),
            _get_bill_key_map(plan.bill_keys),
        ),
    )
    _log_table_difference(
        "Bill report speakers",
        _get_table_difference(
            _get_bill_report_speaker_map(CRUDBillReportSpeaker(session).get_rows()),
            _get_bill_report_speaker_map(plan.bill_report_speakers),
        ),
    )
    _log_table_difference(
        "Bill stage lines",
        _get_table_difference(
            _get_bill_stage_line_map(CRUDBillStageLine(session).get_rows()),
            _get_bill_stage_line_map(plan.bill_stage_lines),
        ),
    )
    if not is_commit:
        logger.info("Dry run: nothing written")
        return

    write_bill_speaker_plan(session, plan)
    session.commit()
    logger.info("Committed")
    vacuum_analyze_written_tables(
        session,
        [
            BillKey.__tablename__,
            BillReportSpeaker.__tablename__,
            BillStageLine.__tablename__,
        ],
    )


def _apply_report_plan(
    session: Session, report_ids: list[int], is_commit: bool
) -> None:
    plan = get_report_bill_speaker_plan(session, report_ids)
    _log_counts(
        get_bill_speaker_counts(
            session, plan.bill_report_speakers, plan.bill_stage_lines
        )
    )
    logger.info(
        f"Plan: {len(plan.bill_report_speakers):,} bill report speakers and {len(plan.bill_stage_lines):,} bill stage lines for {len(plan.sprs_report_ids):,} reports"
    )
    _log_table_difference(
        "Bill report speakers",
        _get_table_difference(
            _get_bill_report_speaker_map(
                CRUDBillReportSpeaker(session).get_rows_by_sprs_report_ids(
                    plan.sprs_report_ids
                )
            ),
            _get_bill_report_speaker_map(plan.bill_report_speakers),
        ),
    )
    _log_table_difference(
        "Bill stage lines",
        _get_table_difference(
            _get_bill_stage_line_map(
                CRUDBillStageLine(session).get_rows_by_sprs_report_ids(
                    plan.sprs_report_ids
                )
            ),
            _get_bill_stage_line_map(plan.bill_stage_lines),
        ),
    )
    if not is_commit:
        logger.info("Dry run: nothing written")
        return

    write_report_bill_speaker_plan(session, plan)
    session.commit()
    logger.info("Committed")
    vacuum_analyze_written_tables(
        session,
        [BillReportSpeaker.__tablename__, BillStageLine.__tablename__],
    )


def apply_bill_speakers(report_ids: list[int], is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        if report_ids:
            _apply_report_plan(session, report_ids, is_commit)
            return

        _apply_corpus_plan(session, is_commit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the bill keys, the members who spoke in each bill report and the stage lines of each bill report"
    )
    parser.add_argument(
        "--report-id",
        type=int,
        nargs="+",
        action="extend",
        default=[],
        help="only the member and stage rows of these reports (report.id), including a report that no bill holds, whose stale rows are removed; without it all three tables are rebuilt",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored counts by decade, report type and stage, and each bill's key, against the plan; without it the script only reports the plan and the rows it would add, remove and change",
    )
    arguments = parser.parse_args()
    apply_bill_speakers(arguments.report_id, arguments.commit)

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Union

from sqlmodel import Session

from crud.act_history_entry import CRUDActHistoryEntry
from crud.bill import CRUDBill
from crud.bill_key import CRUDBillKey
from crud.bill_report import BillReportSittingDateReportTypeRow, CRUDBillReport
from crud.bill_report_speaker import BillReportSpeakerRow, CRUDBillReportSpeaker
from crud.bill_stage_line import BillStageLineRow, CRUDBillStageLine
from crud.report import CRUDReport, ReportPlacementRow
from crud.speech import CRUDSpeech
from database.bill import Bill, BillReport
from database.bill_key import BillKey
from database.bill_report_speaker import BillReportSpeaker
from database.bill_stage_line import BillStageLine
from enums import BillReportRole, BillStage, ReportType, SpeechKind
from exceptions import HansardWriteCheckError
from logs import logger
from services.bill import (
    FIRST_READING_PATTERN,
    NOT_FIRST_READING_PATTERNS,
    NOT_THIRD_READING_PATTERNS,
    SECOND_READING_AGREED_PATTERN,
    SECOND_READING_PATTERN,
    THIRD_READING_PATTERN,
    BillPlacement,
    get_bill_class,
    is_other_type_bill_reading,
    place_bill_reports,
)
from services.bill_speaker import (
    build_bill_report_speakers,
    build_bill_stage_lines,
    get_bill_key,
)
from utils.bill_join_update import BillJoinUpdate
from utils.title_key import get_title_key

_REPORT_BATCH = 200
_YEARS_PER_DECADE = 10
_STAGE_LINE_KINDS = (SpeechKind.PROCEDURAL, SpeechKind.UNCLASSIFIED)
_BILL_REPORT_TYPES = (ReportType.BILL, ReportType.BILL_INTRODUCTION)


@dataclass(frozen=True)
class BillSpeakerPlan:
    bill_keys: list[BillKey]
    bill_report_speakers: list[BillReportSpeaker]
    bill_stage_lines: list[BillStageLine]


@dataclass(frozen=True)
class ReportBillSpeakerPlan:
    sprs_report_ids: list[str]
    bill_report_speakers: list[BillReportSpeaker]
    bill_stage_lines: list[BillStageLine]


@dataclass(frozen=True)
class BillSpeakerCounts:
    group_to_member_row_count: Counter[str]
    stage_to_line_count: Counter[BillStage]


@dataclass(frozen=True)
class _PlannedRows:
    bill_report_speakers: list[BillReportSpeaker]
    bill_stage_lines: list[BillStageLine]


@dataclass(frozen=True)
class _StoredRows:
    bill_report_speaker_rows: list[BillReportSpeakerRow]
    bill_stage_line_rows: list[BillStageLineRow]


def _build_stage_lines(
    session: Session,
    report_ids: list[int],
    report_id_to_sprs_report_id: dict[int, str],
) -> list[BillStageLine]:
    first_reading_rows = CRUDSpeech(
        session
    ).get_ordinal_transcript_rows_by_report_ids_and_kinds_and_transcript_regex_and_transcript_not_regexes(
        report_ids, _STAGE_LINE_KINDS, FIRST_READING_PATTERN, NOT_FIRST_READING_PATTERNS
    )
    second_reading_order_rows = CRUDSpeech(
        session
    ).get_ordinal_transcript_rows_by_report_ids_and_kinds_and_transcript_regex_and_transcript_not_regexes(
        report_ids, _STAGE_LINE_KINDS, SECOND_READING_PATTERN, ()
    )
    second_reading_agreed_rows = CRUDSpeech(
        session
    ).get_ordinal_transcript_rows_by_report_ids_and_kinds_and_transcript_regex_and_transcript_not_regexes(
        report_ids, _STAGE_LINE_KINDS, SECOND_READING_AGREED_PATTERN, ()
    )
    third_reading_rows = CRUDSpeech(
        session
    ).get_ordinal_transcript_rows_by_report_ids_and_kinds_and_transcript_regex_and_transcript_not_regexes(
        report_ids, _STAGE_LINE_KINDS, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
    )
    return [
        *build_bill_stage_lines(
            BillStage.FIRST_READING, first_reading_rows, report_id_to_sprs_report_id
        ),
        *build_bill_stage_lines(
            BillStage.SECOND_READING_ORDER,
            second_reading_order_rows,
            report_id_to_sprs_report_id,
        ),
        *build_bill_stage_lines(
            BillStage.SECOND_READING_AGREED,
            second_reading_agreed_rows,
            report_id_to_sprs_report_id,
        ),
        *build_bill_stage_lines(
            BillStage.THIRD_READING, third_reading_rows, report_id_to_sprs_report_id
        ),
    ]


def _build_planned_rows(
    session: Session, bill_report_rows: list[BillReportSittingDateReportTypeRow]
) -> _PlannedRows:
    bill_report_speakers: list[BillReportSpeaker] = []
    bill_stage_lines: list[BillStageLine] = []
    for start in range(0, len(bill_report_rows), _REPORT_BATCH):
        report_id_to_sprs_report_id = {
            bill_report_row.report_id: bill_report_row.sprs_report_id
            for bill_report_row in bill_report_rows[start : start + _REPORT_BATCH]
        }
        report_ids = list(report_id_to_sprs_report_id)
        bill_report_speakers.extend(
            build_bill_report_speakers(
                CRUDSpeech(
                    session
                ).get_ordinal_label_rows_by_report_ids_and_kind_and_speaker_id_not_null(
                    report_ids, SpeechKind.SPEECH
                ),
                report_id_to_sprs_report_id,
            )
        )
        bill_stage_lines.extend(
            _build_stage_lines(session, report_ids, report_id_to_sprs_report_id)
        )
    return _PlannedRows(bill_report_speakers, bill_stage_lines)


def _build_bill_keys(
    session: Session, bill_report_rows: list[BillReportSittingDateReportTypeRow]
) -> list[BillKey]:
    bill_id_to_act_ids: defaultdict[int, set[int]] = defaultdict(set)
    for act_history_entry_row in CRUDActHistoryEntry(session).get_rows():
        if act_history_entry_row.bill_id is not None:
            bill_id_to_act_ids[act_history_entry_row.bill_id].add(
                act_history_entry_row.act_id
            )
    bill_id_to_bill_report_rows: defaultdict[
        int, list[BillReportSittingDateReportTypeRow]
    ] = defaultdict(list)
    for bill_report_row in bill_report_rows:
        bill_id_to_bill_report_rows[bill_report_row.bill_id].append(bill_report_row)
    return [
        BillKey(
            act_count=len(bill_id_to_act_ids[bill_id]),
            bill_key=get_bill_key(bill_id, bill_id_to_bill_report_rows[bill_id]),
            bill_id=bill_id,
        )
        for bill_id in sorted(bill_id_to_bill_report_rows)
    ]


def get_bill_speaker_plan(session: Session) -> BillSpeakerPlan:
    bill_report_rows = CRUDBillReport(session).get_sitting_date_report_type_rows()
    planned_rows = _build_planned_rows(session, bill_report_rows)
    return BillSpeakerPlan(
        _build_bill_keys(session, bill_report_rows),
        planned_rows.bill_report_speakers,
        planned_rows.bill_stage_lines,
    )


def get_report_bill_speaker_plan(
    session: Session, report_ids: list[int]
) -> ReportBillSpeakerPlan:
    sprs_report_ids: list[str] = []
    bill_report_speakers: list[BillReportSpeaker] = []
    bill_stage_lines: list[BillStageLine] = []
    sorted_report_ids = sorted(report_ids)
    for start in range(0, len(sorted_report_ids), _REPORT_BATCH):
        batch_report_ids = sorted_report_ids[start : start + _REPORT_BATCH]
        sprs_report_ids.extend(
            report_placement_row.report_id
            for report_placement_row in CRUDReport(session).get_placement_rows_by_ids(
                batch_report_ids
            )
        )
        planned_rows = _build_planned_rows(
            session,
            CRUDBillReport(
                session
            ).get_sitting_date_report_type_rows_by_report_ids(batch_report_ids),
        )
        bill_report_speakers.extend(planned_rows.bill_report_speakers)
        bill_stage_lines.extend(planned_rows.bill_stage_lines)
    return ReportBillSpeakerPlan(
        sprs_report_ids, bill_report_speakers, bill_stage_lines
    )


def _get_group(bill_report_row: BillReportSittingDateReportTypeRow) -> str:
    decade = bill_report_row.sitting_date.year // _YEARS_PER_DECADE * _YEARS_PER_DECADE
    return f"{decade}s {bill_report_row.report_type}"


def get_bill_speaker_counts(
    session: Session,
    bill_report_speakers: Sequence[Union[BillReportSpeaker, BillReportSpeakerRow]],
    bill_stage_lines: Sequence[Union[BillStageLine, BillStageLineRow]],
) -> BillSpeakerCounts:
    sprs_report_id_to_group = {
        bill_report_row.sprs_report_id: _get_group(bill_report_row)
        for bill_report_row in CRUDBillReport(
            session
        ).get_sitting_date_report_type_rows()
    }
    return BillSpeakerCounts(
        Counter(
            sprs_report_id_to_group[bill_report_speaker.sprs_report_id]
            for bill_report_speaker in bill_report_speakers
        ),
        Counter(bill_stage_line.stage for bill_stage_line in bill_stage_lines),
    )


def _validate_can_commit_counts(
    planned_counts: BillSpeakerCounts, stored_counts: BillSpeakerCounts
) -> None:
    if (
        stored_counts.group_to_member_row_count
        != planned_counts.group_to_member_row_count
    ):
        raise HansardWriteCheckError(
            f"Stored bill report speakers by decade and report type {dict(stored_counts.group_to_member_row_count)}, the plan has {dict(planned_counts.group_to_member_row_count)}"
        )
    if stored_counts.stage_to_line_count != planned_counts.stage_to_line_count:
        raise HansardWriteCheckError(
            f"Stored bill stage lines by stage {dict(stored_counts.stage_to_line_count)}, the plan has {dict(planned_counts.stage_to_line_count)}"
        )


def _validate_can_commit_bill_keys(session: Session, plan: BillSpeakerPlan) -> None:
    bill_id_to_bill_report_rows: defaultdict[
        int, list[BillReportSittingDateReportTypeRow]
    ] = defaultdict(list)
    for bill_report_row in CRUDBillReport(
        session
    ).get_sitting_date_report_type_rows():
        bill_id_to_bill_report_rows[bill_report_row.bill_id].append(bill_report_row)
    stored_bill_key_rows = CRUDBillKey(session).get_rows()
    if len(stored_bill_key_rows) != len(plan.bill_keys):
        raise HansardWriteCheckError(
            f"Stored {len(stored_bill_key_rows)} bill keys, the plan has {len(plan.bill_keys)}"
        )
    if {
        stored_bill_key_row.bill_id for stored_bill_key_row in stored_bill_key_rows
    } != set(bill_id_to_bill_report_rows):
        raise HansardWriteCheckError("The stored bill keys do not cover every bill")
    bill_id_to_act_count = {
        bill_key.bill_id: bill_key.act_count for bill_key in plan.bill_keys
    }
    for stored_bill_key_row in stored_bill_key_rows:
        first_reading_sprs_report_id = get_bill_key(
            stored_bill_key_row.bill_id,
            bill_id_to_bill_report_rows[stored_bill_key_row.bill_id],
        )
        if stored_bill_key_row.bill_key != first_reading_sprs_report_id:
            raise HansardWriteCheckError(
                f"Bill {stored_bill_key_row.bill_id}: stored key {stored_bill_key_row.bill_key}, its first READING report is {first_reading_sprs_report_id}"
            )
        if (
            stored_bill_key_row.act_count
            != bill_id_to_act_count[stored_bill_key_row.bill_id]
        ):
            raise HansardWriteCheckError(
                f"Bill {stored_bill_key_row.bill_id}: stored Act count {stored_bill_key_row.act_count}, the plan has {bill_id_to_act_count[stored_bill_key_row.bill_id]}"
            )


def _validate_can_commit_bill_speaker_plan(
    session: Session, plan: BillSpeakerPlan
) -> None:
    _validate_can_commit_bill_keys(session, plan)
    _validate_can_commit_counts(
        get_bill_speaker_counts(
            session, plan.bill_report_speakers, plan.bill_stage_lines
        ),
        get_bill_speaker_counts(
            session,
            CRUDBillReportSpeaker(session).get_rows(),
            CRUDBillStageLine(session).get_rows(),
        ),
    )


def _get_stored_rows(session: Session, sprs_report_ids: list[str]) -> _StoredRows:
    bill_report_speaker_rows: list[BillReportSpeakerRow] = []
    bill_stage_line_rows: list[BillStageLineRow] = []
    for start in range(0, len(sprs_report_ids), _REPORT_BATCH):
        batch_sprs_report_ids = sprs_report_ids[start : start + _REPORT_BATCH]
        bill_report_speaker_rows.extend(
            CRUDBillReportSpeaker(session).get_rows_by_sprs_report_ids(
                batch_sprs_report_ids
            )
        )
        bill_stage_line_rows.extend(
            CRUDBillStageLine(session).get_rows_by_sprs_report_ids(
                batch_sprs_report_ids
            )
        )
    return _StoredRows(bill_report_speaker_rows, bill_stage_line_rows)


def _validate_can_commit_report_bill_speaker_plan(
    session: Session, plan: ReportBillSpeakerPlan
) -> None:
    stored_rows = _get_stored_rows(session, plan.sprs_report_ids)
    _validate_can_commit_counts(
        get_bill_speaker_counts(
            session, plan.bill_report_speakers, plan.bill_stage_lines
        ),
        get_bill_speaker_counts(
            session,
            stored_rows.bill_report_speaker_rows,
            stored_rows.bill_stage_line_rows,
        ),
    )


def write_bill_speaker_plan(session: Session, plan: BillSpeakerPlan) -> None:
    stored_bill_key_count = len(CRUDBillKey(session).get_rows())
    deleted_bill_key_count = CRUDBillKey(session).delete_all()
    if deleted_bill_key_count != stored_bill_key_count:
        raise HansardWriteCheckError(
            f"Deleted {deleted_bill_key_count} bill keys, read {stored_bill_key_count}"
        )
    stored_bill_report_speaker_count = len(CRUDBillReportSpeaker(session).get_rows())
    deleted_bill_report_speaker_count = CRUDBillReportSpeaker(session).delete_all()
    if deleted_bill_report_speaker_count != stored_bill_report_speaker_count:
        raise HansardWriteCheckError(
            f"Deleted {deleted_bill_report_speaker_count} bill report speakers, read {stored_bill_report_speaker_count}"
        )
    stored_bill_stage_line_count = len(CRUDBillStageLine(session).get_rows())
    deleted_bill_stage_line_count = CRUDBillStageLine(session).delete_all()
    if deleted_bill_stage_line_count != stored_bill_stage_line_count:
        raise HansardWriteCheckError(
            f"Deleted {deleted_bill_stage_line_count} bill stage lines, read {stored_bill_stage_line_count}"
        )
    CRUDBillKey(session).add_many(plan.bill_keys)
    CRUDBillReportSpeaker(session).add_many(plan.bill_report_speakers)
    CRUDBillStageLine(session).add_many(plan.bill_stage_lines)
    _validate_can_commit_bill_speaker_plan(session, plan)


def write_report_bill_speaker_plan(
    session: Session, plan: ReportBillSpeakerPlan
) -> None:
    for start in range(0, len(plan.sprs_report_ids), _REPORT_BATCH):
        batch_sprs_report_ids = plan.sprs_report_ids[start : start + _REPORT_BATCH]
        stored_bill_report_speaker_count = len(
            CRUDBillReportSpeaker(session).get_rows_by_sprs_report_ids(
                batch_sprs_report_ids
            )
        )
        deleted_bill_report_speaker_count = CRUDBillReportSpeaker(
            session
        ).delete_by_sprs_report_ids(batch_sprs_report_ids)
        if deleted_bill_report_speaker_count != stored_bill_report_speaker_count:
            raise HansardWriteCheckError(
                f"Deleted {deleted_bill_report_speaker_count} bill report speakers, read {stored_bill_report_speaker_count}"
            )
        stored_bill_stage_line_count = len(
            CRUDBillStageLine(session).get_rows_by_sprs_report_ids(
                batch_sprs_report_ids
            )
        )
        deleted_bill_stage_line_count = CRUDBillStageLine(
            session
        ).delete_by_sprs_report_ids(batch_sprs_report_ids)
        if deleted_bill_stage_line_count != stored_bill_stage_line_count:
            raise HansardWriteCheckError(
                f"Deleted {deleted_bill_stage_line_count} bill stage lines, read {stored_bill_stage_line_count}"
            )
    CRUDBillReportSpeaker(session).add_many(plan.bill_report_speakers)
    CRUDBillStageLine(session).add_many(plan.bill_stage_lines)
    _validate_can_commit_report_bill_speaker_plan(session, plan)


def get_matching_report_ids(
    session: Session,
    report_ids: list[int],
    pattern: str,
    not_patterns: tuple[str, ...],
) -> frozenset[int]:
    return frozenset(
        CRUDSpeech(
            session
        ).get_report_ids_by_report_ids_and_transcript_regex_and_transcript_not_regexes(
            report_ids, pattern, not_patterns
        )
    )


def _get_bill_report_rows(
    session: Session,
    report_ids: list[int],
    first_reading_report_ids: frozenset[int],
    third_reading_report_ids: frozenset[int],
) -> list[ReportPlacementRow]:
    second_reading_report_ids = get_matching_report_ids(
        session, report_ids, SECOND_READING_PATTERN, ()
    )
    return [
        report_row
        for report_row in CRUDReport(session).get_placement_rows_by_ids(report_ids)
        if report_row.report_type in _BILL_REPORT_TYPES
        or is_other_type_bill_reading(
            report_row.title,
            report_row.id in first_reading_report_ids,
            report_row.id in second_reading_report_ids,
            report_row.id in third_reading_report_ids,
        )
    ]


def _get_bill_placement(session: Session, report_ids: list[int]) -> BillPlacement:
    first_reading_report_ids = get_matching_report_ids(
        session, report_ids, FIRST_READING_PATTERN, NOT_FIRST_READING_PATTERNS
    )
    third_reading_report_ids = get_matching_report_ids(
        session, report_ids, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
    )
    report_rows = _get_bill_report_rows(
        session, report_ids, first_reading_report_ids, third_reading_report_ids
    )
    stored_bill_rows = CRUDBill(session).get_rows_by_title_keys(
        sorted({get_title_key(report_row.title) for report_row in report_rows})
    )
    bill_id_to_bill_key = {
        bill_key_row.bill_id: bill_key_row.bill_key
        for bill_key_row in CRUDBillKey(session).get_rows_by_bill_ids(
            [stored_bill_row.id for stored_bill_row in stored_bill_rows]
        )
    }
    return place_bill_reports(
        report_rows,
        first_reading_report_ids,
        third_reading_report_ids,
        stored_bill_rows,
        bill_id_to_bill_key,
    )


def _write_bill_placement(session: Session, bill_placement: BillPlacement) -> list[int]:
    new_bills: list[Bill] = []
    new_report_rows_by_bill: list[list[ReportPlacementRow]] = []
    bill_join_updates: list[BillJoinUpdate] = []
    joined_bill_reports: list[BillReport] = []
    for placed_bill in bill_placement.placed_bills:
        if placed_bill.bill_id is None:
            new_bills.append(
                Bill(
                    title=placed_bill.title,
                    title_key=placed_bill.title_key,
                    first_sitting_date=placed_bill.first_sitting_date,
                    last_sitting_date=placed_bill.last_sitting_date,
                    is_passed=placed_bill.is_passed,
                    bill_class=get_bill_class(placed_bill.title_key),
                )
            )
            new_report_rows_by_bill.append(placed_bill.report_rows)
            continue
        bill_join_updates.append(
            BillJoinUpdate(
                placed_bill.bill_id,
                placed_bill.title,
                placed_bill.last_sitting_date,
                placed_bill.is_passed,
            )
        )
        joined_bill_reports.extend(
            BillReport(
                role=BillReportRole.READING,
                bill_id=placed_bill.bill_id,
                report_id=report_row.id,
            )
            for report_row in placed_bill.report_rows
        )
    CRUDBill(session).add_many(new_bills)
    CRUDBill(session).update_title_and_last_sitting_date_and_is_passed_many(
        bill_join_updates
    )
    new_bill_reports: list[BillReport] = []
    bill_keys: list[BillKey] = []
    for new_bill, report_rows in zip(new_bills, new_report_rows_by_bill, strict=True):
        if new_bill.id is None:
            continue
        new_bill_reports.extend(
            BillReport(
                role=BillReportRole.READING,
                bill_id=new_bill.id,
                report_id=report_row.id,
            )
            for report_row in report_rows
        )
        bill_keys.append(
            BillKey(
                act_count=0,
                bill_key=get_bill_key(
                    new_bill.id,
                    [
                        BillReportSittingDateReportTypeRow(
                            new_bill.id,
                            report_row.id,
                            report_row.report_id,
                            report_row.sitting_date,
                            report_row.report_type,
                            BillReportRole.READING,
                        )
                        for report_row in report_rows
                    ],
                ),
                bill_id=new_bill.id,
            )
        )
    CRUDBillReport(session).add_many(joined_bill_reports + new_bill_reports)
    CRUDBillKey(session).add_many(bill_keys)
    return [
        report_row.id
        for placed_bill in bill_placement.placed_bills
        for report_row in placed_bill.report_rows
    ]


# NOTE: inserts and a three-column update only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_bill_speakers(session: Session, report_ids: list[int]) -> None:
    placed_report_ids = {
        bill_report_row.report_id
        for bill_report_row in CRUDBillReport(
            session
        ).get_sitting_date_report_type_rows_by_report_ids(report_ids)
    }
    bill_placement = _get_bill_placement(
        session,
        [report_id for report_id in report_ids if report_id not in placed_report_ids],
    )
    for left_out_report in bill_placement.left_out_reports:
        logger.info(
            f"Bill report {left_out_report.report_row.report_id} left out: {left_out_report.reason}"
        )
    newly_placed_report_ids = _write_bill_placement(session, bill_placement)
    report_bill_speaker_plan = get_report_bill_speaker_plan(
        session, newly_placed_report_ids
    )
    CRUDBillReportSpeaker(session).add_many(
        report_bill_speaker_plan.bill_report_speakers
    )
    CRUDBillStageLine(session).add_many(report_bill_speaker_plan.bill_stage_lines)
    started_bill_count = len(
        [
            placed_bill
            for placed_bill in bill_placement.placed_bills
            if placed_bill.bill_id is None
        ]
    )
    logger.info(
        f"Bills: placed {len(newly_placed_report_ids)} reports, started {started_bill_count} bills, left out {len(bill_placement.left_out_reports)} reports, added {len(report_bill_speaker_plan.bill_report_speakers)} members and {len(report_bill_speaker_plan.bill_stage_lines)} stage lines"
    )

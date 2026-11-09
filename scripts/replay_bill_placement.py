import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from unittest.mock import patch

from sqlmodel import Session

import services.bill as bill_service
from crud.bill import BillRow, CRUDBill
from crud.bill_key import CRUDBillKey
from crud.bill_report import BillReportSittingDateReportTypeRow, CRUDBillReport
from crud.report import CRUDReport, ReportPlacementRow
from database.init import build_read_only_engine
from enums import (
    BillLeftOutReason,
    BillReplayDifferenceKind,
    BillReportRole,
    ReportType,
)
from logs import logger
from populate.bill_speakers import get_matching_report_ids
from services.bill import (
    BILL_TITLE_END_PATTERN,
    FIRST_READING_PATTERN,
    NOT_FIRST_READING_PATTERNS,
    NOT_THIRD_READING_PATTERNS,
    SECOND_READING_PATTERN,
    THIRD_READING_PATTERN,
    BillPlacement,
    is_other_type_bill_reading,
    place_bill_reports,
    should_start_new_bill,
)
from settings import settings
from utils.data_files import get_bill_title_corrections, get_hand_kept_bills
from utils.title_key import get_title_key

_BILL_REPORT_TYPES = (ReportType.BILL, ReportType.BILL_INTRODUCTION)
_REPLAYED_REPORT_COUNT = 300
_READ_ISOLATION_LEVEL = "REPEATABLE READ"


@dataclass(frozen=True)
class BillReplayDifference:
    sprs_report_id: str
    title: str
    kind: BillReplayDifferenceKind


@dataclass(frozen=True)
class BillReplay:
    replayed_report_count: int
    placed_report_count: int
    left_out_reason_to_report_count: dict[BillLeftOutReason, int]
    explained_differences: list[BillReplayDifference]
    listed_differences: list[BillReplayDifference]


@dataclass(frozen=True)
class _StoredBills:
    report_id_to_bill_id: dict[int, int]
    bill_id_to_report_ids: dict[int, frozenset[int]]


def _get_candidate_rows(session: Session) -> list[ReportPlacementRow]:
    bill_type_rows = CRUDReport(session).get_placement_rows_by_report_types(
        _BILL_REPORT_TYPES
    )
    other_type_rows = CRUDReport(
        session
    ).get_placement_rows_by_report_types_not_in_and_title_regex(
        _BILL_REPORT_TYPES, BILL_TITLE_END_PATTERN
    )
    other_report_ids = [report_row.id for report_row in other_type_rows]
    first_reading_report_ids = get_matching_report_ids(
        session, other_report_ids, FIRST_READING_PATTERN, NOT_FIRST_READING_PATTERNS
    )
    second_reading_report_ids = get_matching_report_ids(
        session, other_report_ids, SECOND_READING_PATTERN, ()
    )
    third_reading_report_ids = get_matching_report_ids(
        session, other_report_ids, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
    )
    return sorted(
        bill_type_rows
        + [
            report_row
            for report_row in other_type_rows
            if is_other_type_bill_reading(
                report_row.title,
                report_row.id in first_reading_report_ids,
                report_row.id in second_reading_report_ids,
                report_row.id in third_reading_report_ids,
            )
        ],
        key=lambda report_row: (report_row.sitting_date, report_row.id),
    )


def _build_bill_rows_before_replay(
    session: Session,
    stored_bill_rows: list[BillRow],
    bill_id_to_reading_rows: dict[int, list[BillReportSittingDateReportTypeRow]],
    replayed_report_ids: frozenset[int],
) -> list[BillRow]:
    bill_rows_before_replay: list[BillRow] = []
    for stored_bill_row in stored_bill_rows:
        kept_rows = [
            reading_row
            for reading_row in bill_id_to_reading_rows.get(stored_bill_row.id, [])
            if reading_row.report_id not in replayed_report_ids
        ]
        if not kept_rows:
            continue
        third_reading_report_ids = get_matching_report_ids(
            session,
            [kept_row.report_id for kept_row in kept_rows],
            THIRD_READING_PATTERN,
            NOT_THIRD_READING_PATTERNS,
        )
        bill_rows_before_replay.append(
            replace(
                stored_bill_row,
                first_sitting_date=min(kept_row.sitting_date for kept_row in kept_rows),
                last_sitting_date=max(kept_row.sitting_date for kept_row in kept_rows),
                is_passed=bool(third_reading_report_ids),
            )
        )
    return bill_rows_before_replay


def _should_start_new_bill_against_the_rule(
    is_passed: bool,
    last_sitting_date: datetime,
    sitting_date: datetime,
    is_first_reading: bool,
) -> bool:
    return not should_start_new_bill(
        is_passed, last_sitting_date, sitting_date, is_first_reading
    )


def _place_replayed_reports(
    is_flip_start_new_bill: bool,
    report_rows: list[ReportPlacementRow],
    first_reading_report_ids: frozenset[int],
    third_reading_report_ids: frozenset[int],
    stored_bill_rows: list[BillRow],
    bill_id_to_bill_key: dict[int, str],
) -> BillPlacement:
    if not is_flip_start_new_bill:
        return place_bill_reports(
            report_rows,
            first_reading_report_ids,
            third_reading_report_ids,
            stored_bill_rows,
            bill_id_to_bill_key,
        )
    with patch.object(
        bill_service,
        "should_start_new_bill",
        _should_start_new_bill_against_the_rule,
    ):
        return place_bill_reports(
            report_rows,
            first_reading_report_ids,
            third_reading_report_ids,
            stored_bill_rows,
            bill_id_to_bill_key,
        )


def _get_differences(
    bill_placement: BillPlacement,
    bill_id_to_kept_report_ids: dict[int, frozenset[int]],
    stored_bills: _StoredBills,
) -> list[BillReplayDifference]:
    hand_kept_report_id_sets = [
        frozenset(hand_kept_bill.report_ids) for hand_kept_bill in get_hand_kept_bills()
    ]
    corrected_report_ids = frozenset(
        title_correction.report_id for title_correction in get_bill_title_corrections()
    )
    differences: list[BillReplayDifference] = []
    for left_out_report in bill_placement.left_out_reports:
        report_row = left_out_report.report_row
        if report_row.id in stored_bills.report_id_to_bill_id:
            differences.append(
                BillReplayDifference(
                    report_row.report_id,
                    report_row.title,
                    BillReplayDifferenceKind.LEFT_OUT_BY_RULE,
                )
            )
    for placed_bill in bill_placement.placed_bills:
        kept_report_ids = (
            frozenset()
            if placed_bill.bill_id is None
            else bill_id_to_kept_report_ids.get(placed_bill.bill_id, frozenset())
        )
        replayed_report_id_set = (
            frozenset(report_row.id for report_row in placed_bill.report_rows)
            | kept_report_ids
        )
        for report_row in placed_bill.report_rows:
            stored_bill_id = stored_bills.report_id_to_bill_id.get(report_row.id)
            if stored_bill_id is None:
                kind = BillReplayDifferenceKind.PLACED_BUT_NOT_STORED
            else:
                stored_report_id_set = stored_bills.bill_id_to_report_ids[
                    stored_bill_id
                ]
                if stored_report_id_set == replayed_report_id_set:
                    continue
                if any(
                    hand_kept_report_id_set
                    & (stored_report_id_set | replayed_report_id_set)
                    for hand_kept_report_id_set in hand_kept_report_id_sets
                ):
                    kind = BillReplayDifferenceKind.HAND_KEPT_BILL
                elif corrected_report_ids & (
                    stored_report_id_set | replayed_report_id_set
                ):
                    kind = BillReplayDifferenceKind.TITLE_CORRECTION
                else:
                    kind = BillReplayDifferenceKind.DIFFERENT_BILL
            differences.append(
                BillReplayDifference(report_row.report_id, report_row.title, kind)
            )
    return differences


def get_bill_replay(session: Session, is_flip_start_new_bill: bool) -> BillReplay:
    replayed_rows = _get_candidate_rows(session)[-_REPLAYED_REPORT_COUNT:]
    replayed_report_ids = [report_row.id for report_row in replayed_rows]
    replayed_report_id_set = frozenset(replayed_report_ids)
    first_reading_report_ids = get_matching_report_ids(
        session, replayed_report_ids, FIRST_READING_PATTERN, NOT_FIRST_READING_PATTERNS
    )
    third_reading_report_ids = get_matching_report_ids(
        session, replayed_report_ids, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
    )
    stored_bill_rows = CRUDBill(session).get_rows_by_title_keys(
        sorted({get_title_key(report_row.title) for report_row in replayed_rows})
    )
    bill_id_to_reading_rows: defaultdict[
        int, list[BillReportSittingDateReportTypeRow]
    ] = defaultdict(list)
    report_id_to_bill_id: dict[int, int] = {}
    for bill_report_row in CRUDBillReport(session).get_sitting_date_report_type_rows():
        if bill_report_row.role != BillReportRole.READING:
            continue
        bill_id_to_reading_rows[bill_report_row.bill_id].append(bill_report_row)
        report_id_to_bill_id[bill_report_row.report_id] = bill_report_row.bill_id
    stored_bills = _StoredBills(
        report_id_to_bill_id,
        {
            bill_id: frozenset(reading_row.report_id for reading_row in reading_rows)
            for bill_id, reading_rows in bill_id_to_reading_rows.items()
        },
    )
    bill_rows_before_replay = _build_bill_rows_before_replay(
        session,
        stored_bill_rows,
        bill_id_to_reading_rows,
        replayed_report_id_set,
    )
    bill_id_to_kept_report_ids = {
        bill_row.id: frozenset(
            reading_row.report_id
            for reading_row in bill_id_to_reading_rows[bill_row.id]
            if reading_row.report_id not in replayed_report_id_set
        )
        for bill_row in bill_rows_before_replay
    }
    bill_id_to_bill_key = {
        bill_key_row.bill_id: bill_key_row.bill_key
        for bill_key_row in CRUDBillKey(session).get_rows_by_bill_ids(
            [bill_row.id for bill_row in bill_rows_before_replay]
        )
    }
    bill_placement = _place_replayed_reports(
        is_flip_start_new_bill,
        replayed_rows,
        first_reading_report_ids,
        third_reading_report_ids,
        bill_rows_before_replay,
        bill_id_to_bill_key,
    )
    differences = _get_differences(
        bill_placement,
        bill_id_to_kept_report_ids,
        stored_bills,
    )
    return BillReplay(
        len(replayed_rows),
        sum(
            len(placed_bill.report_rows) for placed_bill in bill_placement.placed_bills
        ),
        dict(
            Counter(
                left_out_report.reason
                for left_out_report in bill_placement.left_out_reports
            )
        ),
        [
            difference
            for difference in differences
            if difference.kind != BillReplayDifferenceKind.PLACED_BUT_NOT_STORED
            and difference.kind != BillReplayDifferenceKind.DIFFERENT_BILL
        ],
        [
            difference
            for difference in differences
            if difference.kind == BillReplayDifferenceKind.PLACED_BUT_NOT_STORED
            or difference.kind == BillReplayDifferenceKind.DIFFERENT_BILL
        ],
    )


def replay_bill_placement(is_flip_start_new_bill: bool) -> None:
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_READ_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        bill_replay = get_bill_replay(session, is_flip_start_new_bill)
    logger.info(
        f"Replayed {bill_replay.replayed_report_count:,} reports: placed {bill_replay.placed_report_count:,}, left out {sum(bill_replay.left_out_reason_to_report_count.values()):,} ({dict(bill_replay.left_out_reason_to_report_count)}), {len(bill_replay.explained_differences):,} explained differences, {len(bill_replay.listed_differences):,} listed differences"
    )
    for difference in bill_replay.listed_differences:
        logger.info(
            f"{difference.kind}: {difference.sprs_report_id} {difference.title}"
        )
    logger.info("Nothing written")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Place the latest 300 Bill reports against the Bills stored before them with the daily rule and compare with billreport, read only"
    )
    parser.add_argument(
        "--flip-start-new-bill",
        action="store_true",
        help="invert the start-a-new-Bill test for this run, the known-bad case that must list differences before a clean replay counts",
    )
    arguments = parser.parse_args()
    replay_bill_placement(arguments.flip_start_new_bill)

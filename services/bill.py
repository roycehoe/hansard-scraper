import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from crud.report import ReportSittingDateTitleRow
from exceptions import HansardHandKeptEntryError
from schemas.bill_title_correction import BillTitleCorrection
from schemas.hand_kept_bill import HandKeptBill
from utils.title_key import get_title_key

FIRST_READING_PATTERN = r"\yread (a|the|for the) first time"
NOT_FIRST_READING_PATTERNS = (
    "brought up",
    r"\y(was|were|been|is)\y[^.;]{0,40}\yread (a|the|for the) first time",
)
THIRD_READING_PATTERN = r'^\W*[^"]{0,150}\ybill\y[^"]{0,120}\yread (a|the) third time'
NOT_THIRD_READING_PATTERNS = ("be now read", r"^\W*(I|now|sir|mr)\y")

_MAX_DAYS_BETWEEN_REPORTS = 366
_BILL_WORD_PATTERN = re.compile(r"\bbill\b", re.IGNORECASE)


@dataclass(frozen=True)
class BillGroup:
    title: str
    title_key: str
    first_sitting_date: datetime
    last_sitting_date: datetime
    is_passed: bool
    report_ids: list[int]


@dataclass(frozen=True)
class BillGrouping:
    bill_groups: list[BillGroup]
    skipped_report_rows: list[ReportSittingDateTitleRow]


@dataclass
class _OpenBill:
    title: str
    title_key: str
    first_sitting_date: datetime
    last_sitting_date: datetime
    is_passed: bool
    report_ids: list[int]


def _should_start_new_bill(
    open_bill: _OpenBill, sitting_date: datetime, is_first_reading: bool
) -> bool:
    if (
        open_bill.is_passed or is_first_reading
    ) and sitting_date > open_bill.last_sitting_date:
        return True
    return sitting_date - open_bill.last_sitting_date > timedelta(
        days=_MAX_DAYS_BETWEEN_REPORTS
    )


def _build_bill_group(open_bill: _OpenBill) -> BillGroup:
    return BillGroup(
        open_bill.title,
        open_bill.title_key,
        open_bill.first_sitting_date,
        open_bill.last_sitting_date,
        open_bill.is_passed,
        open_bill.report_ids,
    )


def _build_corrected_report_rows(
    report_rows: list[ReportSittingDateTitleRow],
    title_corrections: list[BillTitleCorrection],
) -> list[ReportSittingDateTitleRow]:
    report_id_to_title = {report_row.id: report_row.title for report_row in report_rows}
    report_id_to_corrected_title: dict[int, str] = {}
    for title_correction in title_corrections:
        printed_title = report_id_to_title.get(title_correction.report_id)
        if printed_title is None:
            raise HansardHandKeptEntryError(
                f"bill_title_corrections.json: report {title_correction.report_id} "
                "is not a bill report"
            )
        if printed_title != title_correction.printed_title:
            raise HansardHandKeptEntryError(
                f"bill_title_corrections.json: report {title_correction.report_id} "
                f"prints {printed_title!r}, not {title_correction.printed_title!r}"
            )
        report_id_to_corrected_title[title_correction.report_id] = (
            title_correction.corrected_title
        )
    return [
        ReportSittingDateTitleRow(
            report_row.id,
            report_row.sitting_date,
            report_id_to_corrected_title.get(report_row.id, report_row.title),
        )
        for report_row in report_rows
    ]


def _build_hand_kept_bill_group(
    hand_kept_bill: HandKeptBill,
    report_id_to_row: dict[int, ReportSittingDateTitleRow],
    third_reading_report_ids: frozenset[int],
) -> BillGroup:
    hand_kept_rows: list[ReportSittingDateTitleRow] = []
    for report_id in hand_kept_bill.report_ids:
        report_row = report_id_to_row.get(report_id)
        if report_row is None:
            raise HansardHandKeptEntryError(
                f"hand_kept_bills.json: {hand_kept_bill.title!r} lists report "
                f"{report_id}, which is not stored"
            )
        hand_kept_rows.append(report_row)
    hand_kept_rows.sort(key=lambda report_row: (report_row.sitting_date, report_row.id))
    return BillGroup(
        hand_kept_bill.title,
        get_title_key(hand_kept_bill.title),
        hand_kept_rows[0].sitting_date,
        hand_kept_rows[-1].sitting_date,
        any(report_row.id in third_reading_report_ids for report_row in hand_kept_rows),
        [report_row.id for report_row in hand_kept_rows],
    )


def _validate_can_replace_bill_groups(
    hand_kept_bill: HandKeptBill, bill_groups: list[BillGroup]
) -> None:
    hand_kept_report_ids = set(hand_kept_bill.report_ids)
    for bill_group in bill_groups:
        group_report_ids = set(bill_group.report_ids)
        if group_report_ids & hand_kept_report_ids and not (
            group_report_ids <= hand_kept_report_ids
        ):
            raise HansardHandKeptEntryError(
                f"hand_kept_bills.json: {hand_kept_bill.title!r} splits the bill "
                f"{bill_group.title!r} of reports {bill_group.report_ids}"
            )


def group_bills(
    report_rows: list[ReportSittingDateTitleRow],
    first_reading_report_ids: frozenset[int],
    third_reading_report_ids: frozenset[int],
    title_corrections: list[BillTitleCorrection],
    hand_kept_bills: list[HandKeptBill],
    hand_kept_report_rows: list[ReportSittingDateTitleRow],
) -> BillGrouping:
    title_key_to_open_bill: dict[str, _OpenBill] = {}
    bill_groups: list[BillGroup] = []
    skipped_report_rows: list[ReportSittingDateTitleRow] = []
    for report_row in _build_corrected_report_rows(report_rows, title_corrections):
        if _BILL_WORD_PATTERN.search(report_row.title) is None:
            skipped_report_rows.append(report_row)
            continue
        title_key = get_title_key(report_row.title)
        previous_bill = title_key_to_open_bill.get(title_key)
        if previous_bill is not None and _should_start_new_bill(
            previous_bill,
            report_row.sitting_date,
            report_row.id in first_reading_report_ids,
        ):
            bill_groups.append(_build_bill_group(previous_bill))
            del title_key_to_open_bill[title_key]
        open_bill = title_key_to_open_bill.setdefault(
            title_key,
            _OpenBill(
                report_row.title,
                title_key,
                report_row.sitting_date,
                report_row.sitting_date,
                False,
                [],
            ),
        )
        open_bill.title = report_row.title
        open_bill.last_sitting_date = report_row.sitting_date
        open_bill.is_passed = (
            open_bill.is_passed or report_row.id in third_reading_report_ids
        )
        open_bill.report_ids.append(report_row.id)
    bill_groups.extend(
        _build_bill_group(open_bill) for open_bill in title_key_to_open_bill.values()
    )
    report_id_to_row = {
        report_row.id: report_row for report_row in hand_kept_report_rows
    }
    hand_kept_report_ids = {
        report_id
        for hand_kept_bill in hand_kept_bills
        for report_id in hand_kept_bill.report_ids
    }
    for hand_kept_bill in hand_kept_bills:
        _validate_can_replace_bill_groups(hand_kept_bill, bill_groups)
    hand_kept_groups = [
        _build_hand_kept_bill_group(
            hand_kept_bill, report_id_to_row, third_reading_report_ids
        )
        for hand_kept_bill in hand_kept_bills
    ]
    bill_groups = [
        bill_group
        for bill_group in bill_groups
        if hand_kept_report_ids.isdisjoint(bill_group.report_ids)
    ] + hand_kept_groups
    skipped_report_rows = [
        report_row
        for report_row in skipped_report_rows
        if report_row.id not in hand_kept_report_ids
    ]
    return BillGrouping(
        sorted(
            bill_groups,
            key=lambda bill_group: (
                bill_group.first_sitting_date,
                bill_group.report_ids[0],
            ),
        ),
        skipped_report_rows,
    )

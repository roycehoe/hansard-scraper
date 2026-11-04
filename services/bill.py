import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from crud.report import ReportSittingDateTitleRow

THIRD_READING_PATTERN = r'^\W*[^"]{0,150}\ybill\y[^"]{0,120}\yread (a|the) third time'
NOT_THIRD_READING_PATTERNS = ("be now read", r"^\W*(I|now|sir|mr)\y")

_MAX_DAYS_BETWEEN_REPORTS = 366
_BILL_WORD_PATTERN = re.compile(r"\bbill\b", re.IGNORECASE)
_NON_KEY_PATTERN = re.compile(r"[\W_]+")


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


def get_title_key(title: str) -> str:
    return _NON_KEY_PATTERN.sub("", title.lower())


def _should_start_new_bill(open_bill: _OpenBill, sitting_date: datetime) -> bool:
    if open_bill.is_passed and sitting_date > open_bill.last_sitting_date:
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


def group_bills(
    report_rows: list[ReportSittingDateTitleRow],
    third_reading_report_ids: frozenset[int],
) -> BillGrouping:
    title_key_to_open_bill: dict[str, _OpenBill] = {}
    bill_groups: list[BillGroup] = []
    skipped_report_rows: list[ReportSittingDateTitleRow] = []
    for report_row in report_rows:
        if _BILL_WORD_PATTERN.search(report_row.title) is None:
            skipped_report_rows.append(report_row)
            continue
        title_key = get_title_key(report_row.title)
        previous_bill = title_key_to_open_bill.get(title_key)
        if previous_bill is not None and _should_start_new_bill(
            previous_bill, report_row.sitting_date
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

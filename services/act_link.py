import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from enums import BillLinkSource
from utils.title_key import get_title_key

_MAX_DAYS_FROM_READING = 1
_TRAILING_YEAR = re.compile(r"[,\s]*\d{4}\s*$")
_TRAILING_LAW_WORD = re.compile(r"\s*\b(?:Act|Ordinance)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class LinkableBill:
    bill_index: int
    report_dates: list[date]


@dataclass(frozen=True)
class BillLink:
    bill_index: int
    source: BillLinkSource


@dataclass(frozen=True, order=True)
class _CloseBill:
    gap_days: int
    bill_index: int


def get_bill_title_key(printed_title: str) -> str:
    without_year = _TRAILING_YEAR.sub("", printed_title)
    if _TRAILING_LAW_WORD.search(without_year) is None:
        return get_title_key(f"{without_year} Bill")
    return get_title_key(_TRAILING_LAW_WORD.sub(" Bill", without_year))


def _get_nearest_bill_index(
    reading_date: Optional[date], linkable_bills: list[LinkableBill]
) -> Optional[int]:
    if reading_date is None:
        return None
    close_bills = [
        _CloseBill(gap_days, bill.bill_index)
        for bill in linkable_bills
        if (
            gap_days := min(
                abs((report_date - reading_date).days)
                for report_date in bill.report_dates
            )
        )
        <= _MAX_DAYS_FROM_READING
    ]
    if len(close_bills) == 0:
        return None
    return min(close_bills).bill_index


def get_bill_link(
    printed_title: str,
    first_reading_date: Optional[date],
    second_reading_date: Optional[date],
    third_reading_date: Optional[date],
    title_key_to_linkable_bills: dict[str, list[LinkableBill]],
) -> Optional[BillLink]:
    linkable_bills = title_key_to_linkable_bills.get(get_bill_title_key(printed_title))
    if linkable_bills is None:
        return None
    for source, reading_date in (
        (BillLinkSource.FIRST_READING_DATE, first_reading_date),
        (BillLinkSource.THIRD_READING_DATE, third_reading_date),
        (BillLinkSource.SECOND_READING_DATE, second_reading_date),
    ):
        bill_index = _get_nearest_bill_index(reading_date, linkable_bills)
        if bill_index is not None:
            return BillLink(bill_index, source)
    return None

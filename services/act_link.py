import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from enums import BillLinkSource
from utils.title_key import get_title_key

_MAX_DAYS_FROM_READING = 1
_LEADING_THE = re.compile(r"^The\s+")
_THE_KEY_PREFIX = "the"
_TRAILING_CHAPTER = re.compile(r"\s*\(Chapter\s+[A-Za-z0-9]+\)\s*$")
_TRAILING_YEAR = re.compile(r"[,\s]*\d{4}\s*$")
_TRAILING_LAW_WORD = re.compile(r"\s*\b(?:Act|Ordinance)\s*$", re.IGNORECASE)
_AMENDMENT_OR_NUMBER_KEY_PART = re.compile(r"amendment(?!s)(?:no\d+)?|no\d+")


@dataclass(frozen=True)
class LinkableBill:
    bill_index: int
    report_dates: list[date]


@dataclass(frozen=True)
class BillLookups:
    title_key_to_linkable_bills: dict[str, list[LinkableBill]]
    loose_title_key_to_linkable_bills: dict[str, list[LinkableBill]]


@dataclass(frozen=True)
class BillLink:
    bill_index: int
    source: BillLinkSource


@dataclass(frozen=True, order=True)
class _CloseBill:
    gap_days: int
    bill_index: int


def get_bill_title_key(printed_title: str) -> str:
    without_the = _LEADING_THE.sub("", printed_title)
    without_chapter = _TRAILING_CHAPTER.sub("", without_the)
    without_year = _TRAILING_YEAR.sub("", without_chapter)
    if _TRAILING_LAW_WORD.search(without_year) is None:
        return get_title_key(f"{without_year} Bill")
    return get_title_key(_TRAILING_LAW_WORD.sub(" Bill", without_year))


def get_loose_title_key(title_key: str) -> str:
    return _AMENDMENT_OR_NUMBER_KEY_PART.sub("", title_key)


def build_bill_lookups(
    title_key_to_linkable_bills: dict[str, list[LinkableBill]],
) -> BillLookups:
    loose_title_key_to_linkable_bills: dict[str, list[LinkableBill]] = {}
    for title_key, linkable_bills in title_key_to_linkable_bills.items():
        loose_title_key_to_linkable_bills.setdefault(
            get_loose_title_key(title_key), []
        ).extend(linkable_bills)
    return BillLookups(title_key_to_linkable_bills, loose_title_key_to_linkable_bills)


def _is_near_reading(reading_date: date, linkable_bill: LinkableBill) -> bool:
    return any(
        abs((report_date - reading_date).days) <= _MAX_DAYS_FROM_READING
        for report_date in linkable_bill.report_dates
    )


def _get_loose_bill_index(
    first_reading_date: Optional[date],
    third_reading_date: Optional[date],
    linkable_bills: list[LinkableBill],
) -> Optional[int]:
    anchor_date = (
        first_reading_date if first_reading_date is not None else third_reading_date
    )
    if anchor_date is None:
        return None
    close_bill_indexes = [
        linkable_bill.bill_index
        for linkable_bill in linkable_bills
        if _is_near_reading(anchor_date, linkable_bill)
        and (
            first_reading_date is None
            or third_reading_date is None
            or _is_near_reading(third_reading_date, linkable_bill)
        )
    ]
    if len(close_bill_indexes) != 1:
        return None
    return close_bill_indexes[0]


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


def _get_bill_link_by_title_key(
    title_key: str,
    first_reading_date: Optional[date],
    second_reading_date: Optional[date],
    third_reading_date: Optional[date],
    bill_lookups: BillLookups,
) -> Optional[BillLink]:
    linkable_bills = bill_lookups.title_key_to_linkable_bills.get(title_key)
    if linkable_bills is not None:
        for source, reading_date in (
            (BillLinkSource.FIRST_READING_DATE, first_reading_date),
            (BillLinkSource.THIRD_READING_DATE, third_reading_date),
            (BillLinkSource.SECOND_READING_DATE, second_reading_date),
        ):
            bill_index = _get_nearest_bill_index(reading_date, linkable_bills)
            if bill_index is not None:
                return BillLink(bill_index, source)
    loose_linkable_bills = bill_lookups.loose_title_key_to_linkable_bills.get(
        get_loose_title_key(title_key)
    )
    if loose_linkable_bills is None:
        return None
    loose_bill_index = _get_loose_bill_index(
        first_reading_date, third_reading_date, loose_linkable_bills
    )
    if loose_bill_index is None:
        return None
    return BillLink(loose_bill_index, BillLinkSource.LOOSE_TITLE_READING_DATES)


def get_bill_link(
    printed_title: str,
    first_reading_date: Optional[date],
    second_reading_date: Optional[date],
    third_reading_date: Optional[date],
    bill_lookups: BillLookups,
) -> Optional[BillLink]:
    title_key = get_bill_title_key(printed_title)
    if _LEADING_THE.match(printed_title) is None:
        return _get_bill_link_by_title_key(
            title_key,
            first_reading_date,
            second_reading_date,
            third_reading_date,
            bill_lookups,
        )
    bill_link = _get_bill_link_by_title_key(
        f"{_THE_KEY_PREFIX}{title_key}",
        first_reading_date,
        second_reading_date,
        third_reading_date,
        bill_lookups,
    )
    if bill_link is not None:
        return bill_link
    return _get_bill_link_by_title_key(
        title_key,
        first_reading_date,
        second_reading_date,
        third_reading_date,
        bill_lookups,
    )

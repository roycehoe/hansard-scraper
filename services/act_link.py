from dataclasses import dataclass
from datetime import date
from typing import Optional

from enums import BillLinkSource
from exceptions import HansardHandKeptEntryError
from schemas.hand_kept_act_link import HandKeptActLink
from utils.bill_number import normalize_bill_number
from utils.title_key import (
    get_bill_title_key,
    get_loose_title_key,
    is_leading_the_title,
)

_MAX_DAYS_FROM_READING = 1
_THE_KEY_PREFIX = "the"


@dataclass(frozen=True)
class LinkableBill:
    bill_index: int
    report_dates: list[date]


@dataclass(frozen=True)
class BillLookups:
    title_key_to_linkable_bills: dict[str, list[LinkableBill]]
    loose_title_key_to_linkable_bills: dict[str, list[LinkableBill]]
    bill_number_to_linkable_bills: dict[str, list[LinkableBill]]


@dataclass(frozen=True)
class BillLink:
    bill_index: int
    source: BillLinkSource


@dataclass(frozen=True, order=True)
class _CloseBill:
    gap_days: int
    bill_index: int


def build_bill_lookups(
    title_key_to_linkable_bills: dict[str, list[LinkableBill]],
    bill_number_to_linkable_bills: dict[str, list[LinkableBill]],
) -> BillLookups:
    loose_title_key_to_linkable_bills: dict[str, list[LinkableBill]] = {}
    for title_key, linkable_bills in title_key_to_linkable_bills.items():
        loose_title_key_to_linkable_bills.setdefault(
            get_loose_title_key(title_key), []
        ).extend(linkable_bills)
    return BillLookups(
        title_key_to_linkable_bills,
        loose_title_key_to_linkable_bills,
        bill_number_to_linkable_bills,
    )


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
    if not is_leading_the_title(printed_title):
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


def get_bill_number_link_index(
    printed_bill_number: Optional[str],
    first_reading_date: Optional[date],
    bill_lookups: BillLookups,
) -> Optional[int]:
    if printed_bill_number is None:
        return None
    if first_reading_date is None:
        return None
    bill_number = normalize_bill_number(printed_bill_number)
    if bill_number is None:
        return None
    linkable_bills = bill_lookups.bill_number_to_linkable_bills.get(bill_number)
    if linkable_bills is None:
        return None
    close_bill_indexes = [
        linkable_bill.bill_index
        for linkable_bill in linkable_bills
        if _is_near_reading(first_reading_date, linkable_bill)
    ]
    if len(close_bill_indexes) != 1:
        return None
    return close_bill_indexes[0]


def get_hand_kept_bill_link(
    sso_code: str,
    ordinal: int,
    printed_title: str,
    hand_kept_act_links: list[HandKeptActLink],
    bill_report_ids: list[list[int]],
) -> Optional[BillLink]:
    for hand_kept_act_link in hand_kept_act_links:
        if (
            hand_kept_act_link.sso_code != sso_code
            or hand_kept_act_link.ordinal != ordinal
        ):
            continue
        if hand_kept_act_link.printed_title != printed_title:
            raise HansardHandKeptEntryError(
                f"hand_kept_act_links.json: {sso_code} {ordinal} prints "
                f"{printed_title!r}, not {hand_kept_act_link.printed_title!r}"
            )
        for bill_index, report_ids in enumerate(bill_report_ids):
            if set(report_ids) == set(hand_kept_act_link.report_ids):
                return BillLink(bill_index, BillLinkSource.HAND_KEPT)
        raise HansardHandKeptEntryError(
            f"hand_kept_act_links.json: {sso_code} {ordinal} names reports "
            f"{hand_kept_act_link.report_ids}, which no bill holds exactly"
        )
    return None


def validate_can_find_hand_kept_act_links(
    hand_kept_act_links: list[HandKeptActLink],
    linked_sso_codes_and_ordinals: set[tuple[str, int]],
) -> None:
    for hand_kept_act_link in hand_kept_act_links:
        if (
            hand_kept_act_link.sso_code,
            hand_kept_act_link.ordinal,
        ) not in linked_sso_codes_and_ordinals:
            raise HansardHandKeptEntryError(
                f"hand_kept_act_links.json: {hand_kept_act_link.sso_code} "
                f"{hand_kept_act_link.ordinal} is not an Act or Ordinance entry "
                "of the harvest"
            )

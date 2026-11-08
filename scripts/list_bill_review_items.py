import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.act_history_entry import ActHistoryEntryRow, CRUDActHistoryEntry
from crud.acts_supplement_entry import ActsSupplementEntryRow, CRUDActsSupplementEntry
from crud.bill import BillRow, CRUDBill
from crud.bill_report import CRUDBillReport
from crud.bills_supplement_entry import (
    BillsSupplementEntryRow,
    CRUDBillsSupplementEntry,
)
from database.init import build_read_only_engine
from enums import (
    ActHistoryEntryKind,
    BillEra,
    BillNumberSource,
    BillReviewItemKind,
    EgazetteSupplementKind,
)
from logs import logger
from populate.act_links import (
    BillGroupingContext,
    build_bill_lookups_from_context,
    get_bill_grouping_context,
)
from schemas.bill_review_list import BillEraDoneTests, BillReviewItem, BillReviewList
from schemas.bill_title_correction import BillTitleCorrection
from schemas.hand_kept_bill import HandKeptBill
from services.act_link import BillLookups, get_bill_number_link_index
from services.bill import (
    ActNumberCandidate,
    BillGroup,
    BillNumberCandidate,
    build_acts_supplement_act_number_candidate,
    build_listing_bill_number_candidate,
    get_act_number_candidates_in_window,
    is_publication_date_misprinted,
)
from settings import settings
from utils.data_files import get_bill_title_corrections, get_hand_kept_bills
from utils.title_key import get_bill_title_key, get_loose_title_key

_SECOND_ERA_START_YEAR = 1961
_THIRD_ERA_START_YEAR = 2006
_FIRST_ANNUAL_NUMBERING_YEAR = 1966
_JANUARY_1961_SERIES_YEAR = 1961
_OCTOBER_1963_SERIES_YEAR = 1963
_LAST_ORDINAL_BEFORE_THE_LISTING = 123
_FIRST_COMPLETE_SUPPLEMENT_YEAR = 1966
_MIN_TITLE_SIMILARITY = 0.85
_MAX_DAYS_FROM_READING = 1
_THE_KEY_PREFIX = "the"
_READ_ISOLATION_LEVEL = "REPEATABLE READ"


@dataclass(frozen=True)
class _ReviewBill:
    bill_index: int
    bill_group: BillGroup
    first_reading_dates: list[date]
    report_dates: list[date]


@dataclass(frozen=True)
class _ReviewInputs:
    review_bills: list[_ReviewBill]
    context: BillGroupingContext
    bill_lookups: BillLookups
    entry_rows: list[BillsSupplementEntryRow]
    acts_supplement_entry_rows: list[ActsSupplementEntryRow]
    act_number_candidates: list[ActNumberCandidate]
    act_history_entry_rows: list[ActHistoryEntryRow]
    stored_bill_rows: list[BillRow]
    stored_bill_id_to_bill_index: dict[int, int]
    hand_kept_bills: list[HandKeptBill]


def get_bill_era(year: int) -> BillEra:
    if year >= _THIRD_ERA_START_YEAR:
        return BillEra.YEARS_2006_ON
    if year >= _SECOND_ERA_START_YEAR:
        return BillEra.YEARS_1961_TO_2005
    return BillEra.YEARS_1955_TO_1960


def _get_bill_number_ordinal(bill_number: str) -> int:
    return int(bill_number.split("/")[0])


def _get_bill_number_year(bill_number: str) -> int:
    return int(bill_number.split("/")[1])


def _get_bill_number_series_year(bill_number: str) -> int:
    year = _get_bill_number_year(bill_number)
    if year >= _FIRST_ANNUAL_NUMBERING_YEAR:
        return year
    if _get_bill_number_ordinal(bill_number) > _LAST_ORDINAL_BEFORE_THE_LISTING:
        return _JANUARY_1961_SERIES_YEAR
    return _OCTOBER_1963_SERIES_YEAR


def get_supplement_bill_number_count(bill_numbers: list[str], era: BillEra) -> int:
    series_year_to_highest_ordinal: dict[int, int] = defaultdict(int)
    for bill_number in bill_numbers:
        series_year = _get_bill_number_series_year(bill_number)
        series_year_to_highest_ordinal[series_year] = max(
            series_year_to_highest_ordinal[series_year],
            _get_bill_number_ordinal(bill_number),
        )
    return sum(
        highest_ordinal - _LAST_ORDINAL_BEFORE_THE_LISTING
        if series_year == _JANUARY_1961_SERIES_YEAR
        else highest_ordinal
        for series_year, highest_ordinal in series_year_to_highest_ordinal.items()
        if get_bill_era(series_year) == era
    )


def _build_review_bills(context: BillGroupingContext) -> list[_ReviewBill]:
    return [
        _ReviewBill(
            bill_index,
            bill_group,
            sorted(
                context.report_id_to_sitting_date[report_id]
                for report_id in bill_group.report_ids
                if report_id in context.first_reading_report_ids
            ),
            sorted(
                context.report_id_to_sitting_date[report_id]
                for report_id in bill_group.report_ids
            ),
        )
        for bill_index, bill_group in enumerate(context.bill_grouping.bill_groups)
    ]


def _is_read_in_window(
    review_bill: _ReviewBill, candidate: BillNumberCandidate
) -> bool:
    return any(
        candidate.earliest_first_reading_date
        <= first_reading_date
        <= candidate.latest_first_reading_date
        for first_reading_date in review_bill.first_reading_dates
    )


def _is_exact_title(review_bill: _ReviewBill, title_key: str) -> bool:
    if review_bill.bill_group.title_key == title_key:
        return True
    return review_bill.bill_group.title_key == f"{_THE_KEY_PREFIX}{title_key}"


def _is_loose_or_similar_title(review_bill: _ReviewBill, title_key: str) -> bool:
    if get_loose_title_key(review_bill.bill_group.title_key) == get_loose_title_key(
        title_key
    ):
        return True
    return (
        SequenceMatcher(None, review_bill.bill_group.title_key, title_key).ratio()
        >= _MIN_TITLE_SIMILARITY
    )


def _format_bills(review_bills: list[_ReviewBill]) -> str:
    return "; ".join(
        f"{review_bill.bill_group.title} (reports {review_bill.bill_group.report_ids})"
        for review_bill in review_bills
    )


def _get_neighbour_first_reading(
    numbered_bills: dict[str, _ReviewBill], bill_number: str, is_lower: bool
) -> Optional[date]:
    ordinal = _get_bill_number_ordinal(bill_number)
    year = _get_bill_number_year(bill_number)
    neighbour_ordinals = [
        _get_bill_number_ordinal(numbered_bill_number)
        for numbered_bill_number, review_bill in numbered_bills.items()
        if _get_bill_number_year(numbered_bill_number) == year
        and review_bill.first_reading_dates
        and (
            _get_bill_number_ordinal(numbered_bill_number) < ordinal
            if is_lower
            else _get_bill_number_ordinal(numbered_bill_number) > ordinal
        )
    ]
    if not neighbour_ordinals:
        return None
    neighbour_ordinal = max(neighbour_ordinals) if is_lower else min(neighbour_ordinals)
    return numbered_bills[f"{neighbour_ordinal}/{year}"].first_reading_dates[0]


def _build_unplaced_entry_item(
    entry_row: BillsSupplementEntryRow,
    candidate: BillNumberCandidate,
    inputs: _ReviewInputs,
    numbered_bills: dict[str, _ReviewBill],
) -> BillReviewItem:
    era = get_bill_era(_get_bill_number_year(entry_row.bill_number))
    lower_bound = _get_neighbour_first_reading(
        numbered_bills, entry_row.bill_number, is_lower=True
    )
    upper_bound = _get_neighbour_first_reading(
        numbered_bills, entry_row.bill_number, is_lower=False
    )
    if lower_bound is None or upper_bound is None:
        return BillReviewItem(
            kind=BillReviewItemKind.SUPPLEMENT_ENTRY_UNPLACED,
            era=era,
            bill_number=entry_row.bill_number,
            printed_title=entry_row.printed_title,
            bill_title=None,
            report_ids=[],
            detail=f"No bill read within {candidate.earliest_first_reading_date} to {candidate.latest_first_reading_date}; R1b has no numbered neighbour on one side",
        )
    proposed_bills = [
        review_bill
        for review_bill in inputs.review_bills
        if _is_exact_title(review_bill, candidate.title_key)
        and any(
            lower_bound <= first_reading_date <= upper_bound
            for first_reading_date in review_bill.first_reading_dates
        )
    ]
    if len(proposed_bills) != 1:
        return BillReviewItem(
            kind=BillReviewItemKind.SUPPLEMENT_ENTRY_UNPLACED,
            era=era,
            bill_number=entry_row.bill_number,
            printed_title=entry_row.printed_title,
            bill_title=None,
            report_ids=[],
            detail=f"No bill read within {candidate.earliest_first_reading_date} to {candidate.latest_first_reading_date}; R1b finds {len(proposed_bills)} same-title bills read between {lower_bound} and {upper_bound}",
        )
    (proposed_bill,) = proposed_bills
    return BillReviewItem(
        kind=BillReviewItemKind.SUPPLEMENT_ENTRY_UNPLACED,
        era=era,
        bill_number=entry_row.bill_number,
        printed_title=entry_row.printed_title,
        bill_title=proposed_bill.bill_group.title,
        report_ids=proposed_bill.bill_group.report_ids,
        detail=f"No bill read within {candidate.earliest_first_reading_date} to {candidate.latest_first_reading_date}; R1b proposes the bill read on {proposed_bill.first_reading_dates[0]}, between the neighbours read on {lower_bound} and {upper_bound}",
    )


def _build_supplement_entry_items(
    entry_row: BillsSupplementEntryRow,
    inputs: _ReviewInputs,
    numbered_bills: dict[str, _ReviewBill],
) -> list[BillReviewItem]:
    items: list[BillReviewItem] = []
    year = _get_bill_number_year(entry_row.bill_number)
    era = get_bill_era(year)
    if is_publication_date_misprinted(
        entry_row.bill_number, entry_row.publication_date
    ):
        items.append(
            BillReviewItem(
                kind=BillReviewItemKind.MISPRINTED_PUBLICATION_DATE,
                era=era,
                bill_number=entry_row.bill_number,
                printed_title=entry_row.printed_title,
                bill_title=None,
                report_ids=[],
                detail=f"Published {entry_row.publication_date}, outside {year}",
            )
        )
    placed_bill = numbered_bills.get(entry_row.bill_number)
    if (
        placed_bill is not None
        and placed_bill.bill_group.bill_number_source
        == BillNumberSource.BILLS_SUPPLEMENT_LISTING
    ):
        return items
    candidate = build_listing_bill_number_candidate(
        entry_row.printed_title, entry_row.bill_number, entry_row.publication_date
    )
    exact_bills = [
        review_bill
        for review_bill in inputs.review_bills
        if _is_exact_title(review_bill, candidate.title_key)
        and _is_read_in_window(review_bill, candidate)
    ]
    if len(exact_bills) > 1:
        items.append(
            BillReviewItem(
                kind=BillReviewItemKind.SUPPLEMENT_ENTRY_WITH_TWO_CANDIDATES,
                era=era,
                bill_number=entry_row.bill_number,
                printed_title=entry_row.printed_title,
                bill_title=None,
                report_ids=[],
                detail=f"Same-title bills read within the window: {_format_bills(exact_bills)}",
            )
        )
        return items
    if len(exact_bills) == 1:
        (exact_bill,) = exact_bills
        items.append(
            BillReviewItem(
                kind=BillReviewItemKind.SUPPLEMENT_ENTRY_UNPLACED,
                era=era,
                bill_number=entry_row.bill_number,
                printed_title=entry_row.printed_title,
                bill_title=exact_bill.bill_group.title,
                report_ids=exact_bill.bill_group.report_ids,
                detail=f"The one same-title bill read within the window holds bill number {exact_bill.bill_group.bill_number}",
            )
        )
        return items
    loose_bills = [
        review_bill
        for review_bill in inputs.review_bills
        if _is_loose_or_similar_title(review_bill, candidate.title_key)
        and _is_read_in_window(review_bill, candidate)
    ]
    if loose_bills:
        items.append(
            BillReviewItem(
                kind=BillReviewItemKind.SUPPLEMENT_LINK_BY_LOOSE_OR_SIMILAR_TITLE,
                era=era,
                bill_number=entry_row.bill_number,
                printed_title=entry_row.printed_title,
                bill_title=loose_bills[0].bill_group.title,
                report_ids=loose_bills[0].bill_group.report_ids,
                detail=f"Bills of a loose or similar title read within the window: {_format_bills(loose_bills)}",
            )
        )
        return items
    items.append(
        _build_unplaced_entry_item(entry_row, candidate, inputs, numbered_bills)
    )
    return items


def _build_split_merge_items(inputs: _ReviewInputs) -> list[BillReviewItem]:
    report_id_to_review_bill = {
        report_id: review_bill
        for review_bill in inputs.review_bills
        for report_id in review_bill.bill_group.report_ids
    }
    hand_kept_report_id_sets = [
        frozenset(hand_kept_bill.report_ids)
        for hand_kept_bill in inputs.hand_kept_bills
    ]
    items: list[BillReviewItem] = []
    for split_merge in inputs.context.bill_grouping.split_merges:
        report_ids = split_merge.head_report_ids + split_merge.tail_report_ids
        review_bill = report_id_to_review_bill[report_ids[0]]
        hand_kept_note = (
            "; equals a hand-kept bill"
            if frozenset(review_bill.bill_group.report_ids) in hand_kept_report_id_sets
            else ""
        )
        items.append(
            BillReviewItem(
                kind=BillReviewItemKind.SPLIT_BILL_MERGE,
                era=get_bill_era(review_bill.report_dates[0].year),
                bill_number=review_bill.bill_group.bill_number,
                printed_title=None,
                bill_title=review_bill.bill_group.title,
                report_ids=report_ids,
                detail=f"Head reports {split_merge.head_report_ids} merged with tail reports {split_merge.tail_report_ids}{hand_kept_note}",
            )
        )
    return items


def _is_near_third_reading(review_bill: _ReviewBill, third_reading_date: date) -> bool:
    return any(
        abs((report_date - third_reading_date).days) <= _MAX_DAYS_FROM_READING
        for report_date in review_bill.report_dates
    )


def _get_entry_era(
    entry_row: ActHistoryEntryRow, review_bill: Optional[_ReviewBill]
) -> BillEra:
    if entry_row.first_reading_date is not None:
        return get_bill_era(entry_row.first_reading_date.year)
    if review_bill is not None:
        return get_bill_era(review_bill.report_dates[0].year)
    return get_bill_era(_get_bill_number_year(entry_row.printed_law_number))


def _build_history_entry_items(
    entry_row: ActHistoryEntryRow, inputs: _ReviewInputs
) -> list[BillReviewItem]:
    if (
        entry_row.kind != ActHistoryEntryKind.ACT
        and entry_row.kind != ActHistoryEntryKind.ORDINANCE
    ):
        return []
    number_bill_index = get_bill_number_link_index(
        entry_row.printed_bill_number, entry_row.first_reading_date, inputs.bill_lookups
    )
    title_bill_index = (
        None
        if entry_row.bill_id is None
        else inputs.stored_bill_id_to_bill_index.get(entry_row.bill_id)
    )
    number_bill = (
        None if number_bill_index is None else inputs.review_bills[number_bill_index]
    )
    title_bill = (
        None if title_bill_index is None else inputs.review_bills[title_bill_index]
    )
    items: list[BillReviewItem] = []
    if number_bill is not None and title_bill is None:
        items.append(
            BillReviewItem(
                kind=BillReviewItemKind.HISTORY_LINK_BY_NUMBER_ONLY,
                era=_get_entry_era(entry_row, number_bill),
                bill_number=number_bill.bill_group.bill_number,
                printed_title=entry_row.printed_title,
                bill_title=number_bill.bill_group.title,
                report_ids=number_bill.bill_group.report_ids,
                detail=f"{entry_row.printed_law_number}: bill number {entry_row.printed_bill_number} names a bill the title rules do not link",
            )
        )
    if (
        number_bill is not None
        and title_bill is not None
        and number_bill is not title_bill
    ):
        items.append(
            BillReviewItem(
                kind=BillReviewItemKind.HISTORY_LINK_RULES_DISAGREE,
                era=_get_entry_era(entry_row, number_bill),
                bill_number=number_bill.bill_group.bill_number,
                printed_title=entry_row.printed_title,
                bill_title=title_bill.bill_group.title,
                report_ids=title_bill.bill_group.report_ids,
                detail=f"{entry_row.printed_law_number}: bill number {entry_row.printed_bill_number} names {_format_bills([number_bill])}, the stored link is {_format_bills([title_bill])}",
            )
        )
    if (
        title_bill is not None
        and entry_row.third_reading_date is not None
        and not _is_near_third_reading(title_bill, entry_row.third_reading_date)
    ):
        items.append(
            BillReviewItem(
                kind=BillReviewItemKind.HISTORY_LINK_WITHOUT_THIRD_READING_REPORT,
                era=_get_entry_era(entry_row, title_bill),
                bill_number=title_bill.bill_group.bill_number,
                printed_title=entry_row.printed_title,
                bill_title=title_bill.bill_group.title,
                report_ids=title_bill.bill_group.report_ids,
                detail=f"{entry_row.printed_law_number}: third reading {entry_row.third_reading_date}, the linked bill's reports fall on {title_bill.report_dates}",
            )
        )
    return items


def _build_passed_bill_items(inputs: _ReviewInputs) -> list[BillReviewItem]:
    return [
        BillReviewItem(
            kind=BillReviewItemKind.PASSED_BILL_WITHOUT_SUPPLEMENT_ENTRY,
            era=get_bill_era(review_bill.report_dates[0].year),
            bill_number=None,
            printed_title=None,
            bill_title=review_bill.bill_group.title,
            report_ids=review_bill.bill_group.report_ids,
            detail=f"Passed on {review_bill.report_dates[-1]} with no Supplement entry",
        )
        for review_bill in inputs.review_bills
        if review_bill.bill_group.is_passed
        and review_bill.report_dates[0].year >= _FIRST_COMPLETE_SUPPLEMENT_YEAR
        and review_bill.bill_group.bill_number is None
    ]


def _build_two_act_number_items(inputs: _ReviewInputs) -> list[BillReviewItem]:
    items: list[BillReviewItem] = []
    for review_bill in inputs.review_bills:
        if not review_bill.bill_group.is_passed:
            continue
        candidates_in_window = get_act_number_candidates_in_window(
            review_bill.bill_group.title_key,
            review_bill.report_dates[-1],
            inputs.act_number_candidates,
        )
        act_numbers = sorted(
            {candidate.act_number for candidate in candidates_in_window}
        )
        if len(act_numbers) <= 1:
            continue
        items.append(
            BillReviewItem(
                kind=BillReviewItemKind.ACTS_SUPPLEMENT_BILL_WITH_TWO_ACT_NUMBERS,
                era=get_bill_era(review_bill.report_dates[0].year),
                bill_number=review_bill.bill_group.bill_number,
                printed_title=None,
                bill_title=review_bill.bill_group.title,
                report_ids=review_bill.bill_group.report_ids,
                detail=f"Last debated {review_bill.report_dates[-1]}; Acts Supplement entries of the title within the window: {', '.join(act_numbers)}",
            )
        )
    return items


def _get_nearest_passed_bill(
    title_key: str, publication_date: date, review_bills: list[_ReviewBill]
) -> Optional[_ReviewBill]:
    same_title_passed_bills = [
        review_bill
        for review_bill in review_bills
        if review_bill.bill_group.is_passed
        and review_bill.bill_group.title_key == title_key
    ]
    if not same_title_passed_bills:
        return None
    return min(
        same_title_passed_bills,
        key=lambda review_bill: abs(
            (review_bill.report_dates[-1] - publication_date).days
        ),
    )


def _build_unplaced_act_number_item(
    entry_row: ActsSupplementEntryRow, inputs: _ReviewInputs
) -> BillReviewItem:
    era = get_bill_era(_get_bill_number_year(entry_row.act_number))
    nearest_bill = _get_nearest_passed_bill(
        get_bill_title_key(entry_row.printed_title),
        entry_row.publication_date,
        inputs.review_bills,
    )
    if nearest_bill is None:
        return BillReviewItem(
            kind=BillReviewItemKind.ACTS_SUPPLEMENT_ENTRY_UNPLACED,
            era=era,
            bill_number=None,
            printed_title=entry_row.printed_title,
            bill_title=None,
            report_ids=[],
            detail=f"Act {entry_row.act_number} published {entry_row.publication_date}; no passed bill of this title",
        )
    return BillReviewItem(
        kind=BillReviewItemKind.ACTS_SUPPLEMENT_ENTRY_UNPLACED,
        era=era,
        bill_number=nearest_bill.bill_group.bill_number,
        printed_title=entry_row.printed_title,
        bill_title=nearest_bill.bill_group.title,
        report_ids=nearest_bill.bill_group.report_ids,
        detail=f"Act {entry_row.act_number} published {entry_row.publication_date}; the nearest passed bill of this title was last debated {nearest_bill.report_dates[-1]}, {(entry_row.publication_date - nearest_bill.report_dates[-1]).days} days before",
    )


def _build_unplaced_act_number_items(inputs: _ReviewInputs) -> list[BillReviewItem]:
    placed_act_numbers = {
        review_bill.bill_group.act_number
        for review_bill in inputs.review_bills
        if review_bill.bill_group.act_number is not None
    }
    act_number_to_first_entry_row: dict[str, ActsSupplementEntryRow] = {}
    for entry_row in inputs.acts_supplement_entry_rows:
        if entry_row.act_number in placed_act_numbers:
            continue
        act_number_to_first_entry_row.setdefault(entry_row.act_number, entry_row)
    return [
        _build_unplaced_act_number_item(entry_row, inputs)
        for entry_row in act_number_to_first_entry_row.values()
    ]


def _build_items(inputs: _ReviewInputs) -> list[BillReviewItem]:
    numbered_bills = {
        review_bill.bill_group.bill_number: review_bill
        for review_bill in inputs.review_bills
        if review_bill.bill_group.bill_number is not None
    }
    return (
        [
            item
            for entry_row in inputs.entry_rows
            for item in _build_supplement_entry_items(entry_row, inputs, numbered_bills)
        ]
        + _build_split_merge_items(inputs)
        + [
            item
            for entry_row in inputs.act_history_entry_rows
            for item in _build_history_entry_items(entry_row, inputs)
        ]
        + _build_passed_bill_items(inputs)
        + _build_two_act_number_items(inputs)
        + _build_unplaced_act_number_items(inputs)
    )


def _is_debate_complete(review_bill: _ReviewBill, context: BillGroupingContext) -> bool:
    if not review_bill.first_reading_dates:
        return False
    if not review_bill.bill_group.is_passed:
        return True
    return any(
        report_id in context.third_reading_report_ids
        for report_id in review_bill.bill_group.report_ids
    )


def _build_done_tests(
    inputs: _ReviewInputs, items: list[BillReviewItem]
) -> list[BillEraDoneTests]:
    linked_stored_bill_ids = (
        [
            entry_row.bill_id
            for entry_row in inputs.act_history_entry_rows
            if entry_row.bill_id is not None
        ]
        + [
            egazette_supplement_row.bill_id
            for egazette_supplement_row in inputs.context.egazette_supplement_rows
            if egazette_supplement_row.bill_id is not None
        ]
        + [
            stored_bill_row.id
            for stored_bill_row in inputs.stored_bill_rows
            if stored_bill_row.act_number is not None
        ]
    )
    linked_bill_indexes = {
        inputs.stored_bill_id_to_bill_index[stored_bill_id]
        for stored_bill_id in linked_stored_bill_ids
        if stored_bill_id in inputs.stored_bill_id_to_bill_index
    }
    numbered_bill_numbers = [
        entry_row.bill_number for entry_row in inputs.entry_rows
    ] + [
        egazette_supplement_row.bill_number
        for egazette_supplement_row in inputs.context.egazette_supplement_rows
        if egazette_supplement_row.supplement_kind == EgazetteSupplementKind.BILLS
    ]
    done_tests: list[BillEraDoneTests] = []
    for era in BillEra:
        era_bills = [
            review_bill
            for review_bill in inputs.review_bills
            if get_bill_era(review_bill.report_dates[0].year) == era
        ]
        numbered_bills = [
            review_bill
            for review_bill in inputs.review_bills
            if review_bill.bill_group.bill_number is not None
            and get_bill_era(_get_bill_number_year(review_bill.bill_group.bill_number))
            == era
        ]
        passed_bills = [
            review_bill for review_bill in era_bills if review_bill.bill_group.is_passed
        ]
        unclassed_passed_bills = [
            review_bill
            for review_bill in passed_bills
            if review_bill.bill_group.bill_class is None
        ]
        done_tests.append(
            BillEraDoneTests(
                era=era,
                hansard_bill_count=len(era_bills),
                supplement_bill_number_count=get_supplement_bill_number_count(
                    numbered_bill_numbers, era
                ),
                numbered_bill_count=len(numbered_bills),
                debate_complete_bill_count=sum(
                    _is_debate_complete(review_bill, inputs.context)
                    for review_bill in numbered_bills
                ),
                passed_bill_count=len(passed_bills),
                outcome_resolved_bill_count=sum(
                    review_bill.bill_index in linked_bill_indexes
                    or review_bill.bill_group.bill_class is not None
                    for review_bill in passed_bills
                ),
                unclassed_passed_bill_count=len(unclassed_passed_bills),
                unclassed_outcome_resolved_bill_count=sum(
                    review_bill.bill_index in linked_bill_indexes
                    for review_bill in unclassed_passed_bills
                ),
                review_item_count=sum(item.era == era for item in items),
            )
        )
    return done_tests


def get_bill_review_list(
    session: Session,
    bill_title_corrections: list[BillTitleCorrection],
    hand_kept_bills: list[HandKeptBill],
) -> BillReviewList:
    context = get_bill_grouping_context(
        session, bill_title_corrections, hand_kept_bills
    )
    review_bills = _build_review_bills(context)
    report_ids_to_bill_index = {
        frozenset(review_bill.bill_group.report_ids): review_bill.bill_index
        for review_bill in review_bills
    }
    stored_bill_id_to_report_ids: dict[int, set[int]] = defaultdict(set)
    for bill_report_row in CRUDBillReport(session).get_rows():
        stored_bill_id_to_report_ids[bill_report_row.bill_id].add(
            bill_report_row.report_id
        )
    stored_bill_id_to_bill_index = {
        stored_bill_id: report_ids_to_bill_index[frozenset(report_ids)]
        for stored_bill_id, report_ids in stored_bill_id_to_report_ids.items()
        if frozenset(report_ids) in report_ids_to_bill_index
    }
    logger.info(
        f"Stored bills: {len(stored_bill_id_to_report_ids):,}, {len(stored_bill_id_to_report_ids) - len(stored_bill_id_to_bill_index):,} not in the grouping"
    )
    acts_supplement_entry_rows = CRUDActsSupplementEntry(session).get_rows()
    inputs = _ReviewInputs(
        review_bills,
        context,
        build_bill_lookups_from_context(context),
        CRUDBillsSupplementEntry(session).get_rows(),
        acts_supplement_entry_rows,
        [
            build_acts_supplement_act_number_candidate(
                entry_row.printed_title,
                entry_row.act_number,
                entry_row.publication_date,
            )
            for entry_row in acts_supplement_entry_rows
        ],
        CRUDActHistoryEntry(session).get_rows(),
        CRUDBill(session).get_rows(),
        stored_bill_id_to_bill_index,
        hand_kept_bills,
    )
    items = _build_items(inputs)
    return BillReviewList(items=items, done_tests=_build_done_tests(inputs, items))


def _format_share(count: int, total: int) -> str:
    if total == 0:
        return f"{count:,} of 0"
    return f"{count:,} of {total:,} ({count / total:.1%})"


def _get_era_label(era: BillEra) -> str:
    if era == BillEra.YEARS_1955_TO_1960:
        return "1955 to 1960"
    if era == BillEra.YEARS_1961_TO_2005:
        return "1961 to 2005"
    return "2006 on"


def get_summary_lines(review_list: BillReviewList) -> list[str]:
    lines = [
        f"Review items: {len(review_list.items):,}",
        "Review items by kind: "
        + (
            ", ".join(
                f"{kind} {count:,}"
                for kind, count in sorted(
                    Counter(item.kind.value for item in review_list.items).items()
                )
            )
            or "none"
        ),
    ]
    for done_tests in review_list.done_tests:
        era_label = _get_era_label(done_tests.era)
        if done_tests.era == BillEra.YEARS_1955_TO_1960:
            lines.append(
                f"{era_label}, test 1 bill completeness: {done_tests.hansard_bill_count:,} bills from Hansard, no outside list"
            )
        else:
            lines.append(
                f"{era_label}, test 1 bill completeness: {_format_share(done_tests.numbered_bill_count, done_tests.supplement_bill_number_count)} Supplement numbers held; {done_tests.hansard_bill_count:,} bills from Hansard"
            )
        lines.append(
            f"{era_label}, test 2 debate completeness: {_format_share(done_tests.debate_complete_bill_count, done_tests.numbered_bill_count)} numbered bills hold their first reading and, when passed, their third"
        )
        lines.append(
            f"{era_label}, test 3 outcome resolved: {_format_share(done_tests.outcome_resolved_bill_count, done_tests.passed_bill_count)} passed bills link to an Act or an Act number or carry a class; {_format_share(done_tests.unclassed_outcome_resolved_bill_count, done_tests.unclassed_passed_bill_count)} passed bills of no class link to an Act or an Act number"
        )
        lines.append(
            f"{era_label}, test 4 review items: {done_tests.review_item_count:,}"
        )
    return lines


def list_bill_review_items(review_path: Path, summary_path: Path) -> None:
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_READ_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        review_list = get_bill_review_list(
            session, get_bill_title_corrections(), get_hand_kept_bills()
        )
    lines = get_summary_lines(review_list)
    for line in lines:
        logger.info(line)
    review_path.write_text(review_list.model_dump_json(indent=1))
    summary_path.write_text("\n".join(lines) + "\n")
    logger.info(f"Wrote {review_path} and {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List the bill links no rule settles, and the counts of objective 7's done tests 1 to 4 by era, read only"
    )
    parser.add_argument(
        "--review-file",
        type=Path,
        required=True,
        help="where to write the review items as JSON",
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        required=True,
        help="where to write the summary lines, such as docs/figures/2026-11-08-bill-review.txt",
    )
    arguments = parser.parse_args()
    list_bill_review_items(arguments.review_file, arguments.summary_file)

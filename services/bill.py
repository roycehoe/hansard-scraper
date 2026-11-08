import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional

from crud.report import ReportSittingDateTitleRow
from enums import ActNumberSource, BillClass, BillNumberSource, RepealedActUrlSource
from exceptions import HansardHandKeptEntryError
from schemas.bill_title_correction import BillTitleCorrection
from schemas.hand_kept_bill import HandKeptBill
from utils.title_key import get_bill_title_key, get_loose_title_key, get_title_key

FIRST_READING_PATTERN = r"\yread (a|the|for the) first time"
NOT_FIRST_READING_PATTERNS = (
    "brought up",
    r"\y(was|were|been|is)\y[^.;]{0,40}\yread (a|the|for the) first time",
)
THIRD_READING_PATTERN = r'^\W*[^"]{0,150}\ybill\y[^"]{0,120}\yread (a|the) third time'
NOT_THIRD_READING_PATTERNS = ("be now read", r"^\W*(I|now|sir|mr)\y")
SECOND_READING_PATTERN = r"\yorder for second reading read\y"
BILL_TITLE_END_PATTERN = r"bill[^a-z]*$"

_MAX_DAYS_BETWEEN_REPORTS = 366
_BILL_WORD_PATTERN = re.compile(r"\bbill\b", re.IGNORECASE)
_BILL_TITLE_END = re.compile(BILL_TITLE_END_PATTERN, re.IGNORECASE)
_THE_KEY_PREFIX = "the"
_PUBLICATION_ERA_START_YEAR_TO_MAX_DAYS_AFTER_FIRST_READING = (
    (2011, 4),
    (1990, 9),
    (1967, 18),
)
_EARLIEST_ERA_MAX_DAYS_AFTER_FIRST_READING = 35
_MAX_DAYS_FROM_EGAZETTE_FIRST_READING = 1
_MAX_DAYS_FROM_THIRD_READING_TO_ACT_PUBLICATION = 120
_MAX_DAYS_FROM_ACT_PUBLICATION_TO_THIRD_READING = 1
_MAX_DAYS_BETWEEN_SPLIT_HALVES = 800
_MIN_SPLIT_TITLE_SIMILARITY = 0.85
_SUPPLY_TITLE_KEY_PATTERN = re.compile(
    r"^(?:the)?(?:final|further|revised|second|third|fourth|supplementary)*"
    r"(?:supply|appropriation)(?:andbudgetadjustments)?"
    r"(?:no\d+|fy\d{2,4}|\d{4})*bill$"
)
_REPEAL_KEY_PART = "repeal"
_AMENDMENT_KEY_PART = "amendment"
_SSO_ORIGIN = "https://sso.agc.gov.sg"
_REPEALED_ACT_STATUS_WORDS = frozenset(
    {"Repealed", "Spent", "Expired", "Omitted", "Replaced", "Renamed"}
)
_REPEALED_ACT_STATUS_PATTERN = re.compile(
    r"(?:\s*\((?:" + "|".join(sorted(_REPEALED_ACT_STATUS_WORDS)) + r")\))+\s*$"
)
_PUBLICATION_GRACE_MONTH = 1
_PUBLICATION_GRACE_DAY = 31


@dataclass(frozen=True)
class BillNumberCandidate:
    bill_number: str
    title_key: str
    source: BillNumberSource
    earliest_first_reading_date: date
    latest_first_reading_date: date


@dataclass(frozen=True)
class ActNumberCandidate:
    act_number: str
    title_key: str
    source: ActNumberSource
    earliest_third_reading_date: date
    latest_third_reading_date: date


@dataclass(frozen=True)
class RepealedActCandidate:
    sso_code: str
    title_key: str
    enactment_year: int
    repeal_date: date
    url: str
    source: RepealedActUrlSource


@dataclass(frozen=True)
class BillGroup:
    title: str
    title_key: str
    first_sitting_date: datetime
    last_sitting_date: datetime
    is_passed: bool
    report_ids: list[int]
    bill_number: Optional[str]
    bill_number_source: Optional[BillNumberSource]
    bill_class: Optional[BillClass]
    act_number: Optional[str]
    act_number_source: Optional[ActNumberSource]
    repealed_act_url: Optional[str]
    repealed_act_url_source: Optional[RepealedActUrlSource]


@dataclass(frozen=True)
class SplitMerge:
    head_report_ids: list[int]
    tail_report_ids: list[int]


@dataclass(frozen=True)
class BillGrouping:
    bill_groups: list[BillGroup]
    skipped_report_rows: list[ReportSittingDateTitleRow]
    split_merges: list[SplitMerge]


@dataclass
class _RuleBill:
    title: str
    title_key: str
    first_sitting_date: datetime
    last_sitting_date: datetime
    is_passed: bool
    report_ids: list[int]
    first_reading_dates: list[date]
    printed_title_keys: list[str]


@dataclass(frozen=True)
class _MergedRuleBills:
    rule_bills: list[_RuleBill]
    split_merges: list[SplitMerge]


def is_other_type_bill_reading(
    title: str,
    is_first_reading: bool,
    is_second_reading: bool,
    is_third_reading: bool,
) -> bool:
    return _BILL_TITLE_END.search(title) is not None and (
        is_first_reading or is_second_reading or is_third_reading
    )


def get_bill_class(title_key: str) -> Optional[BillClass]:
    if _SUPPLY_TITLE_KEY_PATTERN.match(title_key) is not None:
        return BillClass.SUPPLY
    if _REPEAL_KEY_PART in title_key and _AMENDMENT_KEY_PART not in title_key:
        return BillClass.REPEAL
    return None


def _get_max_days_after_first_reading(publication_date: date) -> int:
    for (
        era_start_year,
        max_days,
    ) in _PUBLICATION_ERA_START_YEAR_TO_MAX_DAYS_AFTER_FIRST_READING:
        if publication_date.year >= era_start_year:
            return max_days
    return _EARLIEST_ERA_MAX_DAYS_AFTER_FIRST_READING


def is_publication_date_misprinted(bill_number: str, publication_date: date) -> bool:
    year = int(bill_number.split("/")[1])
    if publication_date < date(year, 1, 1):
        return True
    return publication_date > date(
        year + 1, _PUBLICATION_GRACE_MONTH, _PUBLICATION_GRACE_DAY
    )


def build_listing_bill_number_candidate(
    printed_title: str, bill_number: str, publication_date: date
) -> BillNumberCandidate:
    return BillNumberCandidate(
        bill_number,
        get_bill_title_key(printed_title),
        BillNumberSource.BILLS_SUPPLEMENT_LISTING,
        publication_date
        - timedelta(days=_get_max_days_after_first_reading(publication_date)),
        publication_date,
    )


def build_egazette_bill_number_candidate(
    printed_title: str, bill_number: str, first_reading_date: date
) -> BillNumberCandidate:
    return BillNumberCandidate(
        bill_number,
        get_bill_title_key(printed_title),
        BillNumberSource.EGAZETTE_BILLS_SUPPLEMENT,
        first_reading_date - timedelta(days=_MAX_DAYS_FROM_EGAZETTE_FIRST_READING),
        first_reading_date + timedelta(days=_MAX_DAYS_FROM_EGAZETTE_FIRST_READING),
    )


def build_acts_supplement_act_number_candidate(
    printed_title: str, act_number: str, publication_date: date
) -> ActNumberCandidate:
    return ActNumberCandidate(
        act_number,
        get_bill_title_key(printed_title),
        ActNumberSource.ACTS_SUPPLEMENT_LISTING,
        publication_date
        - timedelta(days=_MAX_DAYS_FROM_THIRD_READING_TO_ACT_PUBLICATION),
        publication_date
        + timedelta(days=_MAX_DAYS_FROM_ACT_PUBLICATION_TO_THIRD_READING),
    )


def get_act_number_candidates_in_window(
    title_key: str,
    third_reading_date: date,
    act_number_candidates: list[ActNumberCandidate],
) -> list[ActNumberCandidate]:
    return [
        candidate
        for candidate in act_number_candidates
        if candidate.title_key == title_key
        and candidate.earliest_third_reading_date
        <= third_reading_date
        <= candidate.latest_third_reading_date
    ]


def get_single_act_number_candidate(
    candidates_in_window: list[ActNumberCandidate],
) -> Optional[ActNumberCandidate]:
    act_numbers = {candidate.act_number for candidate in candidates_in_window}
    if len(act_numbers) != 1:
        return None
    return candidates_in_window[0]


def _get_act_number_candidate(
    rule_bill: _RuleBill, act_number_candidates: list[ActNumberCandidate]
) -> Optional[ActNumberCandidate]:
    if not rule_bill.is_passed:
        return None
    return get_single_act_number_candidate(
        get_act_number_candidates_in_window(
            rule_bill.title_key,
            rule_bill.last_sitting_date.date(),
            act_number_candidates,
        )
    )


def build_repealed_acts_listing_candidate(
    printed_title: str,
    sso_code: str,
    enactment_year: int,
    repeal_date: date,
    link: str,
) -> RepealedActCandidate:
    return RepealedActCandidate(
        sso_code,
        get_loose_title_key(
            get_bill_title_key(_REPEALED_ACT_STATUS_PATTERN.sub("", printed_title))
        ),
        enactment_year,
        repeal_date,
        _SSO_ORIGIN + link,
        RepealedActUrlSource.REPEALED_ACTS_LISTING,
    )


def get_repealed_act_candidates_of_bill(
    title_key: str,
    first_sitting_date: datetime,
    last_sitting_date: datetime,
    repealed_act_candidates: list[RepealedActCandidate],
) -> list[RepealedActCandidate]:
    loose_title_key = get_loose_title_key(title_key)
    title_candidates = [
        candidate
        for candidate in repealed_act_candidates
        if candidate.title_key == loose_title_key
    ]
    if _AMENDMENT_KEY_PART in title_key:
        return [
            candidate
            for candidate in title_candidates
            if candidate.enactment_year <= first_sitting_date.year
            and last_sitting_date.date() <= candidate.repeal_date
        ]
    return [
        candidate
        for candidate in title_candidates
        if candidate.enactment_year == first_sitting_date.year
        or candidate.enactment_year == last_sitting_date.year
    ]


def get_single_repealed_act_candidate(
    candidates: list[RepealedActCandidate],
) -> Optional[RepealedActCandidate]:
    sso_codes = {candidate.sso_code for candidate in candidates}
    if len(sso_codes) != 1:
        return None
    return candidates[0]


def _get_repealed_act_candidate(
    rule_bill: _RuleBill, repealed_act_candidates: list[RepealedActCandidate]
) -> Optional[RepealedActCandidate]:
    if not rule_bill.is_passed:
        return None
    return get_single_repealed_act_candidate(
        get_repealed_act_candidates_of_bill(
            rule_bill.title_key,
            rule_bill.first_sitting_date,
            rule_bill.last_sitting_date,
            repealed_act_candidates,
        )
    )


def _get_candidate_title_keys(printed_title_keys: list[str]) -> list[str]:
    candidate_title_keys = list(printed_title_keys)
    for title_key in printed_title_keys:
        if title_key.startswith(_THE_KEY_PREFIX):
            candidate_title_keys.append(title_key[len(_THE_KEY_PREFIX) :])
    return candidate_title_keys


def _get_matching_candidates(
    printed_title_keys: list[str],
    first_reading_dates: list[date],
    title_key_to_candidates: dict[str, list[BillNumberCandidate]],
) -> list[BillNumberCandidate]:
    return [
        candidate
        for title_key in _get_candidate_title_keys(printed_title_keys)
        for candidate in title_key_to_candidates.get(title_key, [])
        if any(
            candidate.earliest_first_reading_date
            <= first_reading_date
            <= candidate.latest_first_reading_date
            for first_reading_date in first_reading_dates
        )
    ]


def _build_title_key_to_candidates(
    bill_number_candidates: list[BillNumberCandidate],
) -> dict[str, list[BillNumberCandidate]]:
    title_key_to_candidates: dict[str, list[BillNumberCandidate]] = {}
    for candidate in bill_number_candidates:
        title_key_to_candidates.setdefault(candidate.title_key, []).append(candidate)
    return title_key_to_candidates


def _get_single_bill_number(
    matching_candidates: list[BillNumberCandidate],
) -> Optional[BillNumberCandidate]:
    bill_numbers = {candidate.bill_number for candidate in matching_candidates}
    if len(bill_numbers) != 1:
        return None
    return min(
        matching_candidates,
        key=lambda candidate: list(BillNumberSource).index(candidate.source),
    )


def _assign_bill_numbers(
    rule_bills: list[_RuleBill],
    title_key_to_candidates: dict[str, list[BillNumberCandidate]],
) -> list[Optional[BillNumberCandidate]]:
    single_candidates = [
        _get_single_bill_number(
            _get_matching_candidates(
                rule_bill.printed_title_keys,
                rule_bill.first_reading_dates,
                title_key_to_candidates,
            )
        )
        for rule_bill in rule_bills
    ]
    bill_number_counts = Counter(
        candidate.bill_number
        for candidate in single_candidates
        if candidate is not None
    )
    return [
        candidate
        if candidate is not None and bill_number_counts[candidate.bill_number] == 1
        else None
        for candidate in single_candidates
    ]


def _is_split_tail_of(head: _RuleBill, tail: _RuleBill) -> bool:
    gap = tail.first_sitting_date - head.last_sitting_date
    return (
        timedelta(days=0) < gap <= timedelta(days=_MAX_DAYS_BETWEEN_SPLIT_HALVES)
        and SequenceMatcher(None, head.title_key, tail.title_key).ratio()
        >= _MIN_SPLIT_TITLE_SIMILARITY
    )


def _is_number_conflict(
    head: _RuleBill,
    tail: _RuleBill,
    head_candidate: Optional[BillNumberCandidate],
    title_key_to_candidates: dict[str, list[BillNumberCandidate]],
) -> bool:
    if head_candidate is None:
        return False
    span_start = head.last_sitting_date.date()
    span_end = tail.first_sitting_date.date()
    return any(
        candidate.bill_number != head_candidate.bill_number
        for title_key in _get_candidate_title_keys(tail.printed_title_keys)
        for candidate in title_key_to_candidates.get(title_key, [])
        if candidate.latest_first_reading_date > span_start
        and candidate.earliest_first_reading_date <= span_end
    )


def _merge_split_halves(head: _RuleBill, tail: _RuleBill) -> _RuleBill:
    return _RuleBill(
        tail.title,
        tail.title_key,
        head.first_sitting_date,
        tail.last_sitting_date,
        True,
        head.report_ids + tail.report_ids,
        head.first_reading_dates,
        head.printed_title_keys + tail.printed_title_keys,
    )


def _merge_split_bills(
    rule_bills: list[_RuleBill],
    title_key_to_candidates: dict[str, list[BillNumberCandidate]],
) -> _MergedRuleBills:
    head_candidates = _assign_bill_numbers(rule_bills, title_key_to_candidates)
    head_indexes = [
        index
        for index, rule_bill in enumerate(rule_bills)
        if not rule_bill.is_passed and rule_bill.first_reading_dates
    ]
    tail_indexes = [
        index
        for index, rule_bill in enumerate(rule_bills)
        if rule_bill.is_passed and not rule_bill.first_reading_dates
    ]
    head_index_to_tail_indexes = {
        head_index: [
            tail_index
            for tail_index in tail_indexes
            if _is_split_tail_of(rule_bills[head_index], rule_bills[tail_index])
        ]
        for head_index in head_indexes
    }
    tail_claim_counts = Counter(
        tail_indexes[0]
        for tail_indexes in head_index_to_tail_indexes.values()
        if len(tail_indexes) == 1
    )
    head_index_to_tail_index = {
        head_index: tail_indexes[0]
        for head_index, tail_indexes in head_index_to_tail_indexes.items()
        if len(tail_indexes) == 1
        and tail_claim_counts[tail_indexes[0]] == 1
        and not _is_number_conflict(
            rule_bills[head_index],
            rule_bills[tail_indexes[0]],
            head_candidates[head_index],
            title_key_to_candidates,
        )
    }
    merged_tail_indexes = set(head_index_to_tail_index.values())
    merged_rule_bills = [
        _merge_split_halves(rule_bill, rule_bills[head_index_to_tail_index[index]])
        if index in head_index_to_tail_index
        else rule_bill
        for index, rule_bill in enumerate(rule_bills)
        if index not in merged_tail_indexes
    ]
    split_merges = [
        SplitMerge(rule_bills[head_index].report_ids, rule_bills[tail_index].report_ids)
        for head_index, tail_index in head_index_to_tail_index.items()
    ]
    return _MergedRuleBills(merged_rule_bills, split_merges)


def _should_start_new_bill(
    open_bill: _RuleBill, sitting_date: datetime, is_first_reading: bool
) -> bool:
    if (
        open_bill.is_passed or is_first_reading
    ) and sitting_date > open_bill.last_sitting_date:
        return True
    return sitting_date - open_bill.last_sitting_date > timedelta(
        days=_MAX_DAYS_BETWEEN_REPORTS
    )


def _build_bill_group(
    rule_bill: _RuleBill,
    bill_number_candidate: Optional[BillNumberCandidate],
    act_number_candidate: Optional[ActNumberCandidate],
    repealed_act_candidate: Optional[RepealedActCandidate],
) -> BillGroup:
    return BillGroup(
        rule_bill.title,
        rule_bill.title_key,
        rule_bill.first_sitting_date,
        rule_bill.last_sitting_date,
        rule_bill.is_passed,
        rule_bill.report_ids,
        None if bill_number_candidate is None else bill_number_candidate.bill_number,
        None if bill_number_candidate is None else bill_number_candidate.source,
        get_bill_class(rule_bill.title_key),
        None if act_number_candidate is None else act_number_candidate.act_number,
        None if act_number_candidate is None else act_number_candidate.source,
        None if repealed_act_candidate is None else repealed_act_candidate.url,
        None if repealed_act_candidate is None else repealed_act_candidate.source,
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


def _build_hand_kept_rule_bill(
    hand_kept_bill: HandKeptBill,
    report_id_to_row: dict[int, ReportSittingDateTitleRow],
    first_reading_report_ids: frozenset[int],
    third_reading_report_ids: frozenset[int],
) -> _RuleBill:
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
    return _RuleBill(
        hand_kept_bill.title,
        get_title_key(hand_kept_bill.title),
        hand_kept_rows[0].sitting_date,
        hand_kept_rows[-1].sitting_date,
        any(report_row.id in third_reading_report_ids for report_row in hand_kept_rows),
        [report_row.id for report_row in hand_kept_rows],
        [
            report_row.sitting_date.date()
            for report_row in hand_kept_rows
            if report_row.id in first_reading_report_ids
        ],
        sorted({get_title_key(report_row.title) for report_row in hand_kept_rows}),
    )


def _validate_can_replace_rule_bills(
    hand_kept_bill: HandKeptBill, rule_bills: list[_RuleBill]
) -> None:
    hand_kept_report_ids = set(hand_kept_bill.report_ids)
    for rule_bill in rule_bills:
        group_report_ids = set(rule_bill.report_ids)
        if group_report_ids & hand_kept_report_ids and not (
            group_report_ids <= hand_kept_report_ids
        ):
            raise HansardHandKeptEntryError(
                f"hand_kept_bills.json: {hand_kept_bill.title!r} splits the bill "
                f"{rule_bill.title!r} of reports {rule_bill.report_ids}"
            )


def _group_rule_bills(
    report_rows: list[ReportSittingDateTitleRow],
    first_reading_report_ids: frozenset[int],
    third_reading_report_ids: frozenset[int],
) -> list[_RuleBill]:
    title_key_to_open_bill: dict[str, _RuleBill] = {}
    rule_bills: list[_RuleBill] = []
    for report_row in report_rows:
        if _BILL_WORD_PATTERN.search(report_row.title) is None:
            continue
        title_key = get_title_key(report_row.title)
        is_first_reading = report_row.id in first_reading_report_ids
        previous_bill = title_key_to_open_bill.get(title_key)
        if previous_bill is not None and _should_start_new_bill(
            previous_bill, report_row.sitting_date, is_first_reading
        ):
            rule_bills.append(previous_bill)
            del title_key_to_open_bill[title_key]
        open_bill = title_key_to_open_bill.setdefault(
            title_key,
            _RuleBill(
                report_row.title,
                title_key,
                report_row.sitting_date,
                report_row.sitting_date,
                False,
                [],
                [],
                [title_key],
            ),
        )
        open_bill.title = report_row.title
        open_bill.last_sitting_date = report_row.sitting_date
        open_bill.is_passed = (
            open_bill.is_passed or report_row.id in third_reading_report_ids
        )
        open_bill.report_ids.append(report_row.id)
        if is_first_reading:
            open_bill.first_reading_dates.append(report_row.sitting_date.date())
    rule_bills.extend(title_key_to_open_bill.values())
    return rule_bills


def group_bills(
    report_rows: list[ReportSittingDateTitleRow],
    first_reading_report_ids: frozenset[int],
    third_reading_report_ids: frozenset[int],
    title_corrections: list[BillTitleCorrection],
    hand_kept_bills: list[HandKeptBill],
    hand_kept_report_rows: list[ReportSittingDateTitleRow],
    bill_number_candidates: list[BillNumberCandidate],
    act_number_candidates: list[ActNumberCandidate],
    repealed_act_candidates: list[RepealedActCandidate],
) -> BillGrouping:
    corrected_report_rows = _build_corrected_report_rows(report_rows, title_corrections)
    skipped_report_rows = [
        report_row
        for report_row in corrected_report_rows
        if _BILL_WORD_PATTERN.search(report_row.title) is None
    ]
    title_key_to_candidates = _build_title_key_to_candidates(bill_number_candidates)
    merged_rule_bills = _merge_split_bills(
        _group_rule_bills(
            corrected_report_rows, first_reading_report_ids, third_reading_report_ids
        ),
        title_key_to_candidates,
    )
    rule_bills = merged_rule_bills.rule_bills
    split_merges = merged_rule_bills.split_merges
    report_id_to_row = {
        report_row.id: report_row for report_row in hand_kept_report_rows
    }
    hand_kept_report_ids = {
        report_id
        for hand_kept_bill in hand_kept_bills
        for report_id in hand_kept_bill.report_ids
    }
    for hand_kept_bill in hand_kept_bills:
        _validate_can_replace_rule_bills(hand_kept_bill, rule_bills)
    rule_bills = [
        rule_bill
        for rule_bill in rule_bills
        if hand_kept_report_ids.isdisjoint(rule_bill.report_ids)
    ] + [
        _build_hand_kept_rule_bill(
            hand_kept_bill,
            report_id_to_row,
            first_reading_report_ids,
            third_reading_report_ids,
        )
        for hand_kept_bill in hand_kept_bills
    ]
    bill_number_candidates_by_bill = _assign_bill_numbers(
        rule_bills, title_key_to_candidates
    )
    bill_groups = [
        _build_bill_group(
            rule_bill,
            bill_number_candidate,
            _get_act_number_candidate(rule_bill, act_number_candidates),
            _get_repealed_act_candidate(rule_bill, repealed_act_candidates),
        )
        for rule_bill, bill_number_candidate in zip(
            rule_bills, bill_number_candidates_by_bill, strict=True
        )
    ]
    return BillGrouping(
        sorted(
            bill_groups,
            key=lambda bill_group: (
                bill_group.first_sitting_date,
                bill_group.report_ids[0],
            ),
        ),
        [
            report_row
            for report_row in skipped_report_rows
            if report_row.id not in hand_kept_report_ids
        ],
        split_merges,
    )

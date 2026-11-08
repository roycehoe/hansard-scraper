from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.act import CRUDAct
from crud.act_history_entry import CRUDActHistoryEntry
from crud.acts_supplement_entry import CRUDActsSupplementEntry
from crud.bill import CRUDBill
from crud.bill_report import CRUDBillReport
from crud.bills_supplement_entry import CRUDBillsSupplementEntry
from crud.egazette_supplement import CRUDEgazetteSupplement, EgazetteSupplementRow
from crud.repealed_act_entry import CRUDRepealedActEntry
from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.act import Act, ActHistoryEntry
from database.bill import Bill, BillReport
from enums import (
    ActHistoryEntryKind,
    BillLinkSource,
    EgazetteSupplementKind,
    ReportType,
)
from exceptions import HansardActHistoryError
from schemas.act_link_plan import (
    ActLinkPlan,
    PlannedAct,
    PlannedActHistoryEntry,
    PlannedBill,
    PlannedEgazetteLink,
    PlannedSplitMerge,
    SkippedReport,
    UnparsedEntry,
)
from schemas.bill_title_correction import BillTitleCorrection
from schemas.hand_kept_act_link import HandKeptActLink
from schemas.hand_kept_bill import HandKeptBill
from schemas.harvested_act import HarvestedAct, HarvestedActs
from services.act_history import (
    ParsedHistoryEntry,
    parse_history_entry,
    split_history_entries,
)
from services.act_link import (
    BillLink,
    BillLookups,
    LinkableBill,
    build_bill_lookups,
    get_bill_link,
    get_bill_number_link_index,
    get_hand_kept_bill_link,
    validate_can_find_hand_kept_act_links,
)
from services.act_link_write import ActLinkWrite, build_act_link_write
from services.bill import (
    BILL_TITLE_END_PATTERN,
    FIRST_READING_PATTERN,
    NOT_FIRST_READING_PATTERNS,
    NOT_THIRD_READING_PATTERNS,
    SECOND_READING_PATTERN,
    THIRD_READING_PATTERN,
    ActNumberCandidate,
    BillGrouping,
    BillNumberCandidate,
    RepealedActCandidate,
    build_acts_supplement_act_number_candidate,
    build_egazette_bill_number_candidate,
    build_listing_bill_number_candidate,
    build_repealed_acts_listing_candidate,
    group_bills,
    is_other_type_bill_reading,
    is_publication_date_misprinted,
)
from utils.act_link_update import ActHistoryEntryUpdate
from utils.egazette_supplement_update import EgazetteLinkUpdate

_BILL_REPORT_TYPES = (ReportType.BILL, ReportType.BILL_INTRODUCTION)
_HARVEST_LISTING_FILE = "acts.json"


@dataclass(frozen=True)
class BillGroupingContext:
    bill_grouping: BillGrouping
    report_id_to_sitting_date: dict[int, date]
    first_reading_report_ids: frozenset[int]
    third_reading_report_ids: frozenset[int]
    egazette_supplement_rows: list[EgazetteSupplementRow]


def _is_linkable_kind(kind: ActHistoryEntryKind) -> bool:
    if kind == ActHistoryEntryKind.ACT:
        return True
    return kind == ActHistoryEntryKind.ORDINANCE


def _get_entry_bill_link(
    sso_code: str,
    parsed_entry: ParsedHistoryEntry,
    bill_lookups: BillLookups,
    hand_kept_act_links: list[HandKeptActLink],
    bill_report_ids: list[list[int]],
) -> Optional[BillLink]:
    if not _is_linkable_kind(parsed_entry.kind):
        return None
    hand_kept_bill_link = get_hand_kept_bill_link(
        sso_code,
        parsed_entry.ordinal,
        parsed_entry.printed_title,
        hand_kept_act_links,
        bill_report_ids,
    )
    if hand_kept_bill_link is not None:
        return hand_kept_bill_link
    return get_bill_link(
        parsed_entry.printed_title,
        parsed_entry.first_reading_date,
        parsed_entry.second_reading_date,
        parsed_entry.third_reading_date,
        bill_lookups,
    )


def _get_entry_bill_number_bill_index(
    parsed_entry: ParsedHistoryEntry, bill_lookups: BillLookups
) -> Optional[int]:
    if not _is_linkable_kind(parsed_entry.kind):
        return None
    return get_bill_number_link_index(
        parsed_entry.printed_bill_number,
        parsed_entry.first_reading_date,
        bill_lookups,
    )


def _build_planned_entry(
    sso_code: str,
    parsed_entry: ParsedHistoryEntry,
    bill_lookups: BillLookups,
    hand_kept_act_links: list[HandKeptActLink],
    bill_report_ids: list[list[int]],
) -> PlannedActHistoryEntry:
    bill_link = _get_entry_bill_link(
        sso_code, parsed_entry, bill_lookups, hand_kept_act_links, bill_report_ids
    )
    return PlannedActHistoryEntry(
        ordinal=parsed_entry.ordinal,
        printed_text=parsed_entry.printed_text,
        printed_law_number=parsed_entry.printed_law_number,
        printed_title=parsed_entry.printed_title,
        printed_bill_number=parsed_entry.printed_bill_number,
        first_reading_date=parsed_entry.first_reading_date,
        second_reading_date=parsed_entry.second_reading_date,
        third_reading_date=parsed_entry.third_reading_date,
        commencement_date=parsed_entry.commencement_date,
        kind=parsed_entry.kind,
        defects=parsed_entry.defects,
        bill_index=None if bill_link is None else bill_link.bill_index,
        bill_link_source=None if bill_link is None else bill_link.source,
        bill_number_bill_index=_get_entry_bill_number_bill_index(
            parsed_entry, bill_lookups
        ),
    )


def _build_planned_act(
    harvested_act: HarvestedAct,
    text: str,
    bill_lookups: BillLookups,
    hand_kept_act_links: list[HandKeptActLink],
    bill_report_ids: list[list[int]],
    unparsed_entries: list[UnparsedEntry],
) -> PlannedAct:
    entries: list[PlannedActHistoryEntry] = []
    try:
        blocks = split_history_entries(harvested_act.sso_code, text)
    except HansardActHistoryError as error:
        unparsed_entries.append(
            UnparsedEntry(sso_code=harvested_act.sso_code, message=str(error))
        )
        return PlannedAct(
            sso_code=harvested_act.sso_code, title=harvested_act.title, entries=entries
        )
    for block in blocks:
        try:
            parsed_entry = parse_history_entry(harvested_act.sso_code, block)
        except HansardActHistoryError as error:
            unparsed_entries.append(
                UnparsedEntry(sso_code=harvested_act.sso_code, message=str(error))
            )
            continue
        entries.append(
            _build_planned_entry(
                harvested_act.sso_code,
                parsed_entry,
                bill_lookups,
                hand_kept_act_links,
                bill_report_ids,
            )
        )
    return PlannedAct(
        sso_code=harvested_act.sso_code, title=harvested_act.title, entries=entries
    )


def _build_bill_number_candidates(
    session: Session, egazette_supplement_rows: list[EgazetteSupplementRow]
) -> list[BillNumberCandidate]:
    return [
        build_listing_bill_number_candidate(
            entry_row.printed_title, entry_row.bill_number, entry_row.publication_date
        )
        for entry_row in CRUDBillsSupplementEntry(session).get_rows()
        if not is_publication_date_misprinted(
            entry_row.bill_number, entry_row.publication_date
        )
    ] + [
        build_egazette_bill_number_candidate(
            egazette_supplement_row.printed_title,
            egazette_supplement_row.bill_number,
            egazette_supplement_row.first_reading_date,
        )
        for egazette_supplement_row in egazette_supplement_rows
        if egazette_supplement_row.supplement_kind == EgazetteSupplementKind.BILLS
    ]


def _build_act_number_candidates(session: Session) -> list[ActNumberCandidate]:
    return [
        build_acts_supplement_act_number_candidate(
            entry_row.printed_title, entry_row.act_number, entry_row.publication_date
        )
        for entry_row in CRUDActsSupplementEntry(session).get_rows()
    ]


def _build_repealed_act_candidates(session: Session) -> list[RepealedActCandidate]:
    return [
        build_repealed_acts_listing_candidate(
            entry_row.printed_title,
            entry_row.sso_code,
            entry_row.enactment_year,
            entry_row.repeal_date,
            entry_row.link,
        )
        for entry_row in CRUDRepealedActEntry(session).get_rows()
        if entry_row.enactment_year is not None
    ]


def get_bill_grouping_context(
    session: Session,
    bill_title_corrections: list[BillTitleCorrection],
    hand_kept_bills: list[HandKeptBill],
) -> BillGroupingContext:
    bill_type_report_rows = CRUDReport(
        session
    ).get_sitting_date_title_rows_by_report_types(_BILL_REPORT_TYPES)
    other_type_report_rows = CRUDReport(
        session
    ).get_sitting_date_title_rows_by_report_types_not_in_and_title_regex(
        _BILL_REPORT_TYPES, BILL_TITLE_END_PATTERN
    )
    hand_kept_report_ids = [
        report_id
        for hand_kept_bill in hand_kept_bills
        for report_id in hand_kept_bill.report_ids
    ]
    hand_kept_report_rows = CRUDReport(session).get_sitting_date_title_rows_by_ids(
        hand_kept_report_ids
    )
    other_report_ids = [
        report_row.id for report_row in other_type_report_rows
    ] + hand_kept_report_ids
    first_reading_report_ids = frozenset(
        CRUDSpeech(
            session
        ).get_report_ids_by_report_types_and_transcript_regex_and_transcript_not_regexes(
            _BILL_REPORT_TYPES, FIRST_READING_PATTERN, NOT_FIRST_READING_PATTERNS
        )
    ) | frozenset(
        CRUDSpeech(
            session
        ).get_report_ids_by_report_ids_and_transcript_regex_and_transcript_not_regexes(
            other_report_ids, FIRST_READING_PATTERN, NOT_FIRST_READING_PATTERNS
        )
    )
    third_reading_report_ids = frozenset(
        CRUDSpeech(
            session
        ).get_report_ids_by_report_types_and_transcript_regex_and_transcript_not_regexes(
            _BILL_REPORT_TYPES, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
        )
    ) | frozenset(
        CRUDSpeech(
            session
        ).get_report_ids_by_report_ids_and_transcript_regex_and_transcript_not_regexes(
            other_report_ids, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
        )
    )
    second_reading_report_ids = frozenset(
        CRUDSpeech(
            session
        ).get_report_ids_by_report_ids_and_transcript_regex_and_transcript_not_regexes(
            other_report_ids, SECOND_READING_PATTERN, ()
        )
    )
    report_rows = sorted(
        bill_type_report_rows
        + [
            report_row
            for report_row in other_type_report_rows
            if is_other_type_bill_reading(
                report_row.title,
                report_row.id in first_reading_report_ids,
                report_row.id in second_reading_report_ids,
                report_row.id in third_reading_report_ids,
            )
        ],
        key=lambda report_row: (report_row.sitting_date, report_row.id),
    )
    egazette_supplement_rows = CRUDEgazetteSupplement(session).get_rows()
    bill_grouping = group_bills(
        report_rows,
        first_reading_report_ids,
        third_reading_report_ids,
        bill_title_corrections,
        hand_kept_bills,
        hand_kept_report_rows,
        _build_bill_number_candidates(session, egazette_supplement_rows),
        _build_act_number_candidates(session),
        _build_repealed_act_candidates(session),
    )
    return BillGroupingContext(
        bill_grouping,
        {
            report_row.id: report_row.sitting_date.date()
            for report_row in report_rows + hand_kept_report_rows
        },
        first_reading_report_ids,
        third_reading_report_ids,
        egazette_supplement_rows,
    )


def build_bill_lookups_from_context(context: BillGroupingContext) -> BillLookups:
    title_key_to_linkable_bills: dict[str, list[LinkableBill]] = defaultdict(list)
    bill_number_to_linkable_bills: dict[str, list[LinkableBill]] = defaultdict(list)
    for bill_index, bill_group in enumerate(context.bill_grouping.bill_groups):
        linkable_bill = LinkableBill(
            bill_index,
            [
                context.report_id_to_sitting_date[report_id]
                for report_id in bill_group.report_ids
            ],
        )
        title_key_to_linkable_bills[bill_group.title_key].append(linkable_bill)
        if bill_group.bill_number is not None:
            bill_number_to_linkable_bills[bill_group.bill_number].append(linkable_bill)
    return build_bill_lookups(
        title_key_to_linkable_bills, bill_number_to_linkable_bills
    )


def _get_egazette_link_bill_index(
    egazette_supplement_row: EgazetteSupplementRow,
    bill_lookups: BillLookups,
    context: BillGroupingContext,
) -> Optional[int]:
    if egazette_supplement_row.passing_date is None:
        return None
    linkable_bills = bill_lookups.bill_number_to_linkable_bills.get(
        egazette_supplement_row.bill_number
    )
    if linkable_bills is None:
        return None
    passing_bill_indexes = [
        linkable_bill.bill_index
        for linkable_bill in linkable_bills
        if any(
            report_id in context.third_reading_report_ids
            and context.report_id_to_sitting_date[report_id]
            == egazette_supplement_row.passing_date
            for report_id in context.bill_grouping.bill_groups[
                linkable_bill.bill_index
            ].report_ids
        )
    ]
    if len(passing_bill_indexes) != 1:
        return None
    return passing_bill_indexes[0]


def _build_egazette_links(
    context: BillGroupingContext, bill_lookups: BillLookups
) -> list[PlannedEgazetteLink]:
    egazette_links: list[PlannedEgazetteLink] = []
    for egazette_supplement_row in context.egazette_supplement_rows:
        if egazette_supplement_row.supplement_kind != EgazetteSupplementKind.ACTS:
            continue
        bill_index = _get_egazette_link_bill_index(
            egazette_supplement_row, bill_lookups, context
        )
        if bill_index is None:
            continue
        egazette_links.append(
            PlannedEgazetteLink(url=egazette_supplement_row.url, bill_index=bill_index)
        )
    return egazette_links


def get_act_link_plan(
    session: Session,
    harvest_directory: Path,
    bill_title_corrections: list[BillTitleCorrection],
    hand_kept_bills: list[HandKeptBill],
    hand_kept_act_links: list[HandKeptActLink],
) -> ActLinkPlan:
    context = get_bill_grouping_context(
        session, bill_title_corrections, hand_kept_bills
    )
    bill_grouping = context.bill_grouping
    bill_lookups = build_bill_lookups_from_context(context)
    harvested_acts = HarvestedActs.model_validate_json(
        (harvest_directory / _HARVEST_LISTING_FILE).read_text(encoding="utf8")
    )
    acts: list[PlannedAct] = []
    unfetched_sso_codes: list[str] = []
    unparsed_entries: list[UnparsedEntry] = []
    for harvested_act in harvested_acts.root:
        try:
            text = (harvest_directory / f"{harvested_act.sso_code}.txt").read_text(
                encoding="utf8"
            )
        except FileNotFoundError:
            unfetched_sso_codes.append(harvested_act.sso_code)
            continue
        acts.append(
            _build_planned_act(
                harvested_act,
                text,
                bill_lookups,
                hand_kept_act_links,
                [bill_group.report_ids for bill_group in bill_grouping.bill_groups],
                unparsed_entries,
            )
        )
    validate_can_find_hand_kept_act_links(
        hand_kept_act_links,
        {
            (planned_act.sso_code, planned_entry.ordinal)
            for planned_act in acts
            for planned_entry in planned_act.entries
            if planned_entry.bill_link_source == BillLinkSource.HAND_KEPT
        },
    )
    return ActLinkPlan(
        bills=[
            PlannedBill(
                title=bill_group.title,
                title_key=bill_group.title_key,
                first_sitting_date=bill_group.first_sitting_date,
                last_sitting_date=bill_group.last_sitting_date,
                is_passed=bill_group.is_passed,
                report_ids=bill_group.report_ids,
                bill_number=bill_group.bill_number,
                bill_number_source=bill_group.bill_number_source,
                bill_class=bill_group.bill_class,
                act_number=bill_group.act_number,
                act_number_source=bill_group.act_number_source,
                repealed_act_url=bill_group.repealed_act_url,
                repealed_act_url_source=bill_group.repealed_act_url_source,
            )
            for bill_group in bill_grouping.bill_groups
        ],
        split_merges=[
            PlannedSplitMerge(
                head_report_ids=split_merge.head_report_ids,
                tail_report_ids=split_merge.tail_report_ids,
            )
            for split_merge in bill_grouping.split_merges
        ],
        skipped_reports=[
            SkippedReport(report_id=report_row.id, title=report_row.title)
            for report_row in bill_grouping.skipped_report_rows
        ],
        egazette_links=_build_egazette_links(context, bill_lookups),
        acts=acts,
        unfetched_sso_codes=unfetched_sso_codes,
        unparsed_entries=unparsed_entries,
    )


def get_act_link_write(session: Session, plan: ActLinkPlan) -> ActLinkWrite:
    return build_act_link_write(
        CRUDBill(session).get_rows(),
        CRUDBillReport(session).get_rows(),
        CRUDAct(session).get_rows(),
        CRUDActHistoryEntry(session).get_rows(),
        CRUDEgazetteSupplement(session).get_rows(),
        plan,
    )


def _get_bill_id(
    bill_index_to_id: dict[int, int], bill_index: Optional[int]
) -> Optional[int]:
    if bill_index is None:
        return None
    return bill_index_to_id[bill_index]


def write_act_link_plan(
    session: Session, plan: ActLinkPlan, act_link_write: ActLinkWrite
) -> None:
    new_bills = [
        Bill(
            title=plan.bills[bill_index].title,
            title_key=plan.bills[bill_index].title_key,
            first_sitting_date=plan.bills[bill_index].first_sitting_date,
            last_sitting_date=plan.bills[bill_index].last_sitting_date,
            is_passed=plan.bills[bill_index].is_passed,
            bill_number=plan.bills[bill_index].bill_number,
            bill_number_source=plan.bills[bill_index].bill_number_source,
            bill_class=plan.bills[bill_index].bill_class,
            act_number=plan.bills[bill_index].act_number,
            act_number_source=plan.bills[bill_index].act_number_source,
            repealed_act_url=plan.bills[bill_index].repealed_act_url,
            repealed_act_url_source=plan.bills[bill_index].repealed_act_url_source,
        )
        for bill_index in act_link_write.bill_indexes_to_insert
    ]
    CRUDBill(session).add_many(new_bills)
    CRUDBillReport(session).add_many(
        [
            BillReport(bill_id=new_bill.id, report_id=report_id)
            for new_bill, bill_index in zip(
                new_bills, act_link_write.bill_indexes_to_insert, strict=True
            )
            if new_bill.id is not None
            for report_id in plan.bills[bill_index].report_ids
        ]
    )
    CRUDBill(session).update_many(act_link_write.bill_updates)
    bill_index_to_id = dict(act_link_write.kept_bill_index_to_id)
    for new_bill, bill_index in zip(
        new_bills, act_link_write.bill_indexes_to_insert, strict=True
    ):
        if new_bill.id is not None:
            bill_index_to_id[bill_index] = new_bill.id

    new_acts = [
        Act(sso_code=planned_act.sso_code, title=planned_act.title)
        for planned_act in act_link_write.acts_to_insert
    ]
    CRUDAct(session).add_many(new_acts)
    CRUDAct(session).update_many(act_link_write.act_updates)
    sso_code_to_act_id = dict(act_link_write.kept_sso_code_to_act_id)
    for new_act in new_acts:
        if new_act.id is not None:
            sso_code_to_act_id[new_act.sso_code] = new_act.id

    CRUDActHistoryEntry(session).add_many(
        [
            ActHistoryEntry(
                ordinal=entry_insert.planned_entry.ordinal,
                printed_text=entry_insert.planned_entry.printed_text,
                printed_law_number=entry_insert.planned_entry.printed_law_number,
                printed_title=entry_insert.planned_entry.printed_title,
                printed_bill_number=entry_insert.planned_entry.printed_bill_number,
                first_reading_date=entry_insert.planned_entry.first_reading_date,
                second_reading_date=entry_insert.planned_entry.second_reading_date,
                third_reading_date=entry_insert.planned_entry.third_reading_date,
                commencement_date=entry_insert.planned_entry.commencement_date,
                kind=entry_insert.planned_entry.kind,
                bill_link_source=entry_insert.planned_entry.bill_link_source,
                act_id=sso_code_to_act_id[entry_insert.sso_code],
                bill_id=_get_bill_id(
                    bill_index_to_id, entry_insert.planned_entry.bill_index
                ),
            )
            for entry_insert in act_link_write.entries_to_insert
        ]
    )
    CRUDActHistoryEntry(session).update_many(
        [
            ActHistoryEntryUpdate(
                id=entry_update.id,
                printed_text=entry_update.planned_entry.printed_text,
                printed_law_number=entry_update.planned_entry.printed_law_number,
                printed_title=entry_update.planned_entry.printed_title,
                printed_bill_number=entry_update.planned_entry.printed_bill_number,
                first_reading_date=entry_update.planned_entry.first_reading_date,
                second_reading_date=entry_update.planned_entry.second_reading_date,
                third_reading_date=entry_update.planned_entry.third_reading_date,
                commencement_date=entry_update.planned_entry.commencement_date,
                kind=entry_update.planned_entry.kind,
                bill_link_source=entry_update.planned_entry.bill_link_source,
                bill_id=_get_bill_id(
                    bill_index_to_id, entry_update.planned_entry.bill_index
                ),
            )
            for entry_update in act_link_write.entry_updates
        ]
    )
    url_to_planned_bill_index = {
        egazette_link.url: egazette_link.bill_index
        for egazette_link in plan.egazette_links
    }
    stored_egazette_id_to_url = {
        egazette_supplement_row.id: egazette_supplement_row.url
        for egazette_supplement_row in CRUDEgazetteSupplement(session).get_rows()
    }
    CRUDEgazetteSupplement(session).set_bill_links_bulk(
        [
            EgazetteLinkUpdate(
                egazette_link_update.id,
                _get_bill_id(
                    bill_index_to_id,
                    url_to_planned_bill_index.get(
                        stored_egazette_id_to_url[egazette_link_update.id]
                    ),
                ),
                egazette_link_update.bill_link_source,
            )
            for egazette_link_update in act_link_write.egazette_link_updates
        ]
    )

    CRUDActHistoryEntry(session).delete_by_ids(act_link_write.entry_ids_to_delete)
    CRUDAct(session).delete_by_ids(act_link_write.act_ids_to_delete)
    CRUDBillReport(session).delete_by_bill_ids(act_link_write.bill_ids_to_delete)
    CRUDBill(session).delete_by_ids(act_link_write.bill_ids_to_delete)

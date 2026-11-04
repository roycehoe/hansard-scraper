from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.act import CRUDAct
from crud.act_history_entry import CRUDActHistoryEntry
from crud.bill import CRUDBill
from crud.bill_report import CRUDBillReport
from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.act import Act, ActHistoryEntry
from database.bill import Bill, BillReport
from enums import ActHistoryEntryKind, ReportType
from exceptions import HansardActHistoryError
from schemas.act_link_plan import (
    ActLinkPlan,
    PlannedAct,
    PlannedActHistoryEntry,
    PlannedBill,
    SkippedReport,
    UnparsedEntry,
)
from schemas.harvested_act import HarvestedAct, HarvestedActs
from services.act_history import (
    ParsedHistoryEntry,
    parse_history_entry,
    split_history_entries,
)
from services.act_link import LinkableBill, get_bill_link
from services.bill import (
    NOT_THIRD_READING_PATTERNS,
    THIRD_READING_PATTERN,
    group_bills,
)

_BILL_REPORT_TYPES = (ReportType.BILL, ReportType.BILL_INTRODUCTION)
_HARVEST_LISTING_FILE = "acts.json"


def _build_planned_entry(
    parsed_entry: ParsedHistoryEntry,
    title_key_to_linkable_bills: dict[str, list[LinkableBill]],
) -> PlannedActHistoryEntry:
    bill_link = None
    if (
        parsed_entry.kind == ActHistoryEntryKind.ACT
        or parsed_entry.kind == ActHistoryEntryKind.ORDINANCE
    ):
        bill_link = get_bill_link(
            parsed_entry.printed_title,
            parsed_entry.first_reading_date,
            parsed_entry.second_reading_date,
            parsed_entry.third_reading_date,
            title_key_to_linkable_bills,
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
    )


def _build_planned_act(
    harvested_act: HarvestedAct,
    text: str,
    title_key_to_linkable_bills: dict[str, list[LinkableBill]],
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
        entries.append(_build_planned_entry(parsed_entry, title_key_to_linkable_bills))
    return PlannedAct(
        sso_code=harvested_act.sso_code, title=harvested_act.title, entries=entries
    )


def get_act_link_plan(session: Session, harvest_directory: Path) -> ActLinkPlan:
    report_rows = CRUDReport(session).get_sitting_date_title_rows_by_report_types(
        _BILL_REPORT_TYPES
    )
    third_reading_report_ids = CRUDSpeech(
        session
    ).get_report_ids_by_report_types_and_transcript_regex_and_transcript_not_regexes(
        _BILL_REPORT_TYPES, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
    )
    bill_grouping = group_bills(report_rows, frozenset(third_reading_report_ids))
    report_id_to_sitting_date: dict[int, date] = {
        report_row.id: report_row.sitting_date.date() for report_row in report_rows
    }
    title_key_to_linkable_bills: dict[str, list[LinkableBill]] = defaultdict(list)
    for bill_index, bill_group in enumerate(bill_grouping.bill_groups):
        title_key_to_linkable_bills[bill_group.title_key].append(
            LinkableBill(
                bill_index,
                [
                    report_id_to_sitting_date[report_id]
                    for report_id in bill_group.report_ids
                ],
            )
        )
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
                harvested_act, text, title_key_to_linkable_bills, unparsed_entries
            )
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
            )
            for bill_group in bill_grouping.bill_groups
        ],
        skipped_reports=[
            SkippedReport(report_id=report_row.id, title=report_row.title)
            for report_row in bill_grouping.skipped_report_rows
        ],
        acts=acts,
        unfetched_sso_codes=unfetched_sso_codes,
        unparsed_entries=unparsed_entries,
    )


def _get_bill_id(bills: list[Bill], bill_index: Optional[int]) -> Optional[int]:
    if bill_index is None:
        return None
    return bills[bill_index].id


def write_act_link_plan(session: Session, plan: ActLinkPlan) -> None:
    bills = [
        Bill(
            title=planned_bill.title,
            title_key=planned_bill.title_key,
            first_sitting_date=planned_bill.first_sitting_date,
            last_sitting_date=planned_bill.last_sitting_date,
            is_passed=planned_bill.is_passed,
        )
        for planned_bill in plan.bills
    ]
    CRUDBill(session).add_many(bills)
    CRUDBillReport(session).add_many(
        [
            BillReport(bill_id=bill.id, report_id=report_id)
            for bill, planned_bill in zip(bills, plan.bills, strict=True)
            if bill.id is not None
            for report_id in planned_bill.report_ids
        ]
    )
    acts = [
        Act(sso_code=planned_act.sso_code, title=planned_act.title)
        for planned_act in plan.acts
    ]
    CRUDAct(session).add_many(acts)
    CRUDActHistoryEntry(session).add_many(
        [
            ActHistoryEntry(
                ordinal=planned_entry.ordinal,
                printed_text=planned_entry.printed_text,
                printed_law_number=planned_entry.printed_law_number,
                printed_title=planned_entry.printed_title,
                printed_bill_number=planned_entry.printed_bill_number,
                first_reading_date=planned_entry.first_reading_date,
                second_reading_date=planned_entry.second_reading_date,
                third_reading_date=planned_entry.third_reading_date,
                commencement_date=planned_entry.commencement_date,
                kind=planned_entry.kind,
                bill_link_source=planned_entry.bill_link_source,
                act_id=act.id,
                bill_id=_get_bill_id(bills, planned_entry.bill_index),
            )
            for act, planned_act in zip(acts, plan.acts, strict=True)
            if act.id is not None
            for planned_entry in planned_act.entries
        ]
    )

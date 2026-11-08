from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from crud.act import ActRow
from crud.act_history_entry import ActHistoryEntryRow
from crud.bill import BillRow
from crud.bill_report import BillReportRow
from crud.egazette_supplement import EgazetteSupplementRow
from enums import BillLinkSource
from schemas.act_link_plan import ActLinkPlan, PlannedAct, PlannedActHistoryEntry
from utils.act_link_update import ActUpdate, BillUpdate
from utils.egazette_supplement_update import EgazetteLinkUpdate


@dataclass(frozen=True)
class EntryInsert:
    sso_code: str
    planned_entry: PlannedActHistoryEntry


@dataclass(frozen=True)
class EntryUpdate:
    id: int
    sso_code: str
    planned_entry: PlannedActHistoryEntry
    is_bill_changed: bool


@dataclass(frozen=True)
class ActLinkWrite:
    kept_bill_index_to_id: dict[int, int]
    bill_indexes_to_insert: list[int]
    bill_updates: list[BillUpdate]
    bill_ids_to_delete: list[int]
    kept_sso_code_to_act_id: dict[str, int]
    acts_to_insert: list[PlannedAct]
    act_updates: list[ActUpdate]
    act_ids_to_delete: list[int]
    entries_to_insert: list[EntryInsert]
    entry_updates: list[EntryUpdate]
    entry_ids_to_delete: list[int]
    egazette_link_updates: list[EgazetteLinkUpdate]


def _is_entry_equal_to_plan(
    stored_entry: ActHistoryEntryRow,
    planned_entry: PlannedActHistoryEntry,
    planned_bill_id: Optional[int],
) -> bool:
    return (
        stored_entry.printed_text == planned_entry.printed_text
        and stored_entry.printed_law_number == planned_entry.printed_law_number
        and stored_entry.printed_title == planned_entry.printed_title
        and stored_entry.printed_bill_number == planned_entry.printed_bill_number
        and stored_entry.first_reading_date == planned_entry.first_reading_date
        and stored_entry.second_reading_date == planned_entry.second_reading_date
        and stored_entry.third_reading_date == planned_entry.third_reading_date
        and stored_entry.commencement_date == planned_entry.commencement_date
        and stored_entry.kind == planned_entry.kind
        and stored_entry.bill_link_source == planned_entry.bill_link_source
        and stored_entry.bill_id == planned_bill_id
    )


def build_act_link_write(
    stored_bills: list[BillRow],
    stored_bill_reports: list[BillReportRow],
    stored_acts: list[ActRow],
    stored_entries: list[ActHistoryEntryRow],
    stored_egazette_supplements: list[EgazetteSupplementRow],
    plan: ActLinkPlan,
) -> ActLinkWrite:
    bill_id_to_report_ids: dict[int, list[int]] = defaultdict(list)
    for stored_bill_report in stored_bill_reports:
        bill_id_to_report_ids[stored_bill_report.bill_id].append(
            stored_bill_report.report_id
        )
    report_ids_to_stored_bill: dict[tuple[int, ...], BillRow] = {
        tuple(bill_id_to_report_ids[stored_bill.id]): stored_bill
        for stored_bill in stored_bills
    }

    kept_bill_index_to_id: dict[int, int] = {}
    bill_indexes_to_insert: list[int] = []
    bill_updates: list[BillUpdate] = []
    for bill_index, planned_bill in enumerate(plan.bills):
        stored_bill = report_ids_to_stored_bill.get(tuple(planned_bill.report_ids))
        if stored_bill is None:
            bill_indexes_to_insert.append(bill_index)
            continue
        kept_bill_index_to_id[bill_index] = stored_bill.id
        if (
            stored_bill.title != planned_bill.title
            or stored_bill.title_key != planned_bill.title_key
            or stored_bill.first_sitting_date != planned_bill.first_sitting_date
            or stored_bill.last_sitting_date != planned_bill.last_sitting_date
            or stored_bill.is_passed != planned_bill.is_passed
            or stored_bill.bill_number != planned_bill.bill_number
            or stored_bill.bill_number_source != planned_bill.bill_number_source
            or stored_bill.bill_class != planned_bill.bill_class
            or stored_bill.act_number != planned_bill.act_number
            or stored_bill.act_number_source != planned_bill.act_number_source
            or stored_bill.repealed_act_url != planned_bill.repealed_act_url
            or stored_bill.repealed_act_url_source
            != planned_bill.repealed_act_url_source
        ):
            bill_updates.append(
                BillUpdate(
                    id=stored_bill.id,
                    title=planned_bill.title,
                    title_key=planned_bill.title_key,
                    first_sitting_date=planned_bill.first_sitting_date,
                    last_sitting_date=planned_bill.last_sitting_date,
                    is_passed=planned_bill.is_passed,
                    bill_number=planned_bill.bill_number,
                    bill_number_source=planned_bill.bill_number_source,
                    bill_class=planned_bill.bill_class,
                    act_number=planned_bill.act_number,
                    act_number_source=planned_bill.act_number_source,
                    repealed_act_url=planned_bill.repealed_act_url,
                    repealed_act_url_source=planned_bill.repealed_act_url_source,
                )
            )
    kept_bill_ids = set(kept_bill_index_to_id.values())
    bill_ids_to_delete = [
        stored_bill.id
        for stored_bill in stored_bills
        if stored_bill.id not in kept_bill_ids
    ]

    sso_code_to_stored_act = {
        stored_act.sso_code: stored_act for stored_act in stored_acts
    }
    act_id_to_sso_code = {
        stored_act.id: stored_act.sso_code for stored_act in stored_acts
    }
    planned_sso_codes = {planned_act.sso_code for planned_act in plan.acts}
    kept_sso_code_to_act_id: dict[str, int] = {}
    acts_to_insert: list[PlannedAct] = []
    act_updates: list[ActUpdate] = []
    for planned_act in plan.acts:
        stored_act = sso_code_to_stored_act.get(planned_act.sso_code)
        if stored_act is None:
            acts_to_insert.append(planned_act)
            continue
        kept_sso_code_to_act_id[planned_act.sso_code] = stored_act.id
        if stored_act.title != planned_act.title:
            act_updates.append(ActUpdate(id=stored_act.id, title=planned_act.title))
    act_ids_to_delete = [
        stored_act.id
        for stored_act in stored_acts
        if stored_act.sso_code not in planned_sso_codes
    ]

    sso_code_and_ordinal_to_stored_entry = {
        (act_id_to_sso_code[stored_entry.act_id], stored_entry.ordinal): stored_entry
        for stored_entry in stored_entries
    }
    planned_entry_keys: set[tuple[str, int]] = set()
    entries_to_insert: list[EntryInsert] = []
    entry_updates: list[EntryUpdate] = []
    for planned_act in plan.acts:
        for planned_entry in planned_act.entries:
            entry_key = (planned_act.sso_code, planned_entry.ordinal)
            planned_entry_keys.add(entry_key)
            stored_entry = sso_code_and_ordinal_to_stored_entry.get(entry_key)
            if stored_entry is None:
                entries_to_insert.append(
                    EntryInsert(planned_act.sso_code, planned_entry)
                )
                continue
            planned_bill_id = (
                None
                if planned_entry.bill_index is None
                else kept_bill_index_to_id.get(planned_entry.bill_index)
            )
            is_bill_new = (
                planned_entry.bill_index is not None and planned_bill_id is None
            )
            if not is_bill_new and _is_entry_equal_to_plan(
                stored_entry, planned_entry, planned_bill_id
            ):
                continue
            entry_updates.append(
                EntryUpdate(
                    id=stored_entry.id,
                    sso_code=planned_act.sso_code,
                    planned_entry=planned_entry,
                    is_bill_changed=stored_entry.bill_id is not None
                    and stored_entry.bill_id != planned_bill_id,
                )
            )
    entry_ids_to_delete = [
        stored_entry.id
        for entry_key, stored_entry in sso_code_and_ordinal_to_stored_entry.items()
        if entry_key not in planned_entry_keys
    ]

    url_to_planned_bill_index = {
        egazette_link.url: egazette_link.bill_index
        for egazette_link in plan.egazette_links
    }
    egazette_link_updates: list[EgazetteLinkUpdate] = []
    for stored_egazette_supplement in stored_egazette_supplements:
        planned_bill_index = url_to_planned_bill_index.get(
            stored_egazette_supplement.url
        )
        if planned_bill_index is None:
            if stored_egazette_supplement.bill_id is not None:
                egazette_link_updates.append(
                    EgazetteLinkUpdate(stored_egazette_supplement.id, None, None)
                )
            continue
        planned_bill_id = kept_bill_index_to_id.get(planned_bill_index)
        if (
            planned_bill_id is not None
            and stored_egazette_supplement.bill_id == planned_bill_id
            and stored_egazette_supplement.bill_link_source
            == BillLinkSource.BILL_NUMBER_PASSING_DATE
        ):
            continue
        egazette_link_updates.append(
            EgazetteLinkUpdate(
                stored_egazette_supplement.id,
                planned_bill_id,
                BillLinkSource.BILL_NUMBER_PASSING_DATE,
            )
        )

    return ActLinkWrite(
        kept_bill_index_to_id=kept_bill_index_to_id,
        bill_indexes_to_insert=bill_indexes_to_insert,
        bill_updates=bill_updates,
        bill_ids_to_delete=bill_ids_to_delete,
        kept_sso_code_to_act_id=kept_sso_code_to_act_id,
        acts_to_insert=acts_to_insert,
        act_updates=act_updates,
        act_ids_to_delete=act_ids_to_delete,
        entries_to_insert=entries_to_insert,
        entry_updates=entry_updates,
        entry_ids_to_delete=entry_ids_to_delete,
        egazette_link_updates=egazette_link_updates,
    )


def get_first_difference(act_link_write: ActLinkWrite) -> Optional[str]:
    if act_link_write.bill_indexes_to_insert:
        return f"Planned bill {act_link_write.bill_indexes_to_insert[0]} is not stored"
    if act_link_write.bill_updates:
        return f"Stored bill {act_link_write.bill_updates[0].id} differs from the plan"
    if act_link_write.bill_ids_to_delete:
        return f"Stored bill {act_link_write.bill_ids_to_delete[0]} is not in the plan"
    if act_link_write.acts_to_insert:
        return f"Planned Act {act_link_write.acts_to_insert[0].sso_code} is not stored"
    if act_link_write.act_updates:
        return f"Stored Act {act_link_write.act_updates[0].id} differs from the plan"
    if act_link_write.act_ids_to_delete:
        return f"Stored Act {act_link_write.act_ids_to_delete[0]} is not in the plan"
    if act_link_write.entries_to_insert:
        entry_insert = act_link_write.entries_to_insert[0]
        return f"Planned entry {entry_insert.planned_entry.ordinal} of Act {entry_insert.sso_code} is not stored"
    if act_link_write.entry_updates:
        entry_update = act_link_write.entry_updates[0]
        return f"Stored entry {entry_update.planned_entry.ordinal} of Act {entry_update.sso_code} differs from the plan"
    if act_link_write.entry_ids_to_delete:
        return (
            f"Stored entry {act_link_write.entry_ids_to_delete[0]} is not in the plan"
        )
    if act_link_write.egazette_link_updates:
        return f"Stored eGazette supplement {act_link_write.egazette_link_updates[0].id} links to a bill the plan does not"
    return None

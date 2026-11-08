import argparse
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.act import CRUDAct
from crud.act_history_entry import CRUDActHistoryEntry
from crud.bill import CRUDBill
from crud.bill_report import CRUDBillReport
from crud.egazette_supplement import CRUDEgazetteSupplement
from database.act import Act, ActHistoryEntry
from database.bill import Bill, BillReport
from database.egazette_supplement import EgazetteSupplement
from database.init import engine
from enums import ActHistoryEntryKind
from exceptions import HansardWriteCheckError
from logs import logger
from populate.act_links import (
    get_act_link_plan,
    get_act_link_write,
    write_act_link_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from schemas.act_link_plan import ActLinkPlan, PlannedActHistoryEntry
from services.act_link_write import ActLinkWrite, get_first_difference
from settings import settings
from utils.data_files import (
    get_bill_title_corrections,
    get_hand_kept_act_links,
    get_hand_kept_bills,
)
from utils.write_target import validate_can_write

_YEARS_PER_DECADE = 10


def _get_decade_label(first_reading_date: Optional[date]) -> str:
    if first_reading_date is None:
        return "no first reading date"
    return f"{first_reading_date.year // _YEARS_PER_DECADE * _YEARS_PER_DECADE}s"


def _format_counts(counts: Counter[str]) -> str:
    return (
        ", ".join(f"{label} {count:,}" for label, count in sorted(counts.items()))
        or "none"
    )


def _get_bill_number_rule_outcome(entry: PlannedActHistoryEntry) -> str:
    if entry.printed_bill_number is None:
        return "no bill number printed"
    if entry.bill_index is not None and entry.bill_number_bill_index is not None:
        if entry.bill_index == entry.bill_number_bill_index:
            return "number and title rules agree"
        return "number and title rules disagree"
    if entry.bill_index is not None:
        return "title rule only"
    if entry.bill_number_bill_index is not None:
        return "number rule only"
    return "neither rule"


def _log_plan(plan: ActLinkPlan) -> None:
    bill_report_count = sum(len(planned_bill.report_ids) for planned_bill in plan.bills)
    passed_bill_count = sum(planned_bill.is_passed for planned_bill in plan.bills)
    skipped_title_count = len(
        {skipped_report.title for skipped_report in plan.skipped_reports}
    )
    logger.info(
        f"Bills: {len(plan.bills):,}, {passed_bill_count:,} passed; {bill_report_count:,} reports grouped"
    )
    logger.info(
        f"Skipped: {len(plan.skipped_reports):,} reports whose title names no bill, {skipped_title_count:,} distinct titles"
    )
    logger.info(
        f"Bill numbers by source: {_format_counts(Counter(planned_bill.bill_number_source.value for planned_bill in plan.bills if planned_bill.bill_number_source is not None))}; {sum(planned_bill.bill_number is None for planned_bill in plan.bills):,} bills without a number"
    )
    logger.info(
        f"Bill classes: {_format_counts(Counter(planned_bill.bill_class.value for planned_bill in plan.bills if planned_bill.bill_class is not None))}"
    )
    logger.info(
        f"Split bills merged: {len(plan.split_merges):,}; eGazette Acts linked to a bill: {len(plan.egazette_links):,}"
    )
    entries = [entry for planned_act in plan.acts for entry in planned_act.entries]
    unparsed_sso_codes = {unparsed.sso_code for unparsed in plan.unparsed_entries}
    act_without_history_count = sum(
        len(planned_act.entries) == 0 and planned_act.sso_code not in unparsed_sso_codes
        for planned_act in plan.acts
    )
    logger.info(
        f"Acts: {len(plan.acts):,} read, {len(plan.unfetched_sso_codes):,} not fetched, {act_without_history_count:,} with no Legislative History; {len(entries):,} entries"
    )
    logger.info(
        f"Entries by kind: {_format_counts(Counter(entry.kind.value for entry in entries))}"
    )
    logger.info(
        f"Entries linked by rule: {_format_counts(Counter(entry.bill_link_source.value for entry in entries if entry.bill_link_source is not None))}"
    )
    logger.info(
        f"Act and Ordinance entries not linked, by kind and decade of first reading: {_format_counts(Counter(f'{entry.kind.value} {_get_decade_label(entry.first_reading_date)}' for entry in entries if entry.bill_index is None and (entry.kind == ActHistoryEntryKind.ACT or entry.kind == ActHistoryEntryKind.ORDINANCE)))}"
    )
    logger.info(
        f"Act and Ordinance entries by bill number rule outcome: {_format_counts(Counter(_get_bill_number_rule_outcome(entry) for entry in entries if entry.kind == ActHistoryEntryKind.ACT or entry.kind == ActHistoryEntryKind.ORDINANCE))}"
    )
    logger.info(
        f"Entries by source defect: {_format_counts(Counter(defect.value for entry in entries for defect in entry.defects))}"
    )
    logger.info(f"Unparsed entries: {len(plan.unparsed_entries):,}")
    for unparsed_entry in plan.unparsed_entries:
        logger.info(f"Unparsed: {unparsed_entry.message}")


def _log_write(act_link_write: ActLinkWrite) -> None:
    logger.info(
        f"Bills: {len(act_link_write.kept_bill_index_to_id):,} kept, {len(act_link_write.bill_updates):,} updated, {len(act_link_write.bill_indexes_to_insert):,} inserted, {len(act_link_write.bill_ids_to_delete):,} deleted"
    )
    logger.info(
        f"Acts: {len(act_link_write.acts_to_insert):,} inserted, {len(act_link_write.act_updates):,} updated, {len(act_link_write.act_ids_to_delete):,} deleted"
    )
    logger.info(
        f"Entries: {len(act_link_write.entries_to_insert):,} inserted, {len(act_link_write.entry_updates):,} updated, {len(act_link_write.entry_ids_to_delete):,} deleted; {sum(entry_update.is_bill_changed for entry_update in act_link_write.entry_updates):,} linked entries change bill"
    )
    logger.info(
        f"eGazette supplements: {len(act_link_write.egazette_link_updates):,} bill links set or cleared"
    )


def _validate_can_commit_act_links(session: Session, plan: ActLinkPlan) -> None:
    entries = [entry for planned_act in plan.acts for entry in planned_act.entries]
    stored_and_planned_counts = {
        "bills": (
            CRUDBill(session).get_count(),
            len(plan.bills),
        ),
        "passed bills": (
            CRUDBill(session).get_count_by_is_passed(is_passed=True),
            sum(planned_bill.is_passed for planned_bill in plan.bills),
        ),
        "bill reports": (
            CRUDBillReport(session).get_count(),
            sum(len(planned_bill.report_ids) for planned_bill in plan.bills),
        ),
        "bills with a bill number": (
            CRUDBill(session).get_count_by_bill_number_not_null(),
            sum(planned_bill.bill_number is not None for planned_bill in plan.bills),
        ),
        "bills with a class": (
            CRUDBill(session).get_count_by_bill_class_not_null(),
            sum(planned_bill.bill_class is not None for planned_bill in plan.bills),
        ),
        "linked egazette supplements": (
            CRUDEgazetteSupplement(session).get_count_by_bill_id_not_null(),
            len(plan.egazette_links),
        ),
        "acts": (CRUDAct(session).get_count(), len(plan.acts)),
        "act history entries": (CRUDActHistoryEntry(session).get_count(), len(entries)),
        "linked act history entries": (
            CRUDActHistoryEntry(session).get_count_by_bill_id_not_null(),
            sum(entry.bill_index is not None for entry in entries),
        ),
    }
    for label, (stored_count, planned_count) in stored_and_planned_counts.items():
        if stored_count != planned_count:
            raise HansardWriteCheckError(
                f"{stored_count} {label} are stored, the plan has {planned_count}"
            )
    first_difference = get_first_difference(get_act_link_write(session, plan))
    if first_difference is not None:
        raise HansardWriteCheckError(
            f"The stored rows differ from the plan: {first_difference}"
        )


def apply_act_links(harvest_directory: Path, plan_path: Path, is_commit: bool) -> None:
    if not is_commit:
        with Session(engine) as session:
            plan = get_act_link_plan(
                session,
                harvest_directory,
                get_bill_title_corrections(),
                get_hand_kept_bills(),
                get_hand_kept_act_links(),
            )
            _log_plan(plan)
            _log_write(get_act_link_write(session, plan))
        plan_path.write_text(plan.model_dump_json(indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = ActLinkPlan.model_validate_json(plan_path.read_text())
    with Session(engine) as session:
        plan = get_act_link_plan(
            session,
            harvest_directory,
            get_bill_title_corrections(),
            get_hand_kept_bills(),
            get_hand_kept_act_links(),
        )
        _log_plan(plan)
        if plan != reviewed_plan:
            raise HansardWriteCheckError("The plan differs from the reviewed plan")
        act_link_write = get_act_link_write(session, plan)
        _log_write(act_link_write)
        write_act_link_plan(session, plan, act_link_write)
        _validate_can_commit_act_links(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session,
            [
                Bill.__tablename__,
                BillReport.__tablename__,
                Act.__tablename__,
                ActHistoryEntry.__tablename__,
                EgazetteSupplement.__tablename__,
            ],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store bills grouped from the bill reports, the Acts and their Legislative History, and the links between them, checked against a reviewed plan"
    )
    parser.add_argument(
        "--harvest-directory",
        type=Path,
        required=True,
        help="acts.json and one <sso_code>.txt of pdftotext -layout output per Act",
    )
    parser.add_argument(
        "--plan-file",
        type=Path,
        required=True,
        help="the plan file: written by a dry run, read by --commit",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="check the plan is unchanged, then apply it to the stored rows",
    )
    arguments = parser.parse_args()
    apply_act_links(arguments.harvest_directory, arguments.plan_file, arguments.commit)

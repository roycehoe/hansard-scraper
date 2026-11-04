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
from database.act import Act, ActHistoryEntry
from database.bill import Bill, BillReport
from database.init import engine
from enums import ActHistoryEntryKind
from exceptions import HansardWriteCheckError
from logs import logger
from populate.act_links import get_act_link_plan, write_act_link_plan
from populate.written_tables import vacuum_analyze_written_tables
from schemas.act_link_plan import ActLinkPlan
from settings import settings
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
        f"Entries by source defect: {_format_counts(Counter(defect.value for entry in entries for defect in entry.defects))}"
    )
    logger.info(f"Unparsed entries: {len(plan.unparsed_entries):,}")
    for unparsed_entry in plan.unparsed_entries:
        logger.info(f"Unparsed: {unparsed_entry.message}")


def _validate_can_write_act_links(session: Session) -> None:
    table_name_to_row_count = {
        Bill.__tablename__: CRUDBill(session).get_count(),
        BillReport.__tablename__: CRUDBillReport(session).get_count(),
        Act.__tablename__: CRUDAct(session).get_count(),
        ActHistoryEntry.__tablename__: CRUDActHistoryEntry(session).get_count(),
    }
    for table_name, row_count in table_name_to_row_count.items():
        if row_count != 0:
            raise HansardWriteCheckError(
                f"The {table_name} table holds {row_count} rows"
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


def apply_act_links(harvest_directory: Path, plan_path: Path, is_commit: bool) -> None:
    if not is_commit:
        with Session(engine) as session:
            plan = get_act_link_plan(session, harvest_directory)
        _log_plan(plan)
        plan_path.write_text(plan.model_dump_json(indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = ActLinkPlan.model_validate_json(plan_path.read_text())
    with Session(engine) as session:
        _validate_can_write_act_links(session)
        plan = get_act_link_plan(session, harvest_directory)
        _log_plan(plan)
        if plan != reviewed_plan:
            raise HansardWriteCheckError("The plan differs from the reviewed plan")
        write_act_link_plan(session, plan)
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
        help="check the tables are empty and the plan is unchanged, then write it",
    )
    arguments = parser.parse_args()
    apply_act_links(arguments.harvest_directory, arguments.plan_file, arguments.commit)

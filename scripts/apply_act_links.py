import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.bill import CRUDBill
from crud.bill_report import CRUDBillReport
from database.bill import Bill, BillReport
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from populate.act_links import get_act_link_plan, write_act_link_plan
from populate.written_tables import vacuum_analyze_written_tables
from schemas.act_link_plan import ActLinkPlan
from settings import settings
from utils.write_target import validate_can_write


def _log_plan(plan: ActLinkPlan) -> None:
    bill_report_count = sum(len(planned_bill.report_ids) for planned_bill in plan.bills)
    passed_bill_count = sum(planned_bill.is_passed for planned_bill in plan.bills)
    skipped_title_to_count = Counter(
        skipped_report.title for skipped_report in plan.skipped_reports
    )
    logger.info(
        f"Bills: {len(plan.bills):,}, {passed_bill_count:,} passed; {bill_report_count:,} reports grouped"
    )
    logger.info(
        f"Skipped: {len(plan.skipped_reports):,} reports whose title names no bill, {len(skipped_title_to_count):,} distinct titles"
    )


def _validate_can_write_act_links(session: Session) -> None:
    bill_count = CRUDBill(session).get_count()
    if bill_count != 0:
        raise HansardWriteCheckError(f"The bill table holds {bill_count} rows")
    bill_report_count = CRUDBillReport(session).get_count()
    if bill_report_count != 0:
        raise HansardWriteCheckError(
            f"The billreport table holds {bill_report_count} rows"
        )


def _validate_can_commit_act_links(session: Session, plan: ActLinkPlan) -> None:
    bill_count = CRUDBill(session).get_count()
    if bill_count != len(plan.bills):
        raise HansardWriteCheckError(
            f"{bill_count} bills are stored, the plan has {len(plan.bills)}"
        )
    passed_bill_count = CRUDBill(session).get_count_by_is_passed(is_passed=True)
    planned_passed_bill_count = sum(
        planned_bill.is_passed for planned_bill in plan.bills
    )
    if passed_bill_count != planned_passed_bill_count:
        raise HansardWriteCheckError(
            f"{passed_bill_count} passed bills are stored, the plan has {planned_passed_bill_count}"
        )
    bill_report_count = CRUDBillReport(session).get_count()
    planned_bill_report_count = sum(
        len(planned_bill.report_ids) for planned_bill in plan.bills
    )
    if bill_report_count != planned_bill_report_count:
        raise HansardWriteCheckError(
            f"{bill_report_count} bill reports are stored, the plan has {planned_bill_report_count}"
        )


def apply_act_links(plan_path: Path, is_commit: bool) -> None:
    if not is_commit:
        with Session(engine) as session:
            plan = get_act_link_plan(session)
        _log_plan(plan)
        plan_path.write_text(plan.model_dump_json(indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = ActLinkPlan.model_validate_json(plan_path.read_text())
    with Session(engine) as session:
        _validate_can_write_act_links(session)
        plan = get_act_link_plan(session)
        _log_plan(plan)
        if plan != reviewed_plan:
            raise HansardWriteCheckError("The plan differs from the reviewed plan")
        write_act_link_plan(session, plan)
        _validate_can_commit_act_links(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session, [Bill.__tablename__, BillReport.__tablename__]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store bills grouped from the bill reports, checked against a reviewed plan"
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
    apply_act_links(arguments.plan_file, arguments.commit)

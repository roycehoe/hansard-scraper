from sqlmodel import Session

from crud.bill import CRUDBill
from crud.bill_report import CRUDBillReport
from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.bill import Bill, BillReport
from enums import ReportType
from schemas.act_link_plan import ActLinkPlan, PlannedBill, SkippedReport
from services.bill import (
    NOT_THIRD_READING_PATTERNS,
    THIRD_READING_PATTERN,
    group_bills,
)

_BILL_REPORT_TYPES = (ReportType.BILL, ReportType.BILL_INTRODUCTION)


def get_act_link_plan(session: Session) -> ActLinkPlan:
    report_rows = CRUDReport(session).get_sitting_date_title_rows_by_report_types(
        _BILL_REPORT_TYPES
    )
    third_reading_report_ids = CRUDSpeech(
        session
    ).get_report_ids_by_report_types_and_transcript_regex_and_transcript_not_regexes(
        _BILL_REPORT_TYPES, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
    )
    bill_grouping = group_bills(report_rows, frozenset(third_reading_report_ids))
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
    )


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

from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
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

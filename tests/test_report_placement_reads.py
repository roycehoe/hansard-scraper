from datetime import datetime

from sqlmodel import Session

from crud.report import CRUDReport, ReportPlacementRow
from enums import ReportType
from tests.bill_seed import seed_bill_report

_BILL_TITLE_END_PATTERN = r"bill[^a-z]*$"
_BILL_REPORT_TYPES = (ReportType.BILL, ReportType.BILL_INTRODUCTION)
_TITLE = "Estate Duty Bill"
_EARLY_DATE = datetime(2025, 1, 15)
_LATE_DATE = datetime(2025, 2, 19)


def test_get_placement_rows_by_report_types_returns_the_five_columns_in_date_then_id_order(
    scratch_session: Session,
) -> None:
    late_id = seed_bill_report(
        scratch_session, "late-bill", ReportType.BILL, _LATE_DATE, _TITLE, []
    )
    early_introduction_id = seed_bill_report(
        scratch_session,
        "early-intro",
        ReportType.BILL_INTRODUCTION,
        _EARLY_DATE,
        _TITLE,
        [],
    )
    early_bill_id = seed_bill_report(
        scratch_session, "early-bill", ReportType.BILL, _EARLY_DATE, _TITLE, []
    )
    seed_bill_report(
        scratch_session, "a-motion", ReportType.MOTION, _EARLY_DATE, _TITLE, []
    )
    seed_bill_report(
        scratch_session, "an-answer", ReportType.ORAL_ANSWER, _EARLY_DATE, _TITLE, []
    )
    seed_bill_report(
        scratch_session, "a-budget", ReportType.BUDGET, _EARLY_DATE, _TITLE, []
    )

    placement_rows = CRUDReport(scratch_session).get_placement_rows_by_report_types(
        _BILL_REPORT_TYPES
    )

    assert placement_rows == [
        ReportPlacementRow(
            early_introduction_id, "early-intro", _EARLY_DATE, _TITLE, "bill-intro"
        ),
        ReportPlacementRow(early_bill_id, "early-bill", _EARLY_DATE, _TITLE, "bill"),
        ReportPlacementRow(late_id, "late-bill", _LATE_DATE, _TITLE, "bill"),
    ]


def test_get_placement_rows_by_report_types_not_in_and_title_regex_returns_other_types_ending_in_bill(
    scratch_session: Session,
) -> None:
    motion_id = seed_bill_report(
        scratch_session,
        "bill-motion",
        ReportType.MOTION,
        _EARLY_DATE,
        "Motion on Estate Duty Bill",
        [],
    )
    upper_case_motion_id = seed_bill_report(
        scratch_session,
        "upper-motion",
        ReportType.MOTION,
        _LATE_DATE,
        "MOTION ON ESTATE DUTY BILL",
        [],
    )
    seed_bill_report(
        scratch_session, "bill-report", ReportType.BILL, _EARLY_DATE, _TITLE, []
    )
    seed_bill_report(
        scratch_session,
        "adjournment",
        ReportType.MOTION,
        _EARLY_DATE,
        "Adjournment",
        [],
    )

    placement_rows = CRUDReport(
        scratch_session
    ).get_placement_rows_by_report_types_not_in_and_title_regex(
        _BILL_REPORT_TYPES, _BILL_TITLE_END_PATTERN
    )

    assert [placement_row.id for placement_row in placement_rows] == [
        motion_id,
        upper_case_motion_id,
    ]
    assert placement_rows[0].report_id == "bill-motion"
    assert placement_rows[0].report_type == "motion"

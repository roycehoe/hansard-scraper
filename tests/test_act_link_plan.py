from datetime import datetime

from sqlmodel import Session

from database.report import Report
from database.speech import Speech
from enums import ReportType
from populate.act_links import get_act_link_plan
from schemas.act_link_plan import SkippedReport

_PARLIAMENT_NUMBER = 12
_PASSING_LINE = "Question put, and agreed to.\n\nBill read a Third time and passed."


def _seed_report(
    session: Session,
    report_id: str,
    report_type: ReportType,
    sitting_date: datetime,
    title: str,
    lines: list[str],
) -> int:
    report = Report(
        volumeNo=1,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=sitting_date,
        sno=1,
        original_title=title,
        title=title,
        reportId=report_id,
        reportType=report_type.value,
        content=None,
        markdown_content=None,
        htmlFileName=None,
        reportVersion="sprs3",
    )
    session.add(report)
    session.flush()
    assert report.id is not None
    session.add_all(
        Speech(
            ordinal=ordinal,
            speaker=None,
            transcript=line,
            sitting_date=sitting_date,
            report_type=report.report_type,
            report_id=report.id,
        )
        for ordinal, line in enumerate(lines, start=1)
    )
    session.commit()
    return report.id


def test_plan_groups_bill_reports_and_reads_third_reading_lines(
    scratch_session: Session,
) -> None:
    first_reading_id = _seed_report(
        scratch_session,
        "first-reading",
        ReportType.BILL_INTRODUCTION,
        datetime(2024, 12, 2),
        "Estate Duty Bill",
        ["Bill read a First time."],
    )
    second_reading_id = _seed_report(
        scratch_session,
        "second-reading",
        ReportType.BILL,
        datetime(2025, 1, 14),
        "Estate Duty Bill",
        ["Mr Lim: I beg to move, That the Bill be now read a Second time."],
    )
    third_reading_id = _seed_report(
        scratch_session,
        "third-reading",
        ReportType.BILL,
        datetime(2025, 1, 15),
        "Estate Duty Bill",
        [_PASSING_LINE],
    )
    motion_id = _seed_report(
        scratch_session,
        "motion-to-read",
        ReportType.BILL,
        datetime(2025, 6, 2),
        "Water Bill",
        [
            "That the Bill be now read a Third time.",
            "Mr Tan: Sir, I thank members. The Bill read a Third time is good.",
        ],
    )
    adjournment_id = _seed_report(
        scratch_session,
        "adjournment",
        ReportType.BILL,
        datetime(2025, 1, 15),
        "ADJOURNMENT",
        [_PASSING_LINE],
    )
    other_type_id = _seed_report(
        scratch_session,
        "other-type",
        ReportType.MOTION,
        datetime(2025, 1, 15),
        "Sewage Bill",
        [_PASSING_LINE],
    )

    plan = get_act_link_plan(scratch_session)

    assert [
        (planned_bill.title_key, planned_bill.report_ids, planned_bill.is_passed)
        for planned_bill in plan.bills
    ] == [
        (
            "estatedutybill",
            [first_reading_id, second_reading_id, third_reading_id],
            True,
        ),
        ("waterbill", [motion_id], False),
    ]
    assert plan.skipped_reports == [
        SkippedReport(report_id=adjournment_id, title="ADJOURNMENT")
    ]
    assert other_type_id not in {
        report_id
        for planned_bill in plan.bills
        for report_id in planned_bill.report_ids
    }

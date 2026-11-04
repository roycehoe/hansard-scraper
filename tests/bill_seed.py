from datetime import datetime

from sqlmodel import Session

from database.report import Report
from database.speech import Speech
from enums import ReportType

_PARLIAMENT_NUMBER = 12


def seed_bill_report(
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

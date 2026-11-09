import json
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, col, select

from database.bill import Bill, BillReport
from database.report import Report
from database.speaker import Speaker
from database.speech import Speech
from enums import BillReportRole, ReportType
from utils.title_key import get_title_key

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


def seed_speaker(session: Session, name: str) -> int:
    speaker = Speaker(
        name=name,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    session.add(speaker)
    session.commit()
    assert speaker.id is not None
    return speaker.id


def seed_bill(
    session: Session, title: str, report_id_to_role: dict[int, BillReportRole]
) -> int:
    sitting_dates = session.exec(
        select(Report.sitting_date).where(col(Report.id).in_(report_id_to_role))
    ).all()
    bill = Bill(
        title=title,
        title_key=get_title_key(title),
        first_sitting_date=min(sitting_dates),
        last_sitting_date=max(sitting_dates),
        is_passed=False,
    )
    session.add(bill)
    session.flush()
    assert bill.id is not None
    session.add_all(
        BillReport(role=role, bill_id=bill.id, report_id=report_id)
        for report_id, role in report_id_to_role.items()
    )
    session.commit()
    return bill.id


_ESTATE_DUTY_ACT_TEXT = """\
LEGISLATIVE HISTORY
 1. Act 3 of 2025 — Estate Duty Act 2025
     Bill                             :   9/2024
     First Reading                    :   2 December 2024
     Second and Third Readings        :   15 January 2025
     Commencement                     :   1 March 2025
 2. 2025 Revised Edition — Estate Duty Act 2025
     Operation                        :   31 December 2025
Abbreviations
"""
_UNAMENDED_ACT_TEXT = "WATER ACT 2025\n\nPart 1\n"


def write_harvest(directory: Path) -> None:
    (directory / "acts.json").write_text(
        json.dumps(
            [
                {"sso_code": "EDA2025", "title": "Estate Duty Act 2025"},
                {"sso_code": "WA2025", "title": "Water Act 2025"},
                {"sso_code": "GONE1999", "title": "Gone Act 1999"},
            ]
        ),
        encoding="utf8",
    )
    (directory / "EDA2025.txt").write_text(_ESTATE_DUTY_ACT_TEXT, encoding="utf8")
    (directory / "WA2025.txt").write_text(_UNAMENDED_ACT_TEXT, encoding="utf8")

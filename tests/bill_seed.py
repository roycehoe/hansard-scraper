import json
from datetime import datetime
from pathlib import Path

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

from datetime import datetime
from typing import Optional

from sqlmodel import Session

from database.report import Report
from database.speech import Speech
from enums import SpeechKind

_DEFAULT_PARLIAMENT_NUMBER = 14
_REPORT_TYPE = "bill"


def add_division_report(
    session: Session,
    report_id: str,
    sitting_date: datetime,
    parliament_number: int = _DEFAULT_PARLIAMENT_NUMBER,
) -> Report:
    report = Report(
        volume_number=parliament_number,
        parliament_number=parliament_number,
        sitting_date=sitting_date,
        speech_number=1,
        original_title="Bill",
        title="Bill",
        report_id=report_id,
        report_type=_REPORT_TYPE,
        content="Report text.",
        report_version="sprs3",
    )
    session.add(report)
    session.flush()
    return report


def add_division_speech_rows(
    session: Session,
    report: Report,
    rows: list[tuple[SpeechKind, Optional[str], str]],
) -> None:
    assert report.id is not None
    session.add_all(
        Speech(
            ordinal=ordinal,
            speaker=speaker,
            transcript=transcript,
            kind=kind,
            sitting_date=report.sitting_date,
            report_type=report.report_type,
            report_id=report.id,
            speaker_id=None,
        )
        for ordinal, (kind, speaker, transcript) in enumerate(rows, 1)
    )
    session.flush()

from datetime import datetime
from typing import Optional

from sqlmodel import Session

from crud.speech import CRUDSpeech
from database.report import Report
from database.speaker import Speaker
from database.speech import Speech
from enums import ReportType, ReportVersion

_SITTING_DATE = datetime(2025, 4, 2)
_PARLIAMENT_NUMBER = 14


def _build_report(report_id: str) -> Report:
    return Report(
        volumeNo=_PARLIAMENT_NUMBER,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title=report_id,
        title=report_id,
        reportId=report_id,
        reportType=ReportType.MOTION,
        content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _build_speech(report_id: Optional[int], ordinal: int, speaker_id: Optional[int]) -> Speech:
    assert report_id is not None
    return Speech(
        ordinal=ordinal,
        speaker="Mr Tan Ah Kow",
        transcript=f"Speech {ordinal}.",
        sitting_date=_SITTING_DATE,
        report_type=ReportType.MOTION,
        report_id=report_id,
        speaker_id=speaker_id,
    )


def test_link_rows_come_in_report_and_ordinal_order(scratch_session: Session) -> None:
    speaker = Speaker(name="Tan Ah Kow", party="PAP", is_legislative_assembly=False, parliament_number=_PARLIAMENT_NUMBER)
    first_report = _build_report("motion-1")
    second_report = _build_report("motion-2")
    scratch_session.add_all([speaker, first_report, second_report])
    scratch_session.commit()
    scratch_session.add_all([
        _build_speech(second_report.id, 2, speaker.id),
        _build_speech(first_report.id, 3, speaker.id),
        _build_speech(second_report.id, 1, speaker.id),
        _build_speech(first_report.id, 1, speaker.id),
    ])
    scratch_session.commit()

    link_rows = CRUDSpeech(scratch_session).get_link_rows_by_speaker_id_not_null()

    assert [(link_row.report_id, link_row.ordinal) for link_row in link_rows] == [
        (first_report.id, 1),
        (first_report.id, 3),
        (second_report.id, 1),
        (second_report.id, 2),
    ]

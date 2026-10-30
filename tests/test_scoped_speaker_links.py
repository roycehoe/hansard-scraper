from datetime import datetime

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.speech import CRUDSpeech
from database.attendance import Attendance
from database.report import Report
from database.sitting import Sitting
from database.speaker import Speaker
from database.speech import Speech
from enums import ReportType, ReportVersion
from populate.speaker_links import link_speakers_by_report_ids_and_sitting_ids

_PARLIAMENT_NUMBER = 14
_SITTING_DATE = datetime(2025, 4, 2)
_SITTING_DATE_KEY = "2-4-2025"
_OTHER_SITTING_DATE_KEY = "3-4-2025"
_SPEAKER_NAME = "Pritam Singh"
_SPEAKER_LABEL = "Mr Pritam Singh"
_SPEECH_NUMBER = 1
_ORDINAL = 1


def _build_report(report_id: str) -> Report:
    return Report(
        volumeNo=_PARLIAMENT_NUMBER,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=_SPEECH_NUMBER,
        original_title=report_id,
        title=report_id,
        reportId=report_id,
        reportType=ReportType.MOTION,
        content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _build_speech(report: Report) -> Speech:
    assert report.id is not None
    return Speech(ordinal=_ORDINAL, speaker=_SPEAKER_LABEL, transcript="Text", sitting_date=report.sitting_date, report_type=report.report_type, report_id=report.id)


def test_links_only_the_given_reports_and_sittings_and_never_commits(scratch_session: Session) -> None:
    first_report = _build_report("first-report")
    second_report = _build_report("second-report")
    sitting = Sitting(sitting_date=_SITTING_DATE_KEY, parlement_no=_PARLIAMENT_NUMBER)
    other_sitting = Sitting(sitting_date=_OTHER_SITTING_DATE_KEY, parlement_no=_PARLIAMENT_NUMBER)
    scratch_session.add_all([
        Speaker(name=_SPEAKER_NAME, party="WP", is_legislative_assembly=False, parliament_number=_PARLIAMENT_NUMBER),
        first_report,
        second_report,
        sitting,
        other_sitting,
    ])
    scratch_session.flush()
    assert sitting.id is not None
    assert other_sitting.id is not None
    scratch_session.add_all([
        _build_speech(first_report),
        _build_speech(second_report),
        Attendance(sitting_id=sitting.id, speaker_name=_SPEAKER_LABEL),
        Attendance(sitting_id=other_sitting.id, speaker_name=_SPEAKER_LABEL),
    ])
    scratch_session.commit()
    first_report_id = first_report.id
    second_report_id = second_report.id
    sitting_id = sitting.id
    other_sitting_id = other_sitting.id
    assert first_report_id is not None
    assert second_report_id is not None
    assert sitting_id is not None
    assert other_sitting_id is not None

    link_speakers_by_report_ids_and_sitting_ids(scratch_session, [first_report_id], [sitting_id])

    assert CRUDSpeech(scratch_session).get_speaker_rows_by_report_ids_and_speaker_id_null([first_report_id]) == []
    assert len(CRUDSpeech(scratch_session).get_speaker_rows_by_report_ids_and_speaker_id_null([second_report_id])) == 1
    assert CRUDAttendance(scratch_session).get_speaker_rows_by_sitting_ids_and_speaker_id_null([sitting_id]) == []
    assert len(CRUDAttendance(scratch_session).get_speaker_rows_by_sitting_ids_and_speaker_id_null([other_sitting_id])) == 1
    scratch_session.rollback()
    assert len(CRUDSpeech(scratch_session).get_speaker_rows_by_report_ids_and_speaker_id_null([first_report_id])) == 1
    assert len(CRUDAttendance(scratch_session).get_speaker_rows_by_sitting_ids_and_speaker_id_null([sitting_id])) == 1

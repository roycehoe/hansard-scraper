from datetime import datetime
from typing import Optional

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from crud.attendance import CRUDAttendance
from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from crud.refresh_run import CRUDRefreshRun
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from database.attendance import Attendance
from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.refresh_run import RefreshRun
from database.report import Report
from database.sitting import Sitting
from database.speaker import Speaker
from enums import RefreshRunStatus, ReportType, ReportVersion

_EARLIER_PARLIAMENT = 13
_LATEST_PARLIAMENT = 14
_LINKED_ATTENDANCE_COUNT = 1
_SITTING_DATE = "2-4-2025"
_SPEECH_NUMBER = 1
_TEXT_SITTING_DATE = datetime(2020, 1, 6)
_EMPTY_TEXT_SITTING_DATE = datetime(2021, 1, 6)
_NULL_TEXT_SITTING_DATE = datetime(2022, 1, 6)
_REPORT_TEXT = "<p>Text</p>"
_COUNT_COLUMNS = tuple(name for name, field in RefreshRun.model_fields.items() if field.annotation is int)


def _build_report(report_id: str, parliament_number: int, sitting_date: datetime, content: Optional[str]) -> Report:
    return Report(
        volumeNo=parliament_number,
        parlNo=parliament_number,
        sittingNo=None,
        sittingDate=sitting_date,
        sno=_SPEECH_NUMBER,
        original_title=report_id,
        title=report_id,
        reportId=report_id,
        reportType=ReportType.MOTION,
        content=content,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def test_add_many_flushes_without_commit(scratch_session: Session) -> None:
    sitting = Sitting(sitting_date=_SITTING_DATE, parlement_no=_LATEST_PARLIAMENT)
    sitting_date_response = HansardSittingDateResponse(sitting_date=_SITTING_DATE, parlement_no=_LATEST_PARLIAMENT)

    CRUDSitting(scratch_session).add_many([sitting])
    CRUDHansardSittingDateResponse(scratch_session).add_many([sitting_date_response])

    assert scratch_session.exec(select(Sitting.id)).all() == [sitting.id]
    assert scratch_session.exec(select(HansardSittingDateResponse.id)).all() == [sitting_date_response.id]
    scratch_session.rollback()
    assert scratch_session.exec(select(Sitting.id)).all() == []
    assert scratch_session.exec(select(HansardSittingDateResponse.id)).all() == []


def test_max_reads(scratch_session: Session) -> None:
    assert CRUDReport(scratch_session).get_max_parliament_number() is None
    assert CRUDSitting(scratch_session).get_max_parlement_no() is None
    assert CRUDReport(scratch_session).get_max_sitting_date_by_content_not_null_and_content_not_empty() is None

    scratch_session.add_all([
        _build_report("with-text", _EARLIER_PARLIAMENT, _TEXT_SITTING_DATE, _REPORT_TEXT),
        _build_report("empty-text", _LATEST_PARLIAMENT, _EMPTY_TEXT_SITTING_DATE, ""),
        _build_report("null-text", _LATEST_PARLIAMENT, _NULL_TEXT_SITTING_DATE, None),
        Sitting(parlement_no=_EARLIER_PARLIAMENT),
        Sitting(parlement_no=_LATEST_PARLIAMENT),
    ])
    scratch_session.flush()

    assert CRUDReport(scratch_session).get_max_parliament_number() == _LATEST_PARLIAMENT
    assert CRUDSitting(scratch_session).get_max_parlement_no() == _LATEST_PARLIAMENT
    assert CRUDReport(scratch_session).get_max_sitting_date_by_content_not_null_and_content_not_empty() == _TEXT_SITTING_DATE
    assert CRUDReport(scratch_session).get_report_ids_by_sitting_date_from(_EMPTY_TEXT_SITTING_DATE) == {"empty-text", "null-text"}


def test_attendance_count_reads_the_database(scratch_session: Session) -> None:
    speaker = Speaker(name="Tan Ah Kow", party="PAP", is_legislative_assembly=False, parliament_number=_LATEST_PARLIAMENT)
    sitting = Sitting(sitting_date=_SITTING_DATE, parlement_no=_LATEST_PARLIAMENT)
    scratch_session.add_all([speaker, sitting])
    scratch_session.flush()
    first_attendance = Attendance(sitting_id=sitting.id, speaker_name="Tan Ah Kow")
    second_attendance = Attendance(sitting_id=sitting.id, speaker_name="Lim Ah Lian")
    scratch_session.add_all([first_attendance, second_attendance])
    scratch_session.flush()
    assert first_attendance.id is not None
    assert speaker.id is not None
    assert sitting.id is not None

    CRUDAttendance(scratch_session).set_speaker_ids_bulk({first_attendance.id: speaker.id})

    assert CRUDAttendance(scratch_session).get_count_by_sitting_ids_and_speaker_id_not_null([sitting.id]) == _LINKED_ATTENDANCE_COUNT
    assert first_attendance.speaker_id is None


def test_refresh_run_create_and_update_commit(scratch_session: Session) -> None:
    refresh_run = RefreshRun()

    CRUDRefreshRun(scratch_session).create(refresh_run)

    assert refresh_run.id is not None
    assert refresh_run.status == RefreshRunStatus.RUNNING
    assert all(getattr(refresh_run, count_column) == 0 for count_column in _COUNT_COLUMNS)
    assert refresh_run.started_at.tzinfo is not None
    refresh_run_id = refresh_run.id
    scratch_session.rollback()
    assert CRUDRefreshRun(scratch_session).get_by_id_for_update(refresh_run_id) is not None

    refresh_run.status = RefreshRunStatus.SUCCEEDED
    CRUDRefreshRun(scratch_session).update(refresh_run)
    scratch_session.rollback()

    stored_refresh_run = CRUDRefreshRun(scratch_session).get_by_id_for_update(refresh_run_id)
    assert stored_refresh_run is not None
    assert stored_refresh_run.status == RefreshRunStatus.SUCCEEDED
    assert CRUDRefreshRun(scratch_session).get_by_status(RefreshRunStatus.RUNNING) == []


def test_refresh_run_status_check_rejects_unknown(scratch_session: Session) -> None:
    count_values = ", ".join("0" for _ in _COUNT_COLUMNS)
    statement = text(
        f"INSERT INTO refresh_run ({', '.join(_COUNT_COLUMNS)}, started_at, status) "
        f"VALUES ({count_values}, now(), 'UNKNOWN')"
    )

    with pytest.raises(IntegrityError, match="ck_refresh_run_status"):
        scratch_session.execute(statement)
    scratch_session.rollback()

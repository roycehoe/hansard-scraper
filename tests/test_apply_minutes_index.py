import json
import shutil
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_minutes_index as apply_minutes_index_script
from crud.minutes import CRUDMinutes
from crud.minutes_index_capture import CRUDMinutesIndexCapture
from database.minutes import Minutes
from enums import (
    MinutesFileFormat,
    MinutesIndexSource,
    MinutesStatus,
)
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.minutes_index_plan import MinutesIndexPlan
from scripts.apply_minutes_index import apply_minutes_index
from services.minutes_index import get_live_capture_url
from settings import settings
from tests.division_seed import add_division_report

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures" / "minutes_index"
_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_LIVE_FILE = "live-index-3-rows.html"
_NEW_SITE_FILE = "archive-index-new-site.html"
_NEW_SITE_PAGE = "<html><body><div class='new-site'></div></body></html>"
_ARCHIVE_FILE_TO_TIMESTAMP = {
    "archive-index-2025-06-named-capture.html": "20250625085704",
    "archive-index-2010-03-doc.html": "20211002142455",
    "archive-index-2021-08.html": "20210912134436",
}
_ARCHIVE_2021_FILE = "archive-index-2021-08.html"
_ARCHIVE_2021_FILE_URL_3_AUGUST = "https://www.parliament.gov.sg/docs/default-source/default-document-library/vp-3aug21.pdf?sfvrsn=aa9ad958_0"
_ARCHIVE_2021_FILE_URL_2_AUGUST = "https://www.parliament.gov.sg/docs/default-source/default-document-library/vp-2aug21.pdf?sfvrsn=d362436f_0"
_REPORT_DATES = (
    datetime(2021, 8, 3),
    datetime(2021, 3, 15),
    datetime(2004, 1, 4),
    datetime(2010, 3, 4),
)
_CAPTURE_COUNT = 4
_FIXTURE_ROW_COUNT = 10
_DRY_RUN_LOG_LINES = [
    "Captures: 4",
    "Capture live-index-3-rows.html: 3 rows",
    "Capture archive-index-2025-06-named-capture.html: 2 rows",
    "Capture archive-index-2010-03-doc.html: 2 rows",
    "Capture archive-index-2021-08.html: 3 rows",
    "Rows: 11 new, 0 moved from NOT_YET_LISTED, 0 moved from FILE_NOT_FOUND, 0 already stored",
    "Rows by status: LISTED 10, NOT_YET_LISTED 1",
    "Rows by index source: ARCHIVE_INDEX_CAPTURE 7, LIVE_PAGE 3",
    "Duplicates dropped: 0, conflicting addresses: 0",
    "Dry run: nothing written",
]


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _build_live_page(rows: list[dict]) -> str:
    rows_text = json.dumps(
        {"initialMPs": {"meta": {"filter_count": len(rows)}, "data": rows}},
        separators=(",", ":"),
    )
    return f"<html><body><script>self.__next_f.push([1,{json.dumps(rows_text)}])</script></body></html>"


def _build_live_row(sitting_date: date, file_id: str, filename: str) -> dict:
    return {
        "description": "Votes and Proceedings No. 1",
        "date": f"{sitting_date.isoformat()}T12:00:00",
        "report": {
            "id": file_id,
            "filename_download": filename,
            "type": "application/pdf",
        },
        "parliaments": {"title": "14th Parliament"},
    }


def _build_manifest_entry(file_path: Path, archive_timestamp: Optional[str]) -> dict:
    original_url = settings.minutes_index_url
    if archive_timestamp is None:
        capture_url = get_live_capture_url(original_url, file_path.read_text())
    else:
        capture_url = (
            f"https://web.archive.org/web/{archive_timestamp}id_/{original_url}"
        )
    return {
        "page": None if archive_timestamp is None else 1,
        "archive_timestamp": archive_timestamp,
        "original_url": original_url,
        "capture_url": capture_url,
        "file": file_path.name,
        "size": len(file_path.read_bytes()),
    }


def _write_captures(directory: Path, live_page: Optional[str] = None) -> None:
    live_path = directory / _LIVE_FILE
    if live_page is None:
        shutil.copy(_FIXTURE_DIRECTORY / _LIVE_FILE, live_path)
    else:
        live_path.write_text(live_page)
    manifest = [_build_manifest_entry(live_path, None)]
    for file_name, archive_timestamp in _ARCHIVE_FILE_TO_TIMESTAMP.items():
        shutil.copy(_FIXTURE_DIRECTORY / file_name, directory / file_name)
        manifest.append(_build_manifest_entry(directory / file_name, archive_timestamp))
    (directory / "captures.json").write_text(json.dumps(manifest))


def _remove_capture(directory: Path, file_name: str) -> None:
    manifest = json.loads((directory / "captures.json").read_text())
    (directory / "captures.json").write_text(
        json.dumps([entry for entry in manifest if entry["file"] != file_name])
    )


def _seed_reports(session: Session) -> None:
    for index, sitting_date in enumerate(_REPORT_DATES):
        add_division_report(session, f"R{index}", sitting_date)
    session.commit()


def _get_minutes(session: Session, sitting_date: date) -> Optional[Minutes]:
    session.expire_all()
    stored_rows = CRUDMinutes(session).get_by_sitting_dates([sitting_date])
    return stored_rows[0] if stored_rows else None


def _get_all_minutes(session: Session) -> list[Minutes]:
    session.expire_all()
    return CRUDMinutes(session).get_by_sitting_dates(
        [sitting_date.date() for sitting_date in _REPORT_DATES]
        + [date(2021, 7, 27), date(2021, 8, 2), date(2010, 3, 3)]
    )


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_minutes_index_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_minutes_index_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_the_plan_file_only(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"

    apply_minutes_index(tmp_path, plan_path, is_commit=False)

    assert log_recorder.messages == _DRY_RUN_LOG_LINES
    plan = MinutesIndexPlan.model_validate_json(plan_path.read_text())
    assert len(plan.rows) == _FIXTURE_ROW_COUNT + 1
    assert CRUDMinutesIndexCapture(scratch_session).get_count() == 0
    assert _get_minutes(scratch_session, date(2021, 8, 3)) is None


def test_commit_stores_captures_listed_rows_and_not_yet_listed_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_minutes_index(tmp_path, plan_path, is_commit=False)

    apply_minutes_index(tmp_path, plan_path, is_commit=True)

    assert CRUDMinutesIndexCapture(scratch_session).get_count() == _CAPTURE_COUNT
    third_august = _get_minutes(scratch_session, date(2021, 8, 3))
    assert third_august is not None
    assert third_august.status == MinutesStatus.LISTED
    assert third_august.index_source == MinutesIndexSource.ARCHIVE_INDEX_CAPTURE
    assert third_august.file_url == _ARCHIVE_2021_FILE_URL_3_AUGUST
    expected_capture_url = f"https://web.archive.org/web/{_ARCHIVE_FILE_TO_TIMESTAMP[_ARCHIVE_2021_FILE]}id_/{settings.minutes_index_url}"
    capture_rows = CRUDMinutesIndexCapture(scratch_session).get_by_capture_urls(
        [expected_capture_url]
    )
    assert third_august.index_capture_id == capture_rows[0].id
    fourth_march = _get_minutes(scratch_session, date(2010, 3, 4))
    assert fourth_march is not None
    assert fourth_march.status == MinutesStatus.LISTED
    assert fourth_march.file_format == MinutesFileFormat.WORD
    fifteenth_march = _get_minutes(scratch_session, date(2021, 3, 15))
    assert fifteenth_march is not None
    assert fifteenth_march.status == MinutesStatus.NOT_YET_LISTED
    assert fifteenth_march.file_url is None
    assert fifteenth_march.index_capture_id is None
    assert _get_minutes(scratch_session, date(2004, 1, 4)) is None


def test_live_row_wins_over_an_archived_row_for_the_same_date(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    live_page = _build_live_page(
        [_build_live_row(date(2021, 8, 3), "live-file", "VP-3Aug2021.pdf")]
    )
    _write_captures(tmp_path, live_page)
    plan_path = tmp_path / "plan.json"
    apply_minutes_index(tmp_path, plan_path, is_commit=False)
    plan = MinutesIndexPlan.model_validate_json(plan_path.read_text())

    apply_minutes_index(tmp_path, plan_path, is_commit=True)

    assert plan.duplicate_count == 1
    assert plan.conflicting_address_count == 1
    third_august = _get_minutes(scratch_session, date(2021, 8, 3))
    assert third_august is not None
    assert third_august.index_source == MinutesIndexSource.LIVE_PAGE
    assert (
        third_august.file_url
        == f"{settings.minutes_media_url}/live-file/VP-3Aug2021.pdf"
    )


def test_second_commit_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_minutes_index(tmp_path, plan_path, is_commit=False)
    apply_minutes_index(tmp_path, plan_path, is_commit=True)
    first_ids = [stored.id for stored in _get_all_minutes(scratch_session)]
    log_recorder.messages.clear()
    apply_minutes_index(tmp_path, plan_path, is_commit=False)

    apply_minutes_index(tmp_path, plan_path, is_commit=True)

    assert [stored.id for stored in _get_all_minutes(scratch_session)] == first_ids
    assert any(
        message.startswith("Rows: 0 new, 0 moved") for message in log_recorder.messages
    )
    assert CRUDMinutesIndexCapture(scratch_session).get_count() == _CAPTURE_COUNT


def test_stored_not_yet_listed_row_moves_to_listed_and_keeps_its_id(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    _write_captures(tmp_path)
    _remove_capture(tmp_path, _ARCHIVE_2021_FILE)
    first_plan_path = tmp_path / "first-plan.json"
    apply_minutes_index(tmp_path, first_plan_path, is_commit=False)
    apply_minutes_index(tmp_path, first_plan_path, is_commit=True)
    before_move = _get_minutes(scratch_session, date(2021, 8, 3))
    assert before_move is not None
    assert before_move.status == MinutesStatus.NOT_YET_LISTED
    first_id = before_move.id
    scratch_session.add(
        Minutes(
            sitting_date=date(2021, 8, 2),
            status=MinutesStatus.TEXT_STORED,
            index_source=MinutesIndexSource.ARCHIVE_INDEX_CAPTURE,
            file_url="https://example.test/stored.pdf",
        )
    )
    scratch_session.commit()
    _write_captures(tmp_path)
    second_plan_path = tmp_path / "second-plan.json"
    log_recorder.messages.clear()

    apply_minutes_index(tmp_path, second_plan_path, is_commit=False)
    apply_minutes_index(tmp_path, second_plan_path, is_commit=True)

    third_august = _get_minutes(scratch_session, date(2021, 8, 3))
    assert third_august is not None
    assert third_august.id == first_id
    assert third_august.status == MinutesStatus.LISTED
    second_august = _get_minutes(scratch_session, date(2021, 8, 2))
    assert second_august is not None
    assert second_august.status == MinutesStatus.TEXT_STORED
    assert second_august.file_url == "https://example.test/stored.pdf"
    assert (
        "Rows: 1 new, 1 moved from NOT_YET_LISTED, 0 moved from FILE_NOT_FOUND, 9 already stored"
        in log_recorder.messages
    )


def test_set_listed_refuses_a_row_whose_status_changed(
    scratch_session: Session,
) -> None:
    minutes = Minutes(sitting_date=date(2021, 8, 3), status=MinutesStatus.LISTED)
    CRUDMinutes(scratch_session).add_many([minutes])
    assert minutes.id is not None

    with pytest.raises(HansardWriteCheckError, match="is no longer NOT_YET_LISTED"):
        CRUDMinutes(scratch_session).set_listed_by_id_and_status(
            minutes.id,
            MinutesStatus.NOT_YET_LISTED,
            MinutesIndexSource.LIVE_PAGE,
            None,
            None,
            None,
            "https://example.test/a.pdf",
            MinutesFileFormat.PDF,
        )


def test_commit_refuses_a_plan_that_differs_from_the_reviewed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_minutes_index(tmp_path, plan_path, is_commit=False)
    reviewed_plan = json.loads(plan_path.read_text())
    reviewed_plan["rows"][0]["printed_label"] = "Changed"
    plan_path.write_text(json.dumps(reviewed_plan))

    with pytest.raises(HansardWriteCheckError, match="differs from the reviewed plan"):
        apply_minutes_index(tmp_path, plan_path, is_commit=True)

    assert CRUDMinutesIndexCapture(scratch_session).get_count() == 0
    assert _get_minutes(scratch_session, date(2021, 8, 3)) is None


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_reports(scratch_session)
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_minutes_index(tmp_path, plan_path, is_commit=False)
    monkeypatch.setattr(
        apply_minutes_index_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_minutes_index(tmp_path, plan_path, is_commit=True)

    assert CRUDMinutesIndexCapture(scratch_session).get_count() == 0
    assert _get_minutes(scratch_session, date(2021, 8, 3)) is None


def test_file_not_found_row_moves_to_listed_when_a_new_address_appears(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    scratch_session.add_all(
        [
            Minutes(
                sitting_date=date(2021, 8, 3),
                status=MinutesStatus.FILE_NOT_FOUND,
                index_source=MinutesIndexSource.ARCHIVE_INDEX_CAPTURE,
                file_url="https://example.test/old-address.pdf",
                sha256="kept-sha",
                status_note="No Archive capture returned a file",
            ),
            Minutes(
                sitting_date=date(2021, 8, 2),
                status=MinutesStatus.FILE_NOT_FOUND,
                index_source=MinutesIndexSource.ARCHIVE_INDEX_CAPTURE,
                file_url=_ARCHIVE_2021_FILE_URL_2_AUGUST,
            ),
        ]
    )
    scratch_session.commit()
    before_move = _get_minutes(scratch_session, date(2021, 8, 3))
    assert before_move is not None
    first_id = before_move.id
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_minutes_index(tmp_path, plan_path, is_commit=False)
    plan = MinutesIndexPlan.model_validate_json(plan_path.read_text())

    apply_minutes_index(tmp_path, plan_path, is_commit=True)

    moved_row = next(
        planned_row
        for planned_row in plan.rows
        if planned_row.sitting_date == date(2021, 8, 3)
    )
    assert moved_row.expected_status == MinutesStatus.FILE_NOT_FOUND
    third_august = _get_minutes(scratch_session, date(2021, 8, 3))
    assert third_august is not None
    assert third_august.id == first_id
    assert third_august.status == MinutesStatus.LISTED
    assert third_august.file_url == _ARCHIVE_2021_FILE_URL_3_AUGUST
    assert third_august.sha256 == "kept-sha"
    assert third_august.status_note is None
    second_august = _get_minutes(scratch_session, date(2021, 8, 2))
    assert second_august is not None
    assert second_august.status == MinutesStatus.FILE_NOT_FOUND


def test_manifest_entry_with_an_error_key_is_refused(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_captures(tmp_path)
    manifest = json.loads((tmp_path / "captures.json").read_text())
    manifest[1]["error"] = "timed out"
    (tmp_path / "captures.json").write_text(json.dumps(manifest))

    with pytest.raises(ValidationError):
        apply_minutes_index(tmp_path, tmp_path / "plan.json", is_commit=False)


def test_archive_page_of_the_new_site_has_zero_rows_and_is_logged(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_captures(tmp_path)
    (tmp_path / _NEW_SITE_FILE).write_text(_NEW_SITE_PAGE)
    manifest = json.loads((tmp_path / "captures.json").read_text())
    manifest.append(_build_manifest_entry(tmp_path / _NEW_SITE_FILE, "20260101000000"))
    (tmp_path / "captures.json").write_text(json.dumps(manifest))
    plan_path = tmp_path / "plan.json"

    apply_minutes_index(tmp_path, plan_path, is_commit=False)

    assert f"Capture {_NEW_SITE_FILE}: 0 rows" in log_recorder.messages
    plan = MinutesIndexPlan.model_validate_json(plan_path.read_text())
    assert len(plan.rows) == _FIXTURE_ROW_COUNT

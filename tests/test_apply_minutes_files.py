import hashlib
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import populate.minutes_files as minutes_files_module
import scripts.apply_minutes_files as apply_minutes_files_script
from crud.minutes import CRUDMinutes
from database.minutes import Minutes
from enums import (
    MinutesFileFormat,
    MinutesIndexSource,
    MinutesStatus,
)
from exceptions import (
    HansardMinutesFileError,
    HansardWriteCheckError,
    HansardWriteTargetError,
)
from schemas.minutes_files_plan import MinutesFilesPlan
from scripts.apply_minutes_files import apply_minutes_files

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures" / "minutes"
_PDF_FIXTURE = "vp-10jan18-first-pages.pdf"
_WORD_FIXTURE = "vp0592008_7.doc"
_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_PDF_URL = "https://www.parliament.gov.sg/api/media/id-a/VP-10Jan2018.pdf"
_PDF_URL_WITH_QUERY = f"{_PDF_URL}?sfvrsn=1"
_OTHER_PDF_URL = "https://www.parliament.gov.sg/api/media/id-b/VP-other.pdf"
_WORD_URL = "https://www.parliament.gov.sg/docs/default-source/Votes-and-Proceedings/vp0592008_7.doc"
_WORD_COPY_URL = "https://www.parliament.gov.sg/docs/default-source/Votes-and-Proceedings/vp0592008_7-copy.doc"
_FETCHED_AT = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
_PDF_DATE = date(2018, 1, 10)
_WORD_DATE = date(2008, 10, 21)
_NO_FILE_NOTE = "No Archive capture or live address returned a PDF or Word file"
_OLDER_NOTE = "No index row or file listing names this sitting; it is older than the live page's oldest row"
_OTHER_TEXT = "WEDNESDAY, 10 JANUARY 2018 votes and proceedings of another kind"
_BOTH_FILES_COUNT = 2
_KEPT_CV_TEXT = "WEDNESDAY, 10 JANUARY 2018 keith chua cv"


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _build_record(
    file_url: str,
    file_name: Optional[str],
    content: bytes,
    is_signature_passed: bool,
    status_code: int = 200,
) -> dict:
    return {
        "file_url": file_url,
        "request_url": file_url,
        "archive_timestamp": None,
        "status_code": status_code,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "file_name": file_name,
        "fetched_at": _FETCHED_AT.isoformat(),
        "is_signature_passed": is_signature_passed,
    }


def _build_file_record(
    directory: Path, file_url: str, fixture_name: str, file_name: str
) -> dict:
    shutil.copy(_FIXTURE_DIRECTORY / fixture_name, directory / file_name)
    return _build_record(
        file_url, file_name, (directory / file_name).read_bytes(), True
    )


def _build_failed_record(file_url: str) -> dict:
    return _build_record(file_url, None, b"not found", False, status_code=404)


def _write_ledger(directory: Path, records: list[dict]) -> None:
    (directory / "fetches.json").write_text(json.dumps(records))


def _add_minutes(session: Session, minutes_rows: list[Minutes]) -> None:
    CRUDMinutes(session).add_many(minutes_rows)
    session.commit()


def _get_minutes(session: Session, sitting_date: date) -> Optional[Minutes]:
    session.expire_all()
    stored_rows = CRUDMinutes(session).get_by_sitting_dates([sitting_date])
    return stored_rows[0] if stored_rows else None


def _get_minutes_id(session: Session, sitting_date: date) -> int:
    stored_minutes = _get_minutes(session, sitting_date)
    assert stored_minutes is not None
    assert stored_minutes.id is not None
    return stored_minutes.id


def _read_plan(plan_path: Path) -> MinutesFilesPlan:
    return MinutesFilesPlan.model_validate_json(plan_path.read_text())


def _run_commit(directory: Path) -> Path:
    plan_path = directory / "plan.json"
    apply_minutes_files(directory, plan_path, is_commit=False)
    apply_minutes_files(directory, plan_path, is_commit=True)
    return plan_path


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_minutes_files_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_minutes_files_script, "logger", recorder)
    return recorder


def test_commit_stores_the_text_of_an_index_file(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                index_source=MinutesIndexSource.ARCHIVE_INDEX_CAPTURE,
                file_url=_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    record = _build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")
    _write_ledger(tmp_path, [record])

    _run_commit(tmp_path)

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.TEXT_STORED
    assert stored_minutes.sha256 == record["sha256"]
    assert stored_minutes.size_bytes == record["size_bytes"]
    assert stored_minutes.file_bytes is None
    assert stored_minutes.fetched_at == _FETCHED_AT
    assert stored_minutes.file_format == MinutesFileFormat.PDF
    assert stored_minutes.extracted_text is not None
    assert "JANUARY 2018" in stored_minutes.extracted_text


def test_head_date_mismatch_needs_review(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=date(2018, 1, 11),
                status=MinutesStatus.LISTED,
                file_url=_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )

    _run_commit(tmp_path)

    stored_minutes = _get_minutes(scratch_session, date(2018, 1, 11))
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.NEEDS_REVIEW
    assert stored_minutes.status_note is not None
    assert "10 January 2018" in stored_minutes.status_note


def test_listing_file_moves_a_not_yet_listed_row(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [Minutes(sitting_date=_WORD_DATE, status=MinutesStatus.NOT_YET_LISTED)],
    )
    first_id = _get_minutes_id(scratch_session, _WORD_DATE)
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _WORD_URL, _WORD_FIXTURE, "1.doc")]
    )

    _run_commit(tmp_path)

    stored_minutes = _get_minutes(scratch_session, _WORD_DATE)
    assert stored_minutes is not None
    assert stored_minutes.id == first_id
    assert stored_minutes.status == MinutesStatus.TEXT_STORED
    assert stored_minutes.index_source == MinutesIndexSource.ARCHIVE_FILE_LISTING
    assert stored_minutes.file_url == _WORD_URL
    assert stored_minutes.file_format == MinutesFileFormat.WORD


def test_listing_file_for_a_date_with_no_row_inserts_one(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _WORD_URL, _WORD_FIXTURE, "1.doc")]
    )
    plan_path = tmp_path / "plan.json"

    apply_minutes_files(tmp_path, plan_path, is_commit=False)
    apply_minutes_files(tmp_path, plan_path, is_commit=True)

    assert _read_plan(plan_path).files[0].is_new_row
    stored_minutes = _get_minutes(scratch_session, _WORD_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.TEXT_STORED
    assert stored_minutes.index_source == MinutesIndexSource.ARCHIVE_FILE_LISTING
    assert stored_minutes.file_url == _WORD_URL


def test_listing_file_for_a_date_an_index_row_already_gives_is_flagged(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                file_url=_OTHER_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )
    plan_path = tmp_path / "plan.json"

    apply_minutes_files(tmp_path, plan_path, is_commit=False)

    plan = _read_plan(plan_path)
    assert plan.files == []
    assert [(flagged.file_url, flagged.reason) for flagged in plan.flagged] == [
        (_PDF_URL, "an index row already gives this date")
    ]
    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.LISTED
    assert stored_minutes.file_url == _OTHER_PDF_URL


@pytest.mark.parametrize(
    ("head_dates", "reason"),
    [
        ([], "the head prints no date"),
        (
            [date(2018, 1, 10), date(2018, 1, 11)],
            "the head prints more than one date",
        ),
    ],
)
def test_listing_file_whose_head_prints_no_single_date_is_flagged(
    head_dates: list[date],
    reason: str,
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        minutes_files_module, "get_minutes_head_dates", lambda text: head_dates
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )
    plan_path = tmp_path / "plan.json"

    apply_minutes_files(tmp_path, plan_path, is_commit=False)

    plan = _read_plan(plan_path)
    assert plan.files == []
    assert [flagged.reason for flagged in plan.flagged] == [reason]


def test_listing_file_whose_head_does_not_read_votes_and_proceedings_is_flagged(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        minutes_files_module, "get_minutes_pdf_text", lambda content: _KEPT_CV_TEXT
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )

    plan_path = _run_commit(tmp_path)

    plan = _read_plan(plan_path)
    assert plan.files == []
    assert [flagged.reason for flagged in plan.flagged] == [
        "the head does not read VOTES AND PROCEEDINGS"
    ]
    assert _get_minutes(scratch_session, _PDF_DATE) is None


def test_two_listing_files_for_one_date_are_both_flagged(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_ledger(
        tmp_path,
        [
            _build_file_record(tmp_path, _WORD_URL, _WORD_FIXTURE, "1.doc"),
            _build_file_record(tmp_path, _WORD_COPY_URL, _WORD_FIXTURE, "2.doc"),
        ],
    )

    plan_path = _run_commit(tmp_path)

    plan = _read_plan(plan_path)
    assert plan.files == []
    assert sorted(flagged.file_url for flagged in plan.flagged) == [
        _WORD_COPY_URL,
        _WORD_URL,
    ]
    assert {flagged.reason for flagged in plan.flagged} == {
        "two listing files give this date"
    }
    assert _get_minutes(scratch_session, _WORD_DATE) is None


def test_listing_file_moves_a_file_not_found_row(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_WORD_DATE,
                status=MinutesStatus.FILE_NOT_FOUND,
                file_url="https://example.test/old.doc",
                status_note="old note",
            )
        ],
    )
    first_id = _get_minutes_id(scratch_session, _WORD_DATE)
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _WORD_URL, _WORD_FIXTURE, "1.doc")]
    )

    _run_commit(tmp_path)

    stored_minutes = _get_minutes(scratch_session, _WORD_DATE)
    assert stored_minutes is not None
    assert stored_minutes.id == first_id
    assert stored_minutes.status == MinutesStatus.TEXT_STORED
    assert stored_minutes.index_source == MinutesIndexSource.ARCHIVE_FILE_LISTING
    assert stored_minutes.file_url == _WORD_URL
    assert stored_minutes.status_note is None


def test_address_with_no_passing_record_is_file_not_found(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                file_url=_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    _write_ledger(tmp_path, [_build_failed_record(_PDF_URL)])

    _run_commit(tmp_path)

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.FILE_NOT_FOUND
    assert stored_minutes.status_note == _NO_FILE_NOTE
    assert stored_minutes.sha256 is None


def test_not_yet_listed_older_than_the_live_page_becomes_file_not_found(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(sitting_date=date(2010, 1, 4), status=MinutesStatus.NOT_YET_LISTED),
            Minutes(sitting_date=date(2026, 9, 1), status=MinutesStatus.NOT_YET_LISTED),
            Minutes(
                sitting_date=date(2026, 8, 5),
                status=MinutesStatus.LISTED,
                index_source=MinutesIndexSource.LIVE_PAGE,
                file_url=_OTHER_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            ),
        ],
    )
    _write_ledger(tmp_path, [])

    _run_commit(tmp_path)

    older_minutes = _get_minutes(scratch_session, date(2010, 1, 4))
    assert older_minutes is not None
    assert older_minutes.status == MinutesStatus.FILE_NOT_FOUND
    assert older_minutes.status_note == _OLDER_NOTE
    newer_minutes = _get_minutes(scratch_session, date(2026, 9, 1))
    assert newer_minutes is not None
    assert newer_minutes.status == MinutesStatus.NOT_YET_LISTED


def test_not_yet_listed_stays_when_no_live_page_row_is_stored(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [Minutes(sitting_date=date(2010, 1, 4), status=MinutesStatus.NOT_YET_LISTED)],
    )
    _write_ledger(tmp_path, [])

    _run_commit(tmp_path)

    older_minutes = _get_minutes(scratch_session, date(2010, 1, 4))
    assert older_minutes is not None
    assert older_minutes.status == MinutesStatus.NOT_YET_LISTED
    assert (
        "No LIVE_PAGE row is stored: no NOT_YET_LISTED row moves to FILE_NOT_FOUND"
        in log_recorder.messages
    )


def test_sha256_mismatch_raises(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )
    stored_bytes = bytearray((tmp_path / "1.pdf").read_bytes())
    stored_bytes[-1] ^= 1
    (tmp_path / "1.pdf").write_bytes(bytes(stored_bytes))

    with pytest.raises(HansardMinutesFileError, match="1.pdf"):
        apply_minutes_files(tmp_path, tmp_path / "plan.json", is_commit=False)


def test_second_commit_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                file_url=_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    _write_ledger(
        tmp_path,
        [
            _build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf"),
            _build_file_record(tmp_path, _WORD_URL, _WORD_FIXTURE, "2.doc"),
        ],
    )
    _run_commit(tmp_path)
    plan_path = tmp_path / "second-plan.json"

    apply_minutes_files(tmp_path, plan_path, is_commit=False)
    apply_minutes_files(tmp_path, plan_path, is_commit=True)

    plan = _read_plan(plan_path)
    assert plan.files == []
    assert plan.already_stored_count == _BOTH_FILES_COUNT


def test_dry_run_writes_the_plan_file_only(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                file_url=_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )
    plan_path = tmp_path / "plan.json"

    apply_minutes_files(tmp_path, plan_path, is_commit=False)

    assert log_recorder.messages == [
        "Files: 1 planned, 0 already stored, 0 flagged",
        "Files by status: TEXT_STORED 1",
        "Rows: 0 new, 0 moved by a listing file",
        "No LIVE_PAGE row is stored: no NOT_YET_LISTED row moves to FILE_NOT_FOUND",
        "Dry run: nothing written",
    ]
    assert len(_read_plan(plan_path).files) == 1
    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.LISTED
    assert stored_minutes.sha256 is None


def test_commit_refuses_a_plan_that_differs_from_the_reviewed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                file_url=_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )
    plan_path = tmp_path / "plan.json"
    apply_minutes_files(tmp_path, plan_path, is_commit=False)
    reviewed_plan = json.loads(plan_path.read_text())
    reviewed_plan["files"][0]["status_note"] = "Changed"
    plan_path.write_text(json.dumps(reviewed_plan))

    with pytest.raises(HansardWriteCheckError, match="differs from the reviewed plan"):
        apply_minutes_files(tmp_path, plan_path, is_commit=True)

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.LISTED


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                file_url=_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )
    plan_path = tmp_path / "plan.json"
    apply_minutes_files(tmp_path, plan_path, is_commit=False)
    monkeypatch.setattr(
        apply_minutes_files_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_minutes_files(tmp_path, plan_path, is_commit=True)

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.LISTED


def test_text_changed_after_the_plan_is_refused(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                file_url=_PDF_URL,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )
    plan_path = tmp_path / "plan.json"
    apply_minutes_files(tmp_path, plan_path, is_commit=False)
    monkeypatch.setattr(
        minutes_files_module, "get_minutes_pdf_text", lambda content: _OTHER_TEXT
    )

    with pytest.raises(HansardWriteCheckError):
        apply_minutes_files(tmp_path, plan_path, is_commit=True)

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.LISTED
    assert stored_minutes.sha256 is None


def test_query_less_ledger_address_of_a_text_stored_row_counts_as_already_stored(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.TEXT_STORED,
                file_url=_PDF_URL_WITH_QUERY,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )
    plan_path = tmp_path / "plan.json"

    apply_minutes_files(tmp_path, plan_path, is_commit=False)

    plan = _read_plan(plan_path)
    assert plan.files == []
    assert plan.flagged == []
    assert plan.already_stored_count == 1


def test_query_less_ledger_address_of_a_listed_row_stores_the_text_on_that_row(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                file_url=_PDF_URL_WITH_QUERY,
                file_format=MinutesFileFormat.PDF,
            )
        ],
    )
    first_id = _get_minutes_id(scratch_session, _PDF_DATE)
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )

    _run_commit(tmp_path)

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.id == first_id
    assert stored_minutes.status == MinutesStatus.TEXT_STORED
    assert stored_minutes.file_url == _PDF_URL_WITH_QUERY


def test_two_stored_rows_under_one_address_are_flagged(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_minutes(
        scratch_session,
        [
            Minutes(
                sitting_date=_PDF_DATE,
                status=MinutesStatus.LISTED,
                file_url=_PDF_URL_WITH_QUERY,
                file_format=MinutesFileFormat.PDF,
            ),
            Minutes(
                sitting_date=date(2018, 1, 11),
                status=MinutesStatus.LISTED,
                file_url=f"{_PDF_URL}?sfvrsn=2",
                file_format=MinutesFileFormat.PDF,
            ),
        ],
    )
    _write_ledger(
        tmp_path, [_build_file_record(tmp_path, _PDF_URL, _PDF_FIXTURE, "1.pdf")]
    )
    plan_path = tmp_path / "plan.json"

    apply_minutes_files(tmp_path, plan_path, is_commit=False)

    plan = _read_plan(plan_path)
    assert plan.files == []
    assert [(flagged.file_url, flagged.reason) for flagged in plan.flagged] == [
        (_PDF_URL, "two stored rows name this address")
    ]

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import populate.egazette_supplements as egazette_supplements_populate
import scripts.apply_egazette_supplements as apply_egazette_supplements_script
from crud.egazette_supplement import CRUDEgazetteSupplement
from enums import EgazetteSupplementKind
from exceptions import (
    HansardEgazetteSupplementError,
    HansardWriteCheckError,
    HansardWriteTargetError,
)
from schemas.egazette_fetch import EgazetteFetchRecord, EgazetteFetchRecords
from schemas.egazette_supplement_plan import EgazetteSupplementPlan
from scripts.apply_egazette_supplements import apply_egazette_supplements

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_BILL_TEXT = (
    "Water Bill\nBill No. 3/2024.\nRead the first time on 9 January 2024.\nA BILL\n"
)
_ACT_TEXT = (
    "The following Act was passed by Parliament on 15 October 2025 and assented\n"
    "to by the President on 11 November 2025:—\nNo. 20 of 2025.\nI assent.\n"
    "President.\n11 November 2025.\nTax Bill\nBill No. 11/2025.\n"
    "Read the first time on 25 September 2025.\n"
)
_UNPARSEABLE_TEXT = "A Gazette cover with no bill\n"
_PARSED_COUNT = 2
_FETCHED_AT = datetime(2026, 11, 8, 3, 0, tzinfo=timezone.utc)
_FILE_PATH_TO_TEXT = {
    "2024/bills/03.pdf": _BILL_TEXT,
    "2025/acts/11.pdf": _ACT_TEXT,
    "2025/bills/09.pdf": _UNPARSEABLE_TEXT,
}


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _build_fetch_record(
    file_path: str, supplement_kind: EgazetteSupplementKind, number: int
) -> EgazetteFetchRecord:
    content = file_path.encode()
    return EgazetteFetchRecord(
        url=f"https://example.test/{file_path}",
        year=int(file_path[:4]),
        supplement_kind=supplement_kind,
        number=number,
        status_code=200,
        fetched_at=_FETCHED_AT,
        file_path=file_path,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _write_harvest(directory: Path) -> None:
    fetch_records = [
        _build_fetch_record("2024/bills/03.pdf", EgazetteSupplementKind.BILLS, 3),
        _build_fetch_record("2025/acts/11.pdf", EgazetteSupplementKind.ACTS, 11),
        _build_fetch_record("2025/bills/09.pdf", EgazetteSupplementKind.BILLS, 9),
        EgazetteFetchRecord(
            url="https://example.test/2025/bills/10.pdf",
            year=2025,
            supplement_kind=EgazetteSupplementKind.BILLS,
            number=10,
            status_code=403,
            fetched_at=_FETCHED_AT,
            file_path=None,
            size_bytes=None,
            sha256=None,
        ),
    ]
    for fetch_record in fetch_records:
        if fetch_record.file_path is None:
            continue
        file_path = directory / fetch_record.file_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(fetch_record.file_path.encode())
    (directory / "fetches.json").write_text(
        EgazetteFetchRecords(fetch_records).model_dump_json(indent=1), encoding="utf8"
    )


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_egazette_supplements_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_egazette_supplements_script, "logger", recorder)
    monkeypatch.setattr(
        egazette_supplements_populate,
        "get_egazette_supplement_text",
        lambda file_path: _FILE_PATH_TO_TEXT[
            file_path.relative_to(file_path.parents[2]).as_posix()
        ],
    )
    return recorder


def _get_stored_count(session: Session) -> int:
    session.expire_all()
    return CRUDEgazetteSupplement(session).get_count()


def test_dry_run_logs_the_counts_and_writes_the_plan_file_only(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"

    apply_egazette_supplements(tmp_path, plan_path, is_commit=False)

    assert log_recorder.messages == [
        "Files by year and kind: 2024 BILLS 1, 2025 ACTS 1",
        "Parsed: 2; unparsed: 1; 403 records: 1",
        "Unparsed: https://example.test/2025/bills/09.pdf: No Bill No. line found in the text",
        "Rows already stored: 0; to insert: 2; to update: 0",
        "Dry run: nothing written",
    ]
    plan = EgazetteSupplementPlan.model_validate_json(plan_path.read_text())
    assert [supplement.bill_number for supplement in plan.supplements] == [
        "3/2024",
        "11/2025",
    ]
    assert plan.supplements[1].printed_act_number == "20 of 2025"
    assert _get_stored_count(scratch_session) == 0


def test_commit_stores_the_reviewed_plan_and_a_second_commit_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_egazette_supplements(tmp_path, plan_path, is_commit=False)

    apply_egazette_supplements(tmp_path, plan_path, is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    assert _get_stored_count(scratch_session) == _PARSED_COUNT
    egazette_supplement_rows = CRUDEgazetteSupplement(scratch_session).get_rows()
    assert egazette_supplement_rows[0].fetched_at == _FETCHED_AT
    assert egazette_supplement_rows[0].bill_id is None
    log_recorder.messages.clear()

    apply_egazette_supplements(tmp_path, plan_path, is_commit=True)

    assert "Rows already stored: 2; to insert: 0; to update: 0" in log_recorder.messages
    scratch_session.expire_all()
    assert (
        CRUDEgazetteSupplement(scratch_session).get_rows() == egazette_supplement_rows
    )


def test_commit_updates_a_stored_row_that_differs_and_keeps_its_id(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_egazette_supplements(tmp_path, plan_path, is_commit=False)
    apply_egazette_supplements(tmp_path, plan_path, is_commit=True)
    row_ids = [
        egazette_supplement_row.id
        for egazette_supplement_row in CRUDEgazetteSupplement(
            scratch_session
        ).get_rows()
    ]
    monkeypatch.setitem(
        _FILE_PATH_TO_TEXT,
        "2024/bills/03.pdf",
        _BILL_TEXT.replace("Water Bill", "Drainage Bill"),
    )
    apply_egazette_supplements(tmp_path, plan_path, is_commit=False)

    apply_egazette_supplements(tmp_path, plan_path, is_commit=True)

    assert "Rows already stored: 2; to insert: 0; to update: 1" in log_recorder.messages
    scratch_session.expire_all()
    egazette_supplement_rows = CRUDEgazetteSupplement(scratch_session).get_rows()
    assert [
        egazette_supplement_row.id
        for egazette_supplement_row in egazette_supplement_rows
    ] == row_ids
    assert egazette_supplement_rows[0].printed_title == "Drainage Bill"


def test_commit_refuses_a_plan_that_differs_from_the_reviewed_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_egazette_supplements(tmp_path, plan_path, is_commit=False)
    monkeypatch.setitem(
        _FILE_PATH_TO_TEXT,
        "2024/bills/03.pdf",
        _BILL_TEXT.replace("Water Bill", "Drainage Bill"),
    )

    with pytest.raises(
        HansardWriteCheckError, match="The plan differs from the reviewed plan"
    ):
        apply_egazette_supplements(tmp_path, plan_path, is_commit=True)

    assert _get_stored_count(scratch_session) == 0


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_egazette_supplements(tmp_path, plan_path, is_commit=False)
    monkeypatch.setattr(
        apply_egazette_supplements_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_egazette_supplements(tmp_path, plan_path, is_commit=True)

    assert _get_stored_count(scratch_session) == 0


def test_a_file_whose_sha256_differs_from_its_fetch_record_raises(
    log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_harvest(tmp_path)
    (tmp_path / "2024/bills/03.pdf").write_bytes(b"changed")

    with pytest.raises(HansardEgazetteSupplementError, match="has SHA-256"):
        apply_egazette_supplements(tmp_path, tmp_path / "plan.json", is_commit=False)

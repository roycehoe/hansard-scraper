import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_bills_supplement as apply_bills_supplement_script
from crud.bills_supplement_capture import CRUDBillsSupplementCapture
from crud.bills_supplement_entry import CRUDBillsSupplementEntry
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.bills_supplement_plan import BillsSupplementPlan
from scripts.apply_bills_supplement import apply_bills_supplement

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_FIRST_CAPTURE_URL = "https://web.archive.org/web/20200101000000id_/https://sso/a"
_SECOND_CAPTURE_URL = "https://web.archive.org/web/20210101000000id_/https://sso/b"
_ROW = """
<tr data-toggle="popover"><td><a class="non-ajax" href="/Bills-Supp/{number}-{year}/Published/{year}0301?DocDate={year}0301">{title}</a></td>
<td class="hidden-xs col-no">Bill {number} of {year}</td></tr>
"""


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _write_captures(directory: Path) -> None:
    first_html = _ROW.format(number=1, year=2015, title="Alpha Bill") + _ROW.format(
        number=2, year=2016, title="Beta Bill"
    )
    second_html = _ROW.format(number=2, year=2016, title="Beta Bill") + _ROW.format(
        number=3, year=2017, title="Gamma Bill"
    )
    (directory / "a.html").write_text(first_html)
    (directory / "b.html").write_text(second_html)
    manifest = [
        {
            "file_name": "a.html",
            "original_url": "https://sso/a",
            "archive_timestamp": "20200101000000",
            "capture_url": _FIRST_CAPTURE_URL,
        },
        {
            "file_name": "b.html",
            "original_url": "https://sso/b",
            "archive_timestamp": "20210101000000",
            "capture_url": _SECOND_CAPTURE_URL,
        },
    ]
    (directory / "captures.json").write_text(json.dumps(manifest))


def _get_stored_counts(session: Session) -> tuple[int, int]:
    session.expire_all()
    return (
        CRUDBillsSupplementCapture(session).get_count(),
        CRUDBillsSupplementEntry(session).get_count(),
    )


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_bills_supplement_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_bills_supplement_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_counts_and_writes_the_plan_file_only(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"

    apply_bills_supplement(tmp_path, plan_path, is_commit=False)

    assert log_recorder.messages == [
        "Captures: 2",
        "Capture a.html: 2 rows",
        "Capture b.html: 2 rows",
        "Entries: 3 distinct, 1 duplicates dropped",
        "Entries by decade of bill number: 2010s 3",
        "Already stored: 0 captures, 0 entries",
        "Dry run: nothing written",
    ]
    plan = BillsSupplementPlan.model_validate_json(plan_path.read_text())
    assert [entry.bill_number for entry in plan.entries] == [
        "1/2015",
        "2/2016",
        "3/2017",
    ]
    assert _get_stored_counts(scratch_session) == (0, 0)


def test_commit_stores_the_plan_and_a_second_commit_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_bills_supplement(tmp_path, plan_path, is_commit=False)

    apply_bills_supplement(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (2, 3)
    entry_rows = CRUDBillsSupplementEntry(scratch_session).get_rows()
    capture_url_by_id = {
        capture_row.id: capture_row.capture_url
        for capture_row in CRUDBillsSupplementCapture(scratch_session).get_rows()
    }
    assert [
        (entry_row.bill_number, capture_url_by_id[entry_row.capture_id])
        for entry_row in entry_rows
    ] == [
        ("1/2015", _FIRST_CAPTURE_URL),
        ("2/2016", _FIRST_CAPTURE_URL),
        ("3/2017", _SECOND_CAPTURE_URL),
    ]
    first_ids = [entry_row.id for entry_row in entry_rows]

    apply_bills_supplement(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (2, 3)
    assert "Already stored: 2 captures, 3 entries" in log_recorder.messages
    assert [
        entry_row.id
        for entry_row in CRUDBillsSupplementEntry(scratch_session).get_rows()
    ] == first_ids


def test_commit_refuses_a_plan_that_differs_from_the_reviewed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_bills_supplement(tmp_path, plan_path, is_commit=False)
    reviewed_plan = json.loads(plan_path.read_text())
    reviewed_plan["entries"][0]["printed_title"] = "Changed Bill"
    plan_path.write_text(json.dumps(reviewed_plan))

    with pytest.raises(HansardWriteCheckError, match="differs from the reviewed plan"):
        apply_bills_supplement(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (0, 0)


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_bills_supplement(tmp_path, plan_path, is_commit=False)
    monkeypatch.setattr(
        apply_bills_supplement_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_bills_supplement(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (0, 0)

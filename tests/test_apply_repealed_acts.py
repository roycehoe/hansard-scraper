import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_repealed_acts as apply_repealed_acts_script
from crud.repealed_act_entry import CRUDRepealedActEntry
from crud.repealed_acts_capture import CRUDRepealedActsCapture
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.repealed_acts_plan import RepealedActsPlan
from scripts.apply_repealed_acts import apply_repealed_acts

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_FIRST_CAPTURE_URL = "https://web.archive.org/web/20200101000000id_/https://sso/a"
_SECOND_CAPTURE_URL = "https://web.archive.org/web/20210101000000id_/https://sso/b"
_ROW = """
<tr data-toggle="popover"><td><a class="non-ajax" href="/Act/{code}/Repealed/20240101?DocDate=20231231">{title}</a></td></tr>
"""


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _write_captures(directory: Path) -> None:
    first_html = _ROW.format(code="AA2015", title="Alpha Act") + _ROW.format(
        code="BB2016", title="Beta Act"
    )
    second_html = _ROW.format(code="BB2016", title="Beta Act") + _ROW.format(
        code="CCUNKNOWN", title="Gamma Act"
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
        CRUDRepealedActsCapture(session).get_count(),
        CRUDRepealedActEntry(session).get_count(),
    )


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_repealed_acts_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_repealed_acts_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_counts_and_writes_the_plan_file_only(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"

    apply_repealed_acts(tmp_path, plan_path, is_commit=False)

    assert log_recorder.messages == [
        "Captures: 2",
        "Capture a.html: 2 rows",
        "Capture b.html: 2 rows",
        "Entries: 3 distinct, 1 duplicates dropped",
        "Entries by decade of enactment year: 2010s 2, no year 1",
        "Already stored: 0 captures, 0 entries",
        "Dry run: nothing written",
    ]
    plan = RepealedActsPlan.model_validate_json(plan_path.read_text())
    assert [entry.sso_code for entry in plan.entries] == [
        "AA2015",
        "BB2016",
        "CCUNKNOWN",
    ]
    assert _get_stored_counts(scratch_session) == (0, 0)


def test_commit_stores_the_plan_and_a_second_commit_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_repealed_acts(tmp_path, plan_path, is_commit=False)

    apply_repealed_acts(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (2, 3)
    entry_rows = CRUDRepealedActEntry(scratch_session).get_rows()
    capture_url_by_id = {
        capture_row.id: capture_row.capture_url
        for capture_row in CRUDRepealedActsCapture(scratch_session).get_rows()
    }
    assert [
        (entry_row.sso_code, capture_url_by_id[entry_row.capture_id])
        for entry_row in entry_rows
    ] == [
        ("AA2015", _FIRST_CAPTURE_URL),
        ("BB2016", _FIRST_CAPTURE_URL),
        ("CCUNKNOWN", _SECOND_CAPTURE_URL),
    ]
    first_ids = [entry_row.id for entry_row in entry_rows]

    apply_repealed_acts(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (2, 3)
    assert "Already stored: 2 captures, 3 entries" in log_recorder.messages
    assert [
        entry_row.id for entry_row in CRUDRepealedActEntry(scratch_session).get_rows()
    ] == first_ids


def test_commit_refuses_a_plan_that_differs_from_the_reviewed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_repealed_acts(tmp_path, plan_path, is_commit=False)
    reviewed_plan = json.loads(plan_path.read_text())
    reviewed_plan["entries"][0]["printed_title"] = "Changed Act"
    plan_path.write_text(json.dumps(reviewed_plan))

    with pytest.raises(HansardWriteCheckError, match="differs from the reviewed plan"):
        apply_repealed_acts(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (0, 0)


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_captures(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_repealed_acts(tmp_path, plan_path, is_commit=False)
    monkeypatch.setattr(
        apply_repealed_acts_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_repealed_acts(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (0, 0)

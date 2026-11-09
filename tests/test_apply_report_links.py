import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_report_links as apply_report_links_script
from crud.report_link import CRUDReportLink
from database.report import Report
from database.speech import Speech
from enums import (
    ReportLinkRule,
    ReportLinkType,
    ReportLinkUnplacedReason,
    ReportType,
    ReportVersion,
)
from exceptions import HansardWriteTargetError
from scripts.apply_report_links import apply_report_links

_SOURCE_REPORT_ID = "SOURCE#1"
_TARGET_REPORT_ID = "TARGET#1"
_TARGET_TITLE = "Title A"
_PLACED_TRANSCRIPT = (
    f'[Please refer to "{_TARGET_TITLE}", Official Report, 3 March 2020, '
    "Volume 94, Issue No 12, Written Answers section]"
)
_UNPLACED_TRANSCRIPT = (
    '[Please refer to "Title B", Official Report, 4 March 2020, '
    "Volume 94, Issue No 13, Written Answers section]"
)
_PLAN_LOG = "Plan: 1 links, 1 unplaced citations"
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_UNPROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5435/hansard_launch"


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


@pytest.fixture(autouse=True)
def _no_report_link_title_corrections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("populate.report_links.get_report_link_title_corrections", list)


def _add_report(
    session: Session,
    report_id: str,
    report_type: ReportType,
    sitting_date: datetime,
    title: str,
) -> Report:
    report = Report(
        volume_number=94,
        parliament_number=14,
        sitting_date=sitting_date,
        speech_number=1,
        original_title=title,
        title=title,
        report_id=report_id,
        report_type=report_type,
        content="Text.",
        report_version=ReportVersion.SPRS3,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _seed_citations(session: Session) -> None:
    source = _add_report(
        session,
        _SOURCE_REPORT_ID,
        ReportType.ORAL_ANSWER,
        datetime(2020, 3, 10),
        "Source title",
    )
    _add_report(
        session,
        _TARGET_REPORT_ID,
        ReportType.ORAL_ANSWER,
        datetime(2020, 3, 3),
        _TARGET_TITLE,
    )
    assert source.id is not None
    for ordinal, transcript in enumerate(
        (_PLACED_TRANSCRIPT, _UNPLACED_TRANSCRIPT), start=1
    ):
        session.add(
            Speech(
                ordinal=ordinal,
                speaker="Mr A",
                transcript=transcript,
                sitting_date=source.sitting_date,
                report_type=source.report_type,
                report_id=source.id,
            )
        )
    session.commit()


def _get_stored_keys(
    session: Session,
) -> list[tuple[ReportLinkType, ReportLinkRule, str, str]]:
    return [
        (
            report_link_row.link_type,
            report_link_row.rule,
            report_link_row.source_report_id,
            report_link_row.target_report_id,
        )
        for report_link_row in CRUDReportLink(session).get_rows()
    ]


_PLANNED_KEYS = [
    (
        ReportLinkType.REPLY,
        ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE,
        _SOURCE_REPORT_ID,
        _TARGET_REPORT_ID,
    )
]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_report_links_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_report_links_script, "logger", recorder)
    monkeypatch.setattr(
        apply_report_links_script,
        "settings",
        SimpleNamespace(database_url=_UNPROTECTED_DATABASE_URL),
    )
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_citations(scratch_session)

    apply_report_links(is_commit=False, unplaced_path=None)

    assert (
        f"{ReportLinkType.REPLY} {ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE}: 1 links"
        in log_recorder.messages
    )
    assert (
        f"Unplaced {ReportLinkUnplacedReason.NO_SITTING_ON_PRINTED_DATE}: 1"
        in log_recorder.messages
    )
    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_stored_keys(scratch_session) == []


def test_commit_writes_the_planned_rows_and_a_rerun_leaves_the_same_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_citations(scratch_session)

    apply_report_links(is_commit=True, unplaced_path=None)
    stored_after_first = _get_stored_keys(scratch_session)
    apply_report_links(is_commit=True, unplaced_path=None)

    assert log_recorder.messages[-1] == "Committed"
    assert stored_after_first == _PLANNED_KEYS
    assert _get_stored_keys(scratch_session) == _PLANNED_KEYS


def test_commit_refuses_the_protected_port_before_any_write(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_citations(scratch_session)
    monkeypatch.setattr(
        apply_report_links_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_report_links(is_commit=True, unplaced_path=None)

    assert _get_stored_keys(scratch_session) == []


def test_unplaced_file_holds_each_citation_with_its_report_text_and_reason(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_citations(scratch_session)
    unplaced_path = tmp_path / "unplaced.json"

    apply_report_links(is_commit=False, unplaced_path=unplaced_path)

    unplaced_records = json.loads(unplaced_path.read_text())
    assert len(unplaced_records) == 1
    assert unplaced_records[0]["source_report_id"] == _SOURCE_REPORT_ID
    assert unplaced_records[0]["paragraph"] == _UNPLACED_TRANSCRIPT
    assert unplaced_records[0]["reason"] == ReportLinkUnplacedReason.NO_SITTING_ON_PRINTED_DATE
    assert _get_stored_keys(scratch_session) == []

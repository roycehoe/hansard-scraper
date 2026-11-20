import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.apply_printed_places as apply_printed_places_script
from database.report import Report
from database.sitting import Sitting
from enums import PrintedPlaceRule
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.printed_place_plan import PrintedPlacePlan
from scripts.apply_printed_places import apply_printed_places
from services.printed_place import PlaceableReport, PrintedPlace

_SITTING_DATE = datetime(2012, 9, 11)
_SECOND_SECTION_TEXT = "<p>Second answer</p>"
_SECTIONS = json.dumps(
    [
        {"title": "First Title", "subTitle": None, "content": "<p>First answer</p>"},
        {"title": "Second Title", "subTitle": None, "content": _SECOND_SECTION_TEXT},
        {"title": "Third Title", "subTitle": None, "content": "<p>Third answer</p>"},
    ]
)
_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _seed_sitting(session: Session) -> None:
    session.add(Sitting(sitting_date="11-9-2012", sections=_SECTIONS))
    session.commit()


def _seed_report(
    session: Session,
    report_id: str,
    speech_number: int,
    original_title: str = "Sample Question",
    content: Optional[str] = None,
    report_type: str = "oral-answer",
) -> None:
    session.add(
        Report(
            volumeNo=1,
            parlNo=12,
            sittingNo=None,
            sittingDate=_SITTING_DATE,
            sno=speech_number,
            original_title=original_title,
            title=original_title,
            reportId=report_id,
            reportType=report_type,
            content=content,
            htmlFileName=None,
            reportVersion="sprs3",
        )
    )
    session.commit()


def _seed_three_reports(session: Session) -> None:
    _seed_sitting(session)
    _seed_report(session, "report-a", 2, content=_SECOND_SECTION_TEXT)
    _seed_report(session, "report-b", 1, "First Title", "<p>Other text</p>")
    _seed_report(session, "report-c", 3, report_type="atbp")


def _get_report_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (
            report.report_id,
            report.speech_number,
            report.printed_place,
            report.printed_place_rule,
        )
        for report in session.exec(select(Report).order_by(Report.id)).all()
    ]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_printed_places_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_printed_places_script, "logger", recorder)
    return recorder


def test_dry_run_writes_the_plan_file_and_no_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_three_reports(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_printed_places([], plan_path, is_commit=False)

    plan = PrintedPlacePlan.model_validate_json(plan_path.read_text())
    assert sorted(planned.sprs_report_id for planned in plan.printed_places) == [
        "report-a",
        "report-b",
        "report-c",
    ]
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert [row[2:] for row in _get_report_rows(scratch_session)] == [
        (None, None),
        (None, None),
        (None, None),
    ]


def test_commit_writes_the_reviewed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_three_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_printed_places([], plan_path, is_commit=False)

    apply_printed_places([], plan_path, is_commit=True)

    assert _get_report_rows(scratch_session) == [
        ("report-a", 2, 2, PrintedPlaceRule.SECTION_TEXT),
        ("report-b", 1, 1, PrintedPlaceRule.SECTION_TITLE),
        ("report-c", 3, 0, PrintedPlaceRule.ASSENT_FIRST),
    ]
    assert log_recorder.messages[-1] == "Committed"


def test_commit_refuses_a_changed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_three_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_printed_places([], plan_path, is_commit=False)
    report = scratch_session.exec(
        select(Report).where(Report.report_id == "report-a")
    ).one()
    report.content = "<p>Changed after the dry run</p>"
    scratch_session.add(report)
    scratch_session.commit()

    with pytest.raises(
        HansardWriteCheckError, match="The plan differs from the reviewed plan"
    ):
        apply_printed_places([], plan_path, is_commit=True)

    assert [row[2:] for row in _get_report_rows(scratch_session)] == [
        (None, None),
        (None, None),
        (None, None),
    ]


def test_commit_refuses_two_reports_sharing_a_place_and_keeps_the_rows(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_three_reports(scratch_session)
    plan_path = tmp_path / "plan.json"

    def get_printed_places_with_a_shared_place(
        sitting_copy: object, placeable_reports: list[PlaceableReport]
    ) -> dict[str, PrintedPlace]:
        return {
            placeable_report.report_id: (
                PrintedPlace(0, PrintedPlaceRule.ASSENT_FIRST)
                if placeable_report.report_type == "atbp"
                else PrintedPlace(1, PrintedPlaceRule.SECTION_TEXT)
            )
            for placeable_report in placeable_reports
        }

    monkeypatch.setattr(
        "populate.printed_places.get_printed_places",
        get_printed_places_with_a_shared_place,
    )
    apply_printed_places([], plan_path, is_commit=False)

    with pytest.raises(HansardWriteCheckError, match="share the place 1"):
        apply_printed_places([], plan_path, is_commit=True)

    assert [row[2:] for row in _get_report_rows(scratch_session)] == [
        (None, None),
        (None, None),
        (None, None),
    ]


def test_two_assent_reports_of_one_sitting_pass_the_guard(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_sitting(scratch_session)
    _seed_report(scratch_session, "assent-a", 1, report_type="atbp")
    _seed_report(scratch_session, "assent-b", 2, report_type="atbp")
    plan_path = tmp_path / "plan.json"

    apply_printed_places([], plan_path, is_commit=False)
    apply_printed_places([], plan_path, is_commit=True)

    assert _get_report_rows(scratch_session) == [
        ("assent-a", 1, 0, PrintedPlaceRule.ASSENT_FIRST),
        ("assent-b", 2, 0, PrintedPlaceRule.ASSENT_FIRST),
    ]


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_three_reports(scratch_session)
    monkeypatch.setattr(
        apply_printed_places_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_printed_places([], tmp_path / "plan.json", is_commit=True)

    assert [row[2:] for row in _get_report_rows(scratch_session)] == [
        (None, None),
        (None, None),
        (None, None),
    ]

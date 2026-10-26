import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.apply_fresh_parse as apply_fresh_parse_script
from database.report import Report
from database.speech import Speech
from enums import ReportVersion, SpeechKind
from exceptions import HansardWriteCheckError
from utils.markdown_parser import get_cleaned_report_markdown

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "unsigned_addenda_has_no_speaker.json"
_SITTING_DATE = datetime(1965, 12, 8)
_STORED_SPEAKER = "The President"


def _add_report(scratch_session: Session, fixture: dict) -> Report:
    report = Report(
        volumeNo=24,
        parlNo=1,
        sittingNo=1,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title=fixture["original_title"],
        title=fixture["title"],
        reportId="fixture",
        reportType=fixture["report_type"],
        content=fixture["html"],
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS2,
        markdown_content=get_cleaned_report_markdown(fixture["html"], ReportVersion.SPRS2),
    )
    scratch_session.add(report)
    scratch_session.flush()
    return report


def _seed_report(scratch_session: Session) -> tuple[Report, dict]:
    fixture = json.loads(_FIXTURE_PATH.read_text())
    report = _add_report(scratch_session, fixture)
    merged_transcript = " ".join(transcript for _speaker, transcript, _kind in fixture["expected_rows"])
    scratch_session.add(Speech(ordinal=1, speaker=_STORED_SPEAKER, transcript=merged_transcript, kind=SpeechKind.SPEECH, sitting_date=_SITTING_DATE, report_id=report.id))
    scratch_session.commit()
    return report, fixture


def _get_stored_rows(scratch_session: Session, report: Report) -> list[list]:
    scratch_session.expire_all()
    speeches = scratch_session.exec(select(Speech).where(Speech.report_id == report.id).order_by(Speech.ordinal)).all()
    return [[speech.ordinal, speech.speaker, speech.transcript, speech.kind] for speech in speeches]


def _write_held(tmp_path: Path, report_ids: list[int]) -> Path:
    held_path = tmp_path / "held.json"
    held_path.write_text(json.dumps([{"report_id": report_id, "reason": "test"} for report_id in report_ids]))
    return held_path


def test_dry_run_writes_the_plan_and_changes_no_row(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(apply_fresh_parse_script, "engine", scratch_engine)
    report, fixture = _seed_report(scratch_session)
    stored_rows = _get_stored_rows(scratch_session, report)
    plan_path = tmp_path / "plan.json"

    apply_fresh_parse_script.apply_fresh_parse(plan_path, _write_held(tmp_path, []), is_commit=False)

    plan = json.loads(plan_path.read_text())
    assert [report_plan["report_id"] for report_plan in plan["report_plans"]] == [report.id]
    assert len(plan["report_plans"][0]["updates"]) == 1
    assert len(plan["report_plans"][0]["inserts"]) == len(fixture["expected_rows"]) - 1
    assert _get_stored_rows(scratch_session, report) == stored_rows


def test_commit_writes_the_parse_and_a_second_dry_run_plans_nothing(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_fresh_parse_script, "engine", scratch_engine)
    report, fixture = _seed_report(scratch_session)
    plan_path = tmp_path / "plan.json"
    held_path = _write_held(tmp_path, [])
    apply_fresh_parse_script.apply_fresh_parse(plan_path, held_path, is_commit=False)

    apply_fresh_parse_script.apply_fresh_parse(plan_path, held_path, is_commit=True)

    expected_rows = [[ordinal, speaker, transcript, SpeechKind(kind)] for ordinal, (speaker, transcript, kind) in enumerate(fixture["expected_rows"], start=1)]
    assert _get_stored_rows(scratch_session, report) == expected_rows
    second_plan_path = tmp_path / "second_plan.json"
    apply_fresh_parse_script.apply_fresh_parse(second_plan_path, held_path, is_commit=False)
    assert json.loads(second_plan_path.read_text())["report_plans"] == []


def test_commit_refuses_after_a_stored_row_changes(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(apply_fresh_parse_script, "engine", scratch_engine)
    report, _ = _seed_report(scratch_session)
    plan_path = tmp_path / "plan.json"
    held_path = _write_held(tmp_path, [])
    apply_fresh_parse_script.apply_fresh_parse(plan_path, held_path, is_commit=False)
    scratch_session.exec(select(Speech).where(Speech.report_id == report.id)).one().speaker = "Mr Speaker"
    scratch_session.commit()
    stored_rows = _get_stored_rows(scratch_session, report)

    with pytest.raises(HansardWriteCheckError, match="differs from the reviewed plan"):
        apply_fresh_parse_script.apply_fresh_parse(plan_path, held_path, is_commit=True)

    assert _get_stored_rows(scratch_session, report) == stored_rows


def test_dry_run_leaves_a_held_report(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(apply_fresh_parse_script, "engine", scratch_engine)
    report, _ = _seed_report(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_fresh_parse_script.apply_fresh_parse(plan_path, _write_held(tmp_path, [report.id]), is_commit=False)

    plan = json.loads(plan_path.read_text())
    assert plan["report_plans"] == []
    assert plan["held_report_ids"] == [report.id]


def test_commit_keeps_the_stored_kind_of_a_paired_row_whose_speaker_and_text_are_unchanged(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_fresh_parse_script, "engine", scratch_engine)
    fixture = json.loads(_FIXTURE_PATH.read_text())
    report = _add_report(scratch_session, fixture)
    stored_kinds = [None] + [SpeechKind.UNCLASSIFIED] * (len(fixture["expected_rows"]) - 1)
    scratch_session.add(Speech(ordinal=1, speaker=_STORED_SPEAKER, transcript="A row the parse does not build", kind=SpeechKind.SPEECH, sitting_date=_SITTING_DATE, report_id=report.id))
    for ordinal, ((speaker, transcript, _kind), stored_kind) in enumerate(zip(fixture["expected_rows"], stored_kinds, strict=True), start=2):
        scratch_session.add(Speech(ordinal=ordinal, speaker=speaker, transcript=transcript, kind=stored_kind, sitting_date=_SITTING_DATE, report_id=report.id))
    scratch_session.commit()
    plan_path = tmp_path / "plan.json"
    held_path = _write_held(tmp_path, [])
    apply_fresh_parse_script.apply_fresh_parse(plan_path, held_path, is_commit=False)

    apply_fresh_parse_script.apply_fresh_parse(plan_path, held_path, is_commit=True)

    expected_rows = [
        [ordinal, speaker, transcript, stored_kind]
        for ordinal, ((speaker, transcript, _kind), stored_kind) in enumerate(zip(fixture["expected_rows"], stored_kinds, strict=True), start=1)
    ]
    assert _get_stored_rows(scratch_session, report) == expected_rows
    second_plan_path = tmp_path / "second_plan.json"
    apply_fresh_parse_script.apply_fresh_parse(second_plan_path, held_path, is_commit=False)
    second_plan = json.loads(second_plan_path.read_text())
    assert second_plan["report_plans"] == []
    assert second_plan["kind_only_report_ids"] == [report.id]

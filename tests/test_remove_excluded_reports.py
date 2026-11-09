import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

import scripts.remove_excluded_reports as remove_excluded_reports_script
from database.report import Report
from database.report_asker import ReportAsker
from database.report_link import ReportLink
from database.report_participant import ReportParticipant
from database.report_put_to import ReportPutTo
from database.report_question_state import ReportQuestionState
from database.speech import Speech
from enums import (
    ParticipantRole,
    ParticipantRoleSource,
    QuestionState,
    ReportAskerSource,
    ReportLinkRule,
    ReportLinkType,
    ReportPutToSource,
)
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.excluded_report_id import ExcludedReportId

_SITTING_DATE = datetime(2007, 10, 22)
_KEPT_REPORT_ID = "kept-report"
_EXCLUDED_REPORT_ID = "excluded-report"
_SECOND_EXCLUDED_REPORT_ID = "second-excluded-report"
_OTHER_REPORT_ID = "other-report"
_THIRD_REPORT_ID = "third-report"
_TEXT = "Same text."
_SEEDED_SPEECH_COUNT = 2


def _add_report(session: Session, report_id: str, content: str) -> Report:
    report = Report(
        volume_number=83,
        parliament_number=11,
        sitting_date=_SITTING_DATE,
        speech_number=1,
        original_title="Bill",
        title="Bill",
        report_id=report_id,
        report_type="bill",
        content=content,
        report_version="sprs2",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _add_speech(session: Session, report: Report) -> None:
    assert report.id is not None
    session.add(
        Speech(
            ordinal=1,
            speaker="Mr A",
            transcript="Hello.",
            sitting_date=_SITTING_DATE,
            report_type=report.report_type,
            report_id=report.id,
        )
    )
    session.commit()


def _add_askers(session: Session, report_id: str, asker_count: int) -> None:
    report = session.exec(
        select(Report).where(col(Report.report_id) == report_id)
    ).one()
    assert report.id is not None
    session.add_all(
        ReportAsker(
            ordinal=ordinal,
            printed_name=f"Mr {ordinal}",
            source=ReportAskerSource.ASKED_LINE,
            report_id=report.id,
        )
        for ordinal in range(1, asker_count + 1)
    )
    session.commit()


def _add_put_tos(session: Session, report_id: str, put_to_count: int) -> None:
    session.add_all(
        ReportPutTo(
            ordinal=ordinal,
            office_printed=f"Minister {ordinal}",
            printed_text=f"asked the Minister {ordinal}",
            source=ReportPutToSource.ASKED_THE,
            first_ordinal=ordinal,
            sprs_report_id=report_id,
        )
        for ordinal in range(1, put_to_count + 1)
    )
    session.commit()


def _add_participants_and_question_states(
    session: Session, report_id: str, participant_count: int
) -> None:
    report = session.exec(
        select(Report).where(col(Report.report_id) == report_id)
    ).one()
    assert report.id is not None
    session.add_all(
        ReportParticipant(
            ordinal=ordinal,
            role=ParticipantRole.ASKER,
            role_source=ParticipantRoleSource.ASKER_RULES,
            first_ordinal=ordinal,
            printed_name=f"Mr {ordinal}",
            report_id=report.id,
        )
        for ordinal in range(1, participant_count + 1)
    )
    session.add(
        ReportQuestionState(
            state=QuestionState.URGENT,
            printed_text="Urgent.",
            report_id=report.id,
        )
    )
    session.commit()


def _add_report_link(
    session: Session, source_report_id: str, target_report_id: str
) -> None:
    session.add(
        ReportLink(
            link_type=ReportLinkType.REPLY,
            rule=ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE,
            printed_citation="Official Report, 1 January 2000",
            source_report_id=source_report_id,
            target_report_id=target_report_id,
        )
    )
    session.commit()


def _get_link_pairs(session: Session) -> list[tuple[str, str]]:
    session.expire_all()
    return sorted(
        session.exec(
            select(ReportLink.source_report_id, ReportLink.target_report_id)
        ).all()
    )


def _seed_duplicate(session: Session, excluded_content: str = _TEXT) -> None:
    for report_id, content in (
        (_KEPT_REPORT_ID, _TEXT),
        (_EXCLUDED_REPORT_ID, excluded_content),
    ):
        _add_speech(session, _add_report(session, report_id, content))


def _use_scratch(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(remove_excluded_reports_script, "engine", scratch_engine)
    excluded_report_ids = [
        ExcludedReportId(
            report_id=_EXCLUDED_REPORT_ID,
            kept_report_id=_KEPT_REPORT_ID,
            reason="duplicate",
        )
    ]
    monkeypatch.setattr(
        remove_excluded_reports_script,
        "get_excluded_report_ids",
        lambda: excluded_report_ids,
    )


def _get_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(session.exec(select(Report.report_id)).all())


def _get_speech_count(session: Session) -> int:
    session.expire_all()
    return len(session.exec(select(Speech.id)).all())


def _get_put_to_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(session.exec(select(ReportPutTo.sprs_report_id)).all())


def _get_asker_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(
        session.exec(
            select(Report.report_id).join(
                ReportAsker, col(ReportAsker.report_id) == col(Report.id)
            )
        ).all()
    )


def _get_participant_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(
        session.exec(
            select(Report.report_id).join(
                ReportParticipant, col(ReportParticipant.report_id) == col(Report.id)
            )
        ).all()
    )


def _get_question_state_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(
        session.exec(
            select(Report.report_id).join(
                ReportQuestionState,
                col(ReportQuestionState.report_id) == col(Report.id),
            )
        ).all()
    )


def test_dry_run_writes_the_plan_and_no_rows(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    plan_path = tmp_path / "plan.json"

    remove_excluded_reports_script.remove_excluded_reports(False, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [
        (removal["report_id"], removal["kept_report_id"], removal["speech_count"])
        for removal in plan
    ] == [(_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID, 1)]
    assert _get_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == _SEEDED_SPEECH_COUNT


def test_commit_refuses_when_the_duplicate_text_differs(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session, excluded_content="Different text.")

    with pytest.raises(HansardWriteCheckError, match="text differs"):
        remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == _SEEDED_SPEECH_COUNT


def test_commit_deletes_exactly_the_planned_report_and_speeches(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == 1
    remove_excluded_reports_script.remove_excluded_reports(True, None)
    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == 1


def test_commit_deletes_the_removed_reports_askers_and_keeps_the_others(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_askers(scratch_session, _EXCLUDED_REPORT_ID, 2)
    _add_askers(scratch_session, _KEPT_REPORT_ID, 1)
    assert _get_asker_report_ids(scratch_session) == [
        _EXCLUDED_REPORT_ID,
        _EXCLUDED_REPORT_ID,
        _KEPT_REPORT_ID,
    ]

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_asker_report_ids(scratch_session) == [_KEPT_REPORT_ID]


def test_dry_run_plan_holds_the_link_count(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_report(scratch_session, _OTHER_REPORT_ID, _TEXT)
    _add_report_link(scratch_session, _EXCLUDED_REPORT_ID, _OTHER_REPORT_ID)
    _add_report_link(scratch_session, _OTHER_REPORT_ID, _EXCLUDED_REPORT_ID)
    plan_path = tmp_path / "plan.json"

    remove_excluded_reports_script.remove_excluded_reports(False, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [removal["link_count"] for removal in plan] == [2]
    assert _get_link_pairs(scratch_session) == [
        (_EXCLUDED_REPORT_ID, _OTHER_REPORT_ID),
        (_OTHER_REPORT_ID, _EXCLUDED_REPORT_ID),
    ]


def test_commit_deletes_links_of_a_removed_source_and_target_and_keeps_the_others(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_report(scratch_session, _OTHER_REPORT_ID, _TEXT)
    _add_report(scratch_session, _THIRD_REPORT_ID, _TEXT)
    _add_report_link(scratch_session, _EXCLUDED_REPORT_ID, _OTHER_REPORT_ID)
    _add_report_link(scratch_session, _OTHER_REPORT_ID, _EXCLUDED_REPORT_ID)
    _add_report_link(scratch_session, _OTHER_REPORT_ID, _THIRD_REPORT_ID)

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [
        _KEPT_REPORT_ID,
        _OTHER_REPORT_ID,
        _THIRD_REPORT_ID,
    ]
    assert _get_link_pairs(scratch_session) == [(_OTHER_REPORT_ID, _THIRD_REPORT_ID)]


def test_commit_counts_a_link_between_two_removed_reports_once(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_speech(
        scratch_session, _add_report(scratch_session, _SECOND_EXCLUDED_REPORT_ID, _TEXT)
    )
    excluded_report_ids = [
        ExcludedReportId(
            report_id=report_id,
            kept_report_id=_KEPT_REPORT_ID,
            reason="duplicate",
        )
        for report_id in (_EXCLUDED_REPORT_ID, _SECOND_EXCLUDED_REPORT_ID)
    ]
    monkeypatch.setattr(
        remove_excluded_reports_script,
        "get_excluded_report_ids",
        lambda: excluded_report_ids,
    )
    _add_report_link(scratch_session, _EXCLUDED_REPORT_ID, _SECOND_EXCLUDED_REPORT_ID)

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_link_pairs(scratch_session) == []


def test_commit_deletes_the_removed_reports_participants_and_question_states_and_keeps_the_others(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_participants_and_question_states(scratch_session, _EXCLUDED_REPORT_ID, 2)
    _add_participants_and_question_states(scratch_session, _KEPT_REPORT_ID, 1)
    assert _get_participant_report_ids(scratch_session) == [
        _EXCLUDED_REPORT_ID,
        _EXCLUDED_REPORT_ID,
        _KEPT_REPORT_ID,
    ]
    assert _get_question_state_report_ids(scratch_session) == [
        _EXCLUDED_REPORT_ID,
        _KEPT_REPORT_ID,
    ]

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_participant_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_question_state_report_ids(scratch_session) == [_KEPT_REPORT_ID]


def test_commit_refuses_the_protected_local_port(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    monkeypatch.setattr(
        remove_excluded_reports_script,
        "settings",
        SimpleNamespace(database_url="postgresql://u:p@localhost:5432/x"),
    )
    _seed_duplicate(scratch_session)

    with pytest.raises(HansardWriteTargetError):
        remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID]


def test_commit_deletes_the_removed_reports_put_tos_and_keeps_the_others(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_put_tos(scratch_session, _EXCLUDED_REPORT_ID, 2)
    _add_put_tos(scratch_session, _KEPT_REPORT_ID, 1)

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_put_to_report_ids(scratch_session) == [_KEPT_REPORT_ID]

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, func, select

import scripts.remove_excluded_reports as remove_excluded_reports_script
from crud.division import CRUDDivision
from database.attached_file_pointer import AttachedFilePointer
from database.bill_report_speaker import BillReportSpeaker
from database.bill_stage_line import BillStageLine
from database.division import Division
from database.division_party_count import DivisionPartyCount
from database.division_vote import DivisionVote
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from database.report import Report
from database.report_asker import ReportAsker
from database.report_link import ReportLink
from database.report_participant import ReportParticipant
from database.report_put_to import ReportPutTo
from database.report_question_state import ReportQuestionState
from database.speaker import Speaker
from database.speech import Speech
from enums import (
    AttachedFilePointerShape,
    BillStage,
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    MinutesDivisionPairing,
    MinutesStatus,
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
_EXCLUDED_STAGE_LINE_COUNT = 2
_DIVISION_PARLIAMENT_NUMBER = 11
_DIVISION_AYES = 5
_DIVISION_NOES = 2
_DIVISION_PRINTED_COUNTS = "The House divided: Ayes, 5; Noes, 2"
_PAIRED_VOTE_ROW_COUNT = 2


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


def _add_division(session: Session, report_id: str) -> None:
    session.add(
        Division(
            sitting_date=_SITTING_DATE.date(),
            parliament_number=_DIVISION_PARLIAMENT_NUMBER,
            report_division_number=1,
            speech_ordinal=1,
            count_source=DivisionCountSource.PRINTED_LINE,
            printed_counts=_DIVISION_PRINTED_COUNTS,
            ayes=_DIVISION_AYES,
            noes=_DIVISION_NOES,
            list_status=DivisionListStatus.NOT_PRINTED,
            sprs_report_id=report_id,
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


def _add_pointers(session: Session, report_id: str, pointer_count: int) -> None:
    session.add_all(
        AttachedFilePointer(
            ordinal=ordinal,
            printed_text="Annex",
            href=f"/search/search/download?value=PDFs/Annex {ordinal}.pdf",
            shape=AttachedFilePointerShape.PDFS,
            download_value=f"PDFs/Annex {ordinal}.pdf",
            sprs_report_id=report_id,
        )
        for ordinal in range(1, pointer_count + 1)
    )
    session.commit()


def _add_paired_minutes_division(session: Session, report_id: str) -> None:
    division = session.exec(
        select(Division).where(col(Division.sprs_report_id) == report_id)
    ).one()
    assert division.id is not None
    minutes = Minutes(sitting_date=_SITTING_DATE.date(), status=MinutesStatus.TEXT_STORED)
    session.add(minutes)
    session.flush()
    assert minutes.id is not None
    session.add(
        MinutesDivision(
            ordinal=1,
            printed_counts=_DIVISION_PRINTED_COUNTS,
            ayes=_DIVISION_AYES,
            noes=_DIVISION_NOES,
            list_status=DivisionListStatus.NOT_PRINTED,
            pairing=MinutesDivisionPairing.PAIRED,
            minutes_id=minutes.id,
            division_id=division.id,
        )
    )
    session.add_all(
        DivisionVote(
            ordinal=1,
            printed_name="Mr A",
            vote_choice=DivisionVoteChoice.AYE,
            list_source=list_source,
            division_id=division.id,
        )
        for list_source in DivisionVoteListSource
    )
    session.commit()


def _get_pointer_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(session.exec(select(AttachedFilePointer.sprs_report_id)).all())


def _get_row_count(session: Session, table: type) -> int:
    session.expire_all()
    return session.exec(select(func.count()).select_from(table)).one()


def _get_division_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(
        report_id
        for report_id in session.exec(select(Division.sprs_report_id)).all()
        if report_id is not None
    )


def _seed_duplicate(session: Session, excluded_content: str = _TEXT) -> None:
    for report_id, content in (
        (_KEPT_REPORT_ID, _TEXT),
        (_EXCLUDED_REPORT_ID, excluded_content),
    ):
        _add_speech(session, _add_report(session, report_id, content))


def _add_bill_speaker_rows(session: Session, report_id: str, row_count: int) -> None:
    speaker = Speaker(
        name=f"Speaker of {report_id}",
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=11,
    )
    session.add(speaker)
    session.flush()
    assert speaker.id is not None
    session.add(
        BillReportSpeaker(
            speech_count=1,
            first_ordinal=1,
            printed_speaker="Mr A",
            sprs_report_id=report_id,
            speaker_id=speaker.id,
        )
    )
    session.add_all(
        BillStageLine(
            stage=BillStage.FIRST_READING,
            printed_text="Bill read a First time.",
            ordinal=ordinal,
            sprs_report_id=report_id,
        )
        for ordinal in range(1, row_count + 1)
    )
    session.commit()


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


def _get_bill_report_speaker_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(session.exec(select(BillReportSpeaker.sprs_report_id)).all())


def _get_bill_stage_line_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(session.exec(select(BillStageLine.sprs_report_id)).all())


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


def test_division_count_is_in_the_plan_file(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_division(scratch_session, _EXCLUDED_REPORT_ID)
    plan_path = tmp_path / "plan.json"

    remove_excluded_reports_script.remove_excluded_reports(False, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [removal["division_count"] for removal in plan] == [1]


def test_commit_refuses_when_the_duplicate_text_differs(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session, excluded_content="Different text.")

    with pytest.raises(HansardWriteCheckError, match="text differs"):
        remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == _SEEDED_SPEECH_COUNT


def test_commit_refuses_when_the_duplicate_speech_rows_differ(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_division(scratch_session, _EXCLUDED_REPORT_ID)
    speech = scratch_session.exec(
        select(Speech)
        .join(Report, col(Report.id) == col(Speech.report_id))
        .where(Report.report_id == _EXCLUDED_REPORT_ID)
    ).one()
    speech.transcript = "Different speech."
    scratch_session.commit()

    with pytest.raises(HansardWriteCheckError, match="speech rows differ"):
        remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == _SEEDED_SPEECH_COUNT
    assert _get_division_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID]


def test_commit_deletes_exactly_the_planned_report_and_speeches(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_division(scratch_session, _EXCLUDED_REPORT_ID)
    _add_division(scratch_session, _KEPT_REPORT_ID)

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_division_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == 1
    remove_excluded_reports_script.remove_excluded_reports(True, None)
    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == 1


def test_commit_refuses_when_fewer_division_rows_are_deleted_than_planned(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_division(scratch_session, _EXCLUDED_REPORT_ID)
    delete_by_ids = CRUDDivision.delete_by_ids
    monkeypatch.setattr(
        CRUDDivision,
        "delete_by_ids",
        lambda crud_division, division_ids: delete_by_ids(crud_division, division_ids)
        - 1,
    )

    with pytest.raises(HansardWriteCheckError, match="division rows"):
        remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID]
    assert _get_division_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID]


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


def test_commit_deletes_the_removed_reports_bill_report_speakers_and_stage_lines_and_keeps_the_others(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_bill_speaker_rows(scratch_session, _EXCLUDED_REPORT_ID, 2)
    _add_bill_speaker_rows(scratch_session, _KEPT_REPORT_ID, 1)
    assert _get_bill_report_speaker_report_ids(scratch_session) == [
        _EXCLUDED_REPORT_ID,
        _KEPT_REPORT_ID,
    ]
    assert _get_bill_stage_line_report_ids(scratch_session) == [
        _EXCLUDED_REPORT_ID,
        _EXCLUDED_REPORT_ID,
        _KEPT_REPORT_ID,
    ]

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_bill_report_speaker_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_bill_stage_line_report_ids(scratch_session) == [_KEPT_REPORT_ID]


def test_dry_run_plan_counts_the_bill_report_speaker_and_stage_line_rows(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_bill_speaker_rows(
        scratch_session, _EXCLUDED_REPORT_ID, _EXCLUDED_STAGE_LINE_COUNT
    )
    plan_path = tmp_path / "plan.json"

    remove_excluded_reports_script.remove_excluded_reports(False, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [
        (removal["bill_report_speaker_count"], removal["bill_stage_line_count"])
        for removal in plan
    ] == [(1, _EXCLUDED_STAGE_LINE_COUNT)]
    assert _get_bill_report_speaker_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID]
    assert _get_bill_stage_line_report_ids(scratch_session) == [
        _EXCLUDED_REPORT_ID,
        _EXCLUDED_REPORT_ID,
    ]


def test_commit_deletes_the_removed_reports_pointers_and_keeps_the_others(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_pointers(scratch_session, _EXCLUDED_REPORT_ID, 2)
    _add_pointers(scratch_session, _KEPT_REPORT_ID, 1)
    assert _get_pointer_report_ids(scratch_session) == [
        _EXCLUDED_REPORT_ID,
        _EXCLUDED_REPORT_ID,
        _KEPT_REPORT_ID,
    ]

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_pointer_report_ids(scratch_session) == [_KEPT_REPORT_ID]


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
    monkeypatch.setattr(remove_excluded_reports_script, "engine", None)

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


def test_the_plan_counts_the_minutes_division_and_vote_rows(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_division(scratch_session, _EXCLUDED_REPORT_ID)
    _add_paired_minutes_division(scratch_session, _EXCLUDED_REPORT_ID)
    plan_path = tmp_path / "plan.json"

    remove_excluded_reports_script.remove_excluded_reports(False, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [removal["minutes_division_count"] for removal in plan] == [1]
    assert [removal["division_vote_count"] for removal in plan] == [
        _PAIRED_VOTE_ROW_COUNT
    ]
    assert _get_row_count(scratch_session, MinutesDivision) == 1


def test_removing_a_report_deletes_its_minutes_division_and_vote_rows(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_division(scratch_session, _EXCLUDED_REPORT_ID)
    _add_division(scratch_session, _KEPT_REPORT_ID)
    _add_paired_minutes_division(scratch_session, _EXCLUDED_REPORT_ID)

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_division_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_row_count(scratch_session, MinutesDivision) == 0
    assert _get_row_count(scratch_session, DivisionVote) == 0
    assert _get_row_count(scratch_session, Minutes) == 1


def test_removing_a_report_deletes_its_party_count_rows(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    _add_division(scratch_session, _EXCLUDED_REPORT_ID)
    _add_division(scratch_session, _KEPT_REPORT_ID)
    for division in scratch_session.exec(select(Division)).all():
        assert division.id is not None
        scratch_session.add(
            DivisionPartyCount(
                member_count=_DIVISION_AYES,
                uncertain_member_count=0,
                party="PAP",
                list_source=DivisionVoteListSource.HANSARD,
                vote_choice=DivisionVoteChoice.AYE,
                division_id=division.id,
            )
        )
    scratch_session.commit()

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_division_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_row_count(scratch_session, DivisionPartyCount) == 1

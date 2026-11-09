from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

import scripts.apply_bill_speakers as apply_bill_speakers_script
from crud.bill_key import CRUDBillKey
from crud.bill_report_speaker import CRUDBillReportSpeaker
from crud.bill_stage_line import CRUDBillStageLine
from database.bill_key import BillKey
from database.bill_report_speaker import BillReportSpeaker
from database.bill_stage_line import BillStageLine
from enums import BillStage, ReportType
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from scripts.apply_bill_speakers import apply_bill_speakers
from tests.bill_seed import (
    BILL_SPEECHES_FIRST_SPRS_REPORT_ID,
    BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
    SPEAKER_A_LABEL,
    SPEAKER_B_LABEL,
    SeededBillSpeeches,
    seed_bill_report,
    seed_bill_speeches,
)

_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_LOOSE_SPRS_REPORT_ID = "loose-report"
_MADE_UP_ORDINAL = 99
_HAND_EDITED_NAME = "Hand edited"


class _LogRecorder:
    def __init__(self):
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_bill_speakers_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_bill_speakers_script, "logger", recorder)
    return recorder


def _get_key_values(session: Session) -> list[tuple[str, int, int]]:
    session.expire_all()
    return [
        (bill_key_row.bill_key, bill_key_row.act_count, bill_key_row.bill_id)
        for bill_key_row in CRUDBillKey(session).get_rows()
    ]


def _get_member_values(session: Session) -> list[tuple[str, int, int, int, str]]:
    session.expire_all()
    return [
        (
            bill_report_speaker_row.sprs_report_id,
            bill_report_speaker_row.speaker_id,
            bill_report_speaker_row.speech_count,
            bill_report_speaker_row.first_ordinal,
            bill_report_speaker_row.printed_speaker,
        )
        for bill_report_speaker_row in CRUDBillReportSpeaker(session).get_rows()
    ]


def _get_stage_line_values(session: Session) -> list[tuple[str, int, BillStage]]:
    session.expire_all()
    return [
        (
            bill_stage_line_row.sprs_report_id,
            bill_stage_line_row.ordinal,
            bill_stage_line_row.stage,
        )
        for bill_stage_line_row in CRUDBillStageLine(session).get_rows()
    ]


def _get_planned_key_values(seeded: SeededBillSpeeches) -> list[tuple[str, int, int]]:
    return [(BILL_SPEECHES_FIRST_SPRS_REPORT_ID, 0, seeded.bill_id)]


def _get_planned_member_values(
    seeded: SeededBillSpeeches,
) -> list[tuple[str, int, int, int, str]]:
    return [
        (
            BILL_SPEECHES_FIRST_SPRS_REPORT_ID,
            seeded.speaker_a_id,
            2,
            2,
            SPEAKER_A_LABEL,
        ),
        (
            BILL_SPEECHES_FIRST_SPRS_REPORT_ID,
            seeded.speaker_b_id,
            1,
            3,
            SPEAKER_B_LABEL,
        ),
        (
            BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
            seeded.speaker_a_id,
            2,
            2,
            SPEAKER_A_LABEL,
        ),
    ]


def _get_planned_stage_line_values() -> list[tuple[str, int, BillStage]]:
    return [
        (BILL_SPEECHES_FIRST_SPRS_REPORT_ID, 1, BillStage.FIRST_READING),
        (BILL_SPEECHES_THIRD_SPRS_REPORT_ID, 1, BillStage.SECOND_READING_AGREED),
        (BILL_SPEECHES_THIRD_SPRS_REPORT_ID, 3, BillStage.THIRD_READING),
    ]


def test_dry_run_logs_the_plan_and_the_differences_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded = seed_bill_speeches(scratch_session)

    apply_bill_speakers([], is_commit=False)

    assert "2020s bill-intro: 2 bill report speakers" in log_recorder.messages
    assert "2020s bill: 1 bill report speakers" in log_recorder.messages
    assert "FIRST_READING: 1 bill stage lines" in log_recorder.messages
    assert (
        "Plan: 1 bill keys, 3 bill report speakers and 3 bill stage lines for 1 bills"
        in log_recorder.messages
    )
    assert (
        f"Bill keys: 1 to add, 0 to remove, 0 to change; involved: {seeded.bill_id}"
        in log_recorder.messages
    )
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_key_values(scratch_session) == []
    assert _get_member_values(scratch_session) == []
    assert _get_stage_line_values(scratch_session) == []


def test_commit_writes_the_planned_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded = seed_bill_speeches(scratch_session)

    apply_bill_speakers([], is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    assert _get_key_values(scratch_session) == _get_planned_key_values(seeded)
    assert _get_member_values(scratch_session) == _get_planned_member_values(seeded)
    assert _get_stage_line_values(scratch_session) == _get_planned_stage_line_values()


def test_a_dry_run_after_a_commit_logs_no_differences(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seed_bill_speeches(scratch_session)
    apply_bill_speakers([], is_commit=True)
    log_recorder.messages.clear()

    apply_bill_speakers([], is_commit=False)

    for label in ("Bill keys", "Bill report speakers", "Bill stage lines"):
        assert (
            f"{label}: 0 to add, 0 to remove, 0 to change; involved: none"
            in log_recorder.messages
        )


def test_commit_on_a_rerun_leaves_the_same_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded = seed_bill_speeches(scratch_session)
    apply_bill_speakers([], is_commit=True)
    first_member_values = _get_member_values(scratch_session)

    apply_bill_speakers([], is_commit=True)

    assert first_member_values == _get_planned_member_values(seeded)
    assert _get_key_values(scratch_session) == _get_planned_key_values(seeded)
    assert _get_member_values(scratch_session) == first_member_values
    assert _get_stage_line_values(scratch_session) == _get_planned_stage_line_values()


def test_a_dry_run_after_a_regroup_shows_the_rebuild_owed(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded = seed_bill_speeches(scratch_session)
    apply_bill_speakers([], is_commit=True)
    stored_bill_key = scratch_session.exec(select(BillKey)).one()
    scratch_session.delete(stored_bill_key)
    scratch_session.add(
        BillStageLine(
            stage=BillStage.THIRD_READING,
            printed_text="Made up.",
            ordinal=_MADE_UP_ORDINAL,
            sprs_report_id=BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
        )
    )
    scratch_session.commit()
    log_recorder.messages.clear()

    apply_bill_speakers([], is_commit=False)

    assert (
        f"Bill keys: 1 to add, 0 to remove, 0 to change; involved: {seeded.bill_id}"
        in log_recorder.messages
    )
    assert (
        "Bill stage lines: 0 to add, 1 to remove, 0 to change; involved: speeches-third"
        in log_recorder.messages
    )


def test_commit_with_report_ids_leaves_other_reports_rows_alone(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded = seed_bill_speeches(scratch_session)
    apply_bill_speakers([], is_commit=True)
    third_report_speaker = scratch_session.exec(
        select(BillReportSpeaker).where(
            col(BillReportSpeaker.sprs_report_id)
            == BILL_SPEECHES_THIRD_SPRS_REPORT_ID
        )
    ).one()
    third_report_speaker.printed_speaker = _HAND_EDITED_NAME
    scratch_session.add(third_report_speaker)
    scratch_session.commit()
    log_recorder.messages.clear()

    apply_bill_speakers([seeded.first_report_id], is_commit=True)

    assert (
        "Plan: 2 bill report speakers and 1 bill stage lines for 1 reports"
        in log_recorder.messages
    )
    assert _get_member_values(scratch_session) == [
        *_get_planned_member_values(seeded)[:2],
        (
            BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
            seeded.speaker_a_id,
            2,
            2,
            _HAND_EDITED_NAME,
        ),
    ]
    assert _get_key_values(scratch_session) == _get_planned_key_values(seeded)


def test_commit_with_a_report_no_bill_holds_removes_its_stale_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded = seed_bill_speeches(scratch_session)
    loose_report_id = seed_bill_report(
        scratch_session,
        _LOOSE_SPRS_REPORT_ID,
        ReportType.BILL,
        datetime(2025, 3, 1),
        "Water Bill",
        [],
    )
    scratch_session.add(
        BillReportSpeaker(
            speech_count=1,
            first_ordinal=1,
            printed_speaker="Stale",
            sprs_report_id=_LOOSE_SPRS_REPORT_ID,
            speaker_id=seeded.speaker_a_id,
        )
    )
    scratch_session.commit()

    apply_bill_speakers([loose_report_id], is_commit=True)

    assert (
        "Plan: 0 bill report speakers and 0 bill stage lines for 1 reports"
        in log_recorder.messages
    )
    assert _get_member_values(scratch_session) == []


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_bill_speeches(scratch_session)
    monkeypatch.setattr(
        apply_bill_speakers_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_bill_speakers([], is_commit=True)

    assert _get_key_values(scratch_session) == []
    assert _get_member_values(scratch_session) == []
    assert _get_stage_line_values(scratch_session) == []


def test_commit_refuses_a_short_member_delete_count_and_keeps_the_rows(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = seed_bill_speeches(scratch_session)
    apply_bill_speakers([], is_commit=True)
    real_delete_all = CRUDBillReportSpeaker.delete_all

    def delete_all_one_short(self: CRUDBillReportSpeaker) -> int:
        return real_delete_all(self) - 1

    monkeypatch.setattr(CRUDBillReportSpeaker, "delete_all", delete_all_one_short)

    with pytest.raises(
        HansardWriteCheckError, match="Deleted 2 bill report speakers, read 3"
    ):
        apply_bill_speakers([], is_commit=True)

    assert _get_member_values(scratch_session) == _get_planned_member_values(seeded)


def test_commit_refuses_stored_rows_that_differ_from_the_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_bill_speeches(scratch_session)
    real_add_many = CRUDBillStageLine.add_many

    def add_many_one_short(
        self: CRUDBillStageLine, bill_stage_lines: list[BillStageLine]
    ) -> None:
        real_add_many(self, bill_stage_lines[:-1])

    monkeypatch.setattr(CRUDBillStageLine, "add_many", add_many_one_short)

    with pytest.raises(
        HansardWriteCheckError, match="Stored bill stage lines by stage"
    ):
        apply_bill_speakers([], is_commit=True)

    assert _get_key_values(scratch_session) == []
    assert _get_member_values(scratch_session) == []
    assert _get_stage_line_values(scratch_session) == []

from dataclasses import replace
from datetime import datetime

import pytest
from sqlmodel import Session, col, select

from crud.bill_key import CRUDBillKey
from crud.bill_report_speaker import CRUDBillReportSpeaker
from crud.bill_stage_line import CRUDBillStageLine
from database.act import Act, ActHistoryEntry
from database.bill import BillReport
from database.bill_key import BillKey
from database.bill_report_speaker import BillReportSpeaker
from enums import ActHistoryEntryKind, BillReportRole, BillStage, ReportType, SpeechKind
from exceptions import HansardWriteCheckError
from populate.bill_speakers import (
    get_bill_speaker_plan,
    get_report_bill_speaker_plan,
    write_bill_speaker_plan,
    write_report_bill_speaker_plan,
)
from tests.bill_seed import (
    BILL_SPEECHES_FIRST_SPRS_REPORT_ID,
    BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
    SPEAKER_A_LABEL,
    SPEAKER_B_LABEL,
    SeededBillSpeeches,
    seed_bill_report,
    seed_bill_speeches,
    seed_speech,
)

_LOOSE_SPRS_REPORT_ID = "loose-report"
_BUDGET_SPRS_REPORT_ID = "budget-report"


def _get_member_values(
    session: Session,
) -> list[tuple[str, int, int, int, str]]:
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


def _get_stage_line_values(session: Session) -> list[tuple[str, int, BillStage, str]]:
    return [
        (
            bill_stage_line_row.sprs_report_id,
            bill_stage_line_row.ordinal,
            bill_stage_line_row.stage,
            bill_stage_line_row.printed_text,
        )
        for bill_stage_line_row in CRUDBillStageLine(session).get_rows()
    ]


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


def _get_planned_stage_line_values() -> list[tuple[str, int, BillStage, str]]:
    return [
        (
            BILL_SPEECHES_FIRST_SPRS_REPORT_ID,
            1,
            BillStage.FIRST_READING,
            "Bill read a First time.",
        ),
        (
            BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
            1,
            BillStage.SECOND_READING_AGREED,
            "Bill accordingly read a Second time and committed to a Committee of the whole House.",
        ),
        (
            BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
            3,
            BillStage.THIRD_READING,
            "Bill read a Third time and passed.",
        ),
    ]


def _write_corpus_plan(session: Session) -> None:
    write_bill_speaker_plan(session, get_bill_speaker_plan(session))
    session.commit()


def test_the_corpus_plan_holds_one_key_per_bill_at_its_first_reading_report(
    scratch_session: Session,
) -> None:
    seeded = seed_bill_speeches(scratch_session)

    plan = get_bill_speaker_plan(scratch_session)

    assert [
        (bill_key.bill_key, bill_key.act_count, bill_key.bill_id)
        for bill_key in plan.bill_keys
    ] == [(BILL_SPEECHES_FIRST_SPRS_REPORT_ID, 0, seeded.bill_id)]


def test_the_key_ignores_a_budget_debate_report_dated_earlier(
    scratch_session: Session,
) -> None:
    seeded = seed_bill_speeches(scratch_session)
    budget_report_id = seed_bill_report(
        scratch_session,
        _BUDGET_SPRS_REPORT_ID,
        ReportType.BUDGET,
        datetime(2024, 1, 5),
        "Supply Bill",
        [],
    )
    scratch_session.add(
        BillReport(
            role=BillReportRole.BUDGET_DEBATE,
            bill_id=seeded.bill_id,
            report_id=budget_report_id,
        )
    )
    scratch_session.commit()

    plan = get_bill_speaker_plan(scratch_session)

    assert [bill_key.bill_key for bill_key in plan.bill_keys] == [
        BILL_SPEECHES_FIRST_SPRS_REPORT_ID
    ]


def test_the_act_count_is_the_number_of_distinct_acts_linked_to_the_bill(
    scratch_session: Session,
) -> None:
    seeded = seed_bill_speeches(scratch_session)
    first_act = Act(sso_code="A1", title="First Act")
    second_act = Act(sso_code="A2", title="Second Act")
    scratch_session.add_all([first_act, second_act])
    scratch_session.flush()
    assert first_act.id is not None
    assert second_act.id is not None
    for act_id, ordinal, bill_id in (
        (first_act.id, 1, seeded.bill_id),
        (first_act.id, 2, seeded.bill_id),
        (second_act.id, 1, seeded.bill_id),
        (second_act.id, 2, None),
    ):
        scratch_session.add(
            ActHistoryEntry(
                ordinal=ordinal,
                printed_text="entry",
                printed_law_number="1 of 2025",
                printed_title="Food Act",
                kind=ActHistoryEntryKind.ACT,
                act_id=act_id,
                bill_id=bill_id,
            )
        )
    scratch_session.commit()

    plan = get_bill_speaker_plan(scratch_session)

    assert [bill_key.act_count for bill_key in plan.bill_keys] == [2]


def test_the_corpus_plan_holds_one_member_row_per_member_and_report(
    scratch_session: Session,
) -> None:
    seeded = seed_bill_speeches(scratch_session)

    plan = get_bill_speaker_plan(scratch_session)

    assert [
        (
            bill_report_speaker.sprs_report_id,
            bill_report_speaker.speaker_id,
            bill_report_speaker.speech_count,
            bill_report_speaker.first_ordinal,
            bill_report_speaker.printed_speaker,
        )
        for bill_report_speaker in plan.bill_report_speakers
    ] == _get_planned_member_values(seeded)


def test_a_budget_debate_report_in_the_bill_adds_its_own_member_rows(
    scratch_session: Session,
) -> None:
    seeded = seed_bill_speeches(scratch_session)
    budget_report_id = seed_bill_report(
        scratch_session,
        _BUDGET_SPRS_REPORT_ID,
        ReportType.BUDGET,
        datetime(2025, 3, 1),
        "Supply Bill",
        [],
    )
    seed_speech(
        scratch_session,
        budget_report_id,
        1,
        SPEAKER_A_LABEL,
        seeded.speaker_a_id,
        SpeechKind.SPEECH,
        "Head A.",
    )
    scratch_session.add(
        BillReport(
            role=BillReportRole.BUDGET_DEBATE,
            bill_id=seeded.bill_id,
            report_id=budget_report_id,
        )
    )
    scratch_session.commit()

    plan = get_bill_speaker_plan(scratch_session)

    assert (
        _BUDGET_SPRS_REPORT_ID,
        seeded.speaker_a_id,
        1,
        1,
        SPEAKER_A_LABEL,
    ) in [
        (
            bill_report_speaker.sprs_report_id,
            bill_report_speaker.speaker_id,
            bill_report_speaker.speech_count,
            bill_report_speaker.first_ordinal,
            bill_report_speaker.printed_speaker,
        )
        for bill_report_speaker in plan.bill_report_speakers
    ]


def test_the_corpus_plan_holds_stage_lines_only_from_procedural_and_unclassified_rows(
    scratch_session: Session,
) -> None:
    seed_bill_speeches(scratch_session)

    plan = get_bill_speaker_plan(scratch_session)

    assert [
        (
            bill_stage_line.sprs_report_id,
            bill_stage_line.ordinal,
            bill_stage_line.stage,
            bill_stage_line.printed_text,
        )
        for bill_stage_line in plan.bill_stage_lines
    ] == _get_planned_stage_line_values()


def test_the_corpus_write_inserts_the_plan_and_a_second_write_leaves_the_same_rows(
    scratch_session: Session,
) -> None:
    seeded = seed_bill_speeches(scratch_session)

    _write_corpus_plan(scratch_session)

    assert _get_member_values(scratch_session) == _get_planned_member_values(seeded)
    assert _get_stage_line_values(scratch_session) == _get_planned_stage_line_values()
    assert [
        (bill_key_row.bill_key, bill_key_row.act_count, bill_key_row.bill_id)
        for bill_key_row in CRUDBillKey(scratch_session).get_rows()
    ] == [(BILL_SPEECHES_FIRST_SPRS_REPORT_ID, 0, seeded.bill_id)]

    _write_corpus_plan(scratch_session)

    assert _get_member_values(scratch_session) == _get_planned_member_values(seeded)
    assert _get_stage_line_values(scratch_session) == _get_planned_stage_line_values()
    assert len(CRUDBillKey(scratch_session).get_rows()) == len(
        get_bill_speaker_plan(scratch_session).bill_keys
    )


def test_the_corpus_write_refuses_a_key_that_is_not_the_first_reading_report(
    scratch_session: Session,
) -> None:
    seeded = seed_bill_speeches(scratch_session)
    plan = get_bill_speaker_plan(scratch_session)
    wrong_plan = replace(
        plan,
        bill_keys=[
            BillKey(
                act_count=0,
                bill_key=BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
                bill_id=seeded.bill_id,
            )
        ],
    )

    with pytest.raises(
        HansardWriteCheckError, match="its first READING report is speeches-first"
    ):
        write_bill_speaker_plan(scratch_session, wrong_plan)


def test_the_corpus_write_refuses_stored_rows_that_differ_from_the_plan(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_bill_speeches(scratch_session)
    real_add_many = CRUDBillReportSpeaker.add_many

    def add_many_one_short(
        self: CRUDBillReportSpeaker, bill_report_speakers: list[BillReportSpeaker]
    ) -> None:
        real_add_many(self, bill_report_speakers[:-1])

    monkeypatch.setattr(CRUDBillReportSpeaker, "add_many", add_many_one_short)

    with pytest.raises(
        HansardWriteCheckError,
        match="Stored bill report speakers by decade and report type",
    ):
        write_bill_speaker_plan(scratch_session, get_bill_speaker_plan(scratch_session))


def test_the_corpus_write_refuses_a_short_delete_count(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_bill_speeches(scratch_session)
    _write_corpus_plan(scratch_session)
    real_delete_all = CRUDBillKey.delete_all

    def delete_all_one_short(self: CRUDBillKey) -> int:
        return real_delete_all(self) - 1

    monkeypatch.setattr(CRUDBillKey, "delete_all", delete_all_one_short)

    with pytest.raises(HansardWriteCheckError, match="Deleted 0 bill keys, read 1"):
        write_bill_speaker_plan(scratch_session, get_bill_speaker_plan(scratch_session))


def test_the_report_plan_lists_every_given_report_and_plans_rows_for_joined_ones_only(
    scratch_session: Session,
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

    plan = get_report_bill_speaker_plan(
        scratch_session, [seeded.first_report_id, loose_report_id]
    )

    assert plan.sprs_report_ids == [
        BILL_SPEECHES_FIRST_SPRS_REPORT_ID,
        _LOOSE_SPRS_REPORT_ID,
    ]
    assert {
        bill_report_speaker.sprs_report_id
        for bill_report_speaker in plan.bill_report_speakers
    } == {BILL_SPEECHES_FIRST_SPRS_REPORT_ID}
    assert [bill_stage_line.stage for bill_stage_line in plan.bill_stage_lines] == [
        BillStage.FIRST_READING
    ]


def test_the_report_write_leaves_other_reports_rows_alone_and_removes_stale_rows_of_an_unjoined_report(
    scratch_session: Session,
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
    _write_corpus_plan(scratch_session)
    scratch_session.add(
        BillReportSpeaker(
            speech_count=1,
            first_ordinal=1,
            printed_speaker="Stale",
            sprs_report_id=_LOOSE_SPRS_REPORT_ID,
            speaker_id=seeded.speaker_a_id,
        )
    )
    third_report_speaker = scratch_session.exec(
        select(BillReportSpeaker).where(
            col(BillReportSpeaker.sprs_report_id) == BILL_SPEECHES_THIRD_SPRS_REPORT_ID
        )
    ).one()
    third_report_speaker.printed_speaker = "Hand edited"
    scratch_session.add(third_report_speaker)
    scratch_session.commit()

    plan = get_report_bill_speaker_plan(
        scratch_session, [seeded.first_report_id, loose_report_id]
    )
    write_report_bill_speaker_plan(scratch_session, plan)
    scratch_session.commit()

    assert _get_member_values(scratch_session) == [
        *_get_planned_member_values(seeded)[:2],
        (
            BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
            seeded.speaker_a_id,
            2,
            2,
            "Hand edited",
        ),
    ]

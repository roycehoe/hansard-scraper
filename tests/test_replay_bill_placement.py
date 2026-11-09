from datetime import datetime
from pathlib import Path

import pytest
from sqlmodel import Session

import scripts.replay_bill_placement as replay_script
from enums import BillLeftOutReason, BillReplayDifferenceKind, ReportType
from schemas.hand_kept_bill import HandKeptBill
from scripts.replay_bill_placement import get_bill_replay
from tests.bill_seed import seed_bill_report, seed_stored_bill

_TITLE = "Estate Duty Bill"
_FIRST_READING_LINE = "Bill read a First time."
_THIRD_READING_LINE = "Bill read a Third time and passed."
_FIRST_DATE = datetime(2025, 1, 15)
_SECOND_DATE = datetime(2025, 2, 19)
_THIRD_DATE = datetime(2025, 3, 5)
_TWO_REPORTS = 2
_THREE_REPORTS = 3
_FORBIDDEN_SOURCE_TEXTS = (
    "validate_can_write",
    "session.commit",
    "session.add",
    "--commit",
)


@pytest.fixture(autouse=True)
def _no_data_file_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(replay_script, "get_hand_kept_bills", list)
    monkeypatch.setattr(replay_script, "get_bill_title_corrections", list)


def _seed_estate_duty_bill(session: Session) -> list[int]:
    first_id = seed_bill_report(
        session,
        "estate-1",
        ReportType.BILL_INTRODUCTION,
        _FIRST_DATE,
        _TITLE,
        [_FIRST_READING_LINE],
    )
    second_id = seed_bill_report(
        session,
        "estate-2",
        ReportType.BILL,
        _SECOND_DATE,
        _TITLE,
        [_THIRD_READING_LINE],
    )
    seed_stored_bill(
        session, _TITLE, [first_id, second_id], _FIRST_DATE, _SECOND_DATE, True, None
    )
    return [first_id, second_id]


def test_a_replay_that_agrees_with_billreport_lists_nothing(
    scratch_session: Session,
) -> None:
    _seed_estate_duty_bill(scratch_session)

    bill_replay = get_bill_replay(scratch_session, False)

    assert bill_replay.placed_report_count == _TWO_REPORTS
    assert bill_replay.listed_differences == []
    assert bill_replay.explained_differences == []


def test_the_flipped_start_a_new_bill_test_lists_differences(
    scratch_session: Session,
) -> None:
    _seed_estate_duty_bill(scratch_session)

    bill_replay = get_bill_replay(scratch_session, True)

    assert bill_replay.listed_differences
    assert {difference.kind for difference in bill_replay.listed_differences} == {
        BillReplayDifferenceKind.DIFFERENT_BILL
    }


def test_a_report_the_rule_places_that_billreport_does_not_hold_is_listed(
    scratch_session: Session,
) -> None:
    _seed_estate_duty_bill(scratch_session)
    seed_bill_report(
        scratch_session, "estate-3", ReportType.BILL, _THIRD_DATE, "Gamma Bill", []
    )

    bill_replay = get_bill_replay(scratch_session, False)

    assert len(bill_replay.listed_differences) == 1
    assert bill_replay.listed_differences[0].sprs_report_id == "estate-3"
    assert (
        bill_replay.listed_differences[0].kind
        == BillReplayDifferenceKind.PLACED_BUT_NOT_STORED
    )


def test_a_bill_report_titled_adjournment_that_billreport_does_not_hold_lists_nothing(
    scratch_session: Session,
) -> None:
    seed_bill_report(
        scratch_session, "adjourn-1", ReportType.BILL, _FIRST_DATE, "ADJOURNMENT", []
    )

    bill_replay = get_bill_replay(scratch_session, False)

    assert bill_replay.listed_differences == []
    assert bill_replay.left_out_reason_to_report_count == {
        BillLeftOutReason.NO_BILL_WORD_IN_TITLE: 1
    }
    assert bill_replay.replayed_report_count == 1


def test_a_report_left_out_by_the_rule_that_billreport_holds_is_explained(
    scratch_session: Session,
) -> None:
    adjournment_id = seed_bill_report(
        scratch_session, "adjourn-1", ReportType.BILL, _FIRST_DATE, "ADJOURNMENT", []
    )
    seed_stored_bill(
        scratch_session,
        "ADJOURNMENT",
        [adjournment_id],
        _FIRST_DATE,
        _FIRST_DATE,
        False,
        None,
    )

    bill_replay = get_bill_replay(scratch_session, False)

    assert [difference.kind for difference in bill_replay.explained_differences] == [
        BillReplayDifferenceKind.LEFT_OUT_BY_RULE
    ]
    assert bill_replay.listed_differences == []


def test_a_stored_hand_kept_bill_explains_a_different_grouping(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_a_id = seed_bill_report(
        scratch_session,
        "estate-a",
        ReportType.BILL_INTRODUCTION,
        _FIRST_DATE,
        _TITLE,
        [_FIRST_READING_LINE],
    )
    report_b_id = seed_bill_report(
        scratch_session, "estate-b", ReportType.BILL, _SECOND_DATE, _TITLE, []
    )
    report_c_id = seed_bill_report(
        scratch_session, "estate-c", ReportType.BILL, _THIRD_DATE, _TITLE, []
    )
    seed_stored_bill(
        scratch_session,
        _TITLE,
        [report_a_id, report_c_id],
        _FIRST_DATE,
        _THIRD_DATE,
        False,
        None,
    )
    seed_stored_bill(
        scratch_session, _TITLE, [report_b_id], _SECOND_DATE, _SECOND_DATE, False, None
    )
    monkeypatch.setattr(
        replay_script,
        "get_hand_kept_bills",
        lambda: [
            HandKeptBill(title=_TITLE, report_ids=[report_a_id, report_c_id], reason="test")
        ],
    )

    bill_replay = get_bill_replay(scratch_session, False)

    assert len(bill_replay.explained_differences) == _THREE_REPORTS
    assert {difference.kind for difference in bill_replay.explained_differences} == {
        BillReplayDifferenceKind.HAND_KEPT_BILL
    }
    assert bill_replay.listed_differences == []


def test_only_the_latest_300_candidates_are_replayed(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_a_id = seed_bill_report(
        scratch_session,
        "estate-a",
        ReportType.BILL_INTRODUCTION,
        _FIRST_DATE,
        _TITLE,
        [_FIRST_READING_LINE],
    )
    report_b_id = seed_bill_report(
        scratch_session, "estate-b", ReportType.BILL, _SECOND_DATE, _TITLE, []
    )
    report_c_id = seed_bill_report(
        scratch_session,
        "estate-c",
        ReportType.BILL,
        _THIRD_DATE,
        _TITLE,
        [_THIRD_READING_LINE],
    )
    seed_stored_bill(
        scratch_session,
        _TITLE,
        [report_a_id, report_b_id, report_c_id],
        _FIRST_DATE,
        _THIRD_DATE,
        True,
        None,
    )
    monkeypatch.setattr(replay_script, "_REPLAYED_REPORT_COUNT", _TWO_REPORTS)

    bill_replay = get_bill_replay(scratch_session, False)

    assert bill_replay.replayed_report_count == _TWO_REPORTS
    assert bill_replay.listed_differences == []
    assert bill_replay.explained_differences == []


def test_the_script_module_defines_no_write_path() -> None:
    source = Path(replay_script.__file__).read_text(encoding="utf-8")

    for forbidden_text in _FORBIDDEN_SOURCE_TEXTS:
        assert forbidden_text not in source

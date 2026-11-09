import re
from datetime import datetime

import pytest
from sqlalchemy import Connection, Engine, event
from sqlmodel import Session, col, select

import populate.bill_speakers as bill_speakers_module
from database.bill import Bill, BillReport
from database.bill_key import BillKey
from database.bill_report_speaker import BillReportSpeaker
from database.bill_stage_line import BillStageLine
from enums import BillClass, BillReportRole, BillStage, ReportType, SpeechKind
from populate.bill_speakers import populate_bill_speakers
from tests.bill_seed import (
    seed_bill_report,
    seed_speaker,
    seed_speech,
    seed_stored_bill,
)

_FIRST_READING_LINE = "Bill read a First time."
_THIRD_READING_LINE = "Bill read a Third time and passed."
_FIRST_DATE = datetime(2025, 1, 15)
_SECOND_DATE = datetime(2025, 2, 19)
_THIRD_DATE = datetime(2025, 3, 5)
_STORED_BILL_NUMBER = "9/2024"
_SET_CLAUSE_PATTERN = re.compile(r"\bSET\b(.*?)\bWHERE\b", re.DOTALL | re.IGNORECASE)
_SET_COLUMN_PATTERN = re.compile(r"(\w+)=%\(")
_THREE_UPDATED_COLUMNS = ["title", "last_sitting_date", "is_passed"]
_SUMMARY_LINE_START = "Bills: placed 2 reports, started 1 bills, left out 0 reports"
_TWO_REPORTS = 2


class _LogRecorder:
    def __init__(self):
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


class _StatementRecorder:
    def __init__(self):
        self.statements: list[str] = []

    def record_statement(
        self,
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        self.statements.append(statement)


@pytest.fixture
def log_recorder(monkeypatch: pytest.MonkeyPatch) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(bill_speakers_module, "logger", recorder)
    return recorder


def _get_bills(session: Session) -> list[Bill]:
    return list(session.exec(select(Bill).order_by(col(Bill.id))).all())


def _get_bill_reports(session: Session) -> list[BillReport]:
    return list(session.exec(select(BillReport).order_by(col(BillReport.id))).all())


def _get_bill_keys(session: Session) -> list[BillKey]:
    return list(session.exec(select(BillKey).order_by(col(BillKey.id))).all())


def _get_bill_report_speakers(session: Session) -> list[BillReportSpeaker]:
    return list(
        session.exec(
            select(BillReportSpeaker).order_by(col(BillReportSpeaker.id))
        ).all()
    )


def _get_bill_stage_lines(session: Session) -> list[BillStageLine]:
    return list(
        session.exec(select(BillStageLine).order_by(col(BillStageLine.id))).all()
    )


def _count_rows(session: Session) -> list[int]:
    return [
        len(_get_bills(session)),
        len(_get_bill_reports(session)),
        len(_get_bill_keys(session)),
        len(_get_bill_report_speakers(session)),
        len(_get_bill_stage_lines(session)),
    ]


def _seed_bill_report(
    session: Session,
    sprs_report_id: str,
    sitting_date: datetime,
    title: str,
    lines: list[str],
) -> int:
    return seed_bill_report(
        session, sprs_report_id, ReportType.BILL, sitting_date, title, lines
    )


def _set_bill_number(session: Session, bill_id: int) -> None:
    bill = session.get(Bill, bill_id)
    assert bill is not None
    bill.bill_number = _STORED_BILL_NUMBER
    session.commit()


def test_a_new_bill_report_adds_a_bill_a_reading_row_and_a_key_row(
    scratch_session: Session,
) -> None:
    report_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", [_FIRST_READING_LINE]
    )

    populate_bill_speakers(scratch_session, [report_id])
    scratch_session.commit()

    bills = _get_bills(scratch_session)
    assert len(bills) == 1
    assert bills[0].title_key == "alphabill"
    assert bills[0].first_sitting_date == _FIRST_DATE
    assert bills[0].last_sitting_date == _FIRST_DATE
    assert bills[0].bill_class is None
    assert not bills[0].is_passed
    bill_reports = _get_bill_reports(scratch_session)
    assert len(bill_reports) == 1
    assert bill_reports[0].role == BillReportRole.READING
    assert bill_reports[0].report_id == report_id
    bill_keys = _get_bill_keys(scratch_session)
    assert len(bill_keys) == 1
    assert bill_keys[0].bill_key == "alpha-1"
    assert bill_keys[0].act_count == 0


def test_a_new_supply_bill_gets_its_class(scratch_session: Session) -> None:
    report_id = _seed_bill_report(
        scratch_session, "supply-1", _FIRST_DATE, "Supply Bill", [_FIRST_READING_LINE]
    )

    populate_bill_speakers(scratch_session, [report_id])
    scratch_session.commit()

    bills = _get_bills(scratch_session)
    assert len(bills) == 1
    assert bills[0].bill_class == BillClass.SUPPLY


def test_two_reports_of_one_new_bill_in_one_call_make_one_bill_and_one_key(
    scratch_session: Session,
) -> None:
    alpha_2_id = _seed_bill_report(
        scratch_session, "alpha-2", _SECOND_DATE, "Alpha Bill", [_THIRD_READING_LINE]
    )
    alpha_1_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", [_FIRST_READING_LINE]
    )

    populate_bill_speakers(scratch_session, [alpha_2_id, alpha_1_id])
    scratch_session.commit()

    bills = _get_bills(scratch_session)
    assert len(bills) == 1
    assert bills[0].is_passed
    assert bills[0].first_sitting_date == _FIRST_DATE
    assert len(_get_bill_reports(scratch_session)) == _TWO_REPORTS
    bill_keys = _get_bill_keys(scratch_session)
    assert len(bill_keys) == 1
    assert bill_keys[0].bill_key == "alpha-1"


def test_two_reports_on_one_date_take_the_lower_sprs_id_as_the_key(
    scratch_session: Session,
) -> None:
    zeta_id = _seed_bill_report(
        scratch_session, "zeta-1", _FIRST_DATE, "Alpha Bill", [_FIRST_READING_LINE]
    )
    alpha_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", []
    )
    assert zeta_id < alpha_id

    populate_bill_speakers(scratch_session, [zeta_id, alpha_id])
    scratch_session.commit()

    bill_keys = _get_bill_keys(scratch_session)
    assert len(bill_keys) == 1
    assert bill_keys[0].bill_key == "alpha-1"


def test_a_report_joins_an_open_bill_and_updates_three_columns(
    scratch_session: Session,
) -> None:
    stored_report_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", [_FIRST_READING_LINE]
    )
    bill_id = seed_stored_bill(
        scratch_session,
        "Alpha Bill",
        [stored_report_id],
        _FIRST_DATE,
        _FIRST_DATE,
        False,
        "alpha-1",
    )
    _set_bill_number(scratch_session, bill_id)
    new_report_id = _seed_bill_report(
        scratch_session, "alpha-2", _SECOND_DATE, "Alpha Bill", [_THIRD_READING_LINE]
    )

    populate_bill_speakers(scratch_session, [new_report_id])
    scratch_session.commit()
    scratch_session.expire_all()

    bills = _get_bills(scratch_session)
    assert len(bills) == 1
    assert bills[0].last_sitting_date == _SECOND_DATE
    assert bills[0].is_passed
    assert bills[0].bill_number == _STORED_BILL_NUMBER
    assert bills[0].title_key == "alphabill"
    assert bills[0].first_sitting_date == _FIRST_DATE
    assert len(_get_bill_reports(scratch_session)) == _TWO_REPORTS


def test_a_report_joining_a_bill_without_a_key_row_adds_no_key_row_and_raises_nothing(
    scratch_session: Session,
) -> None:
    stored_report_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", [_FIRST_READING_LINE]
    )
    seed_stored_bill(
        scratch_session,
        "Alpha Bill",
        [stored_report_id],
        _FIRST_DATE,
        _FIRST_DATE,
        False,
        None,
    )
    new_report_id = _seed_bill_report(
        scratch_session, "alpha-2", _SECOND_DATE, "Alpha Bill", []
    )

    populate_bill_speakers(scratch_session, [new_report_id])
    scratch_session.commit()

    assert _get_bill_keys(scratch_session) == []
    assert new_report_id in [
        bill_report.report_id for bill_report in _get_bill_reports(scratch_session)
    ]


def test_a_report_dated_before_its_open_bill_is_left_out(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    stored_report_id = _seed_bill_report(
        scratch_session, "alpha-2", _SECOND_DATE, "Alpha Bill", []
    )
    seed_stored_bill(
        scratch_session,
        "Alpha Bill",
        [stored_report_id],
        _SECOND_DATE,
        _SECOND_DATE,
        False,
        "alpha-2",
    )
    early_report_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", []
    )

    populate_bill_speakers(scratch_session, [early_report_id])
    scratch_session.commit()

    assert early_report_id not in [
        bill_report.report_id for bill_report in _get_bill_reports(scratch_session)
    ]
    assert "Bill report alpha-1 left out: DATED_BEFORE_OPEN_BILL" in (
        log_recorder.messages
    )


def test_a_report_sorting_below_a_stored_key_on_the_bills_first_date_is_left_out(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    stored_report_id = _seed_bill_report(
        scratch_session, "bill-b", _FIRST_DATE, "Alpha Bill", []
    )
    seed_stored_bill(
        scratch_session,
        "Alpha Bill",
        [stored_report_id],
        _FIRST_DATE,
        _FIRST_DATE,
        False,
        "bill-b",
    )
    low_report_id = _seed_bill_report(
        scratch_session, "bill-a", _FIRST_DATE, "Alpha Bill", []
    )

    populate_bill_speakers(scratch_session, [low_report_id])
    scratch_session.commit()

    assert low_report_id not in [
        bill_report.report_id for bill_report in _get_bill_reports(scratch_session)
    ]
    assert "Bill report bill-a left out: SORTS_BELOW_STORED_KEY" in (
        log_recorder.messages
    )
    bill_keys = _get_bill_keys(scratch_session)
    assert len(bill_keys) == 1
    assert bill_keys[0].bill_key == "bill-b"


def test_a_bill_report_titled_adjournment_is_left_out(
    scratch_session: Session,
) -> None:
    report_id = _seed_bill_report(
        scratch_session, "adjourn-1", _FIRST_DATE, "ADJOURNMENT", []
    )

    populate_bill_speakers(scratch_session, [report_id])
    scratch_session.commit()

    assert _get_bills(scratch_session) == []


def test_a_second_run_over_the_same_report_ids_writes_nothing(
    scratch_session: Session,
) -> None:
    speaker_id = seed_speaker(scratch_session, "Ms A")
    alpha_1_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", []
    )
    seed_speech(
        scratch_session,
        alpha_1_id,
        1,
        None,
        None,
        SpeechKind.PROCEDURAL,
        _FIRST_READING_LINE,
    )
    seed_speech(
        scratch_session,
        alpha_1_id,
        2,
        "Ms A",
        speaker_id,
        SpeechKind.SPEECH,
        "I support the Bill.",
    )
    alpha_2_id = _seed_bill_report(
        scratch_session, "alpha-2", _SECOND_DATE, "Alpha Bill", [_THIRD_READING_LINE]
    )
    report_ids = [alpha_1_id, alpha_2_id]

    populate_bill_speakers(scratch_session, report_ids)
    scratch_session.commit()
    counts_after_first_run = _count_rows(scratch_session)
    populate_bill_speakers(scratch_session, report_ids)
    scratch_session.commit()

    assert _count_rows(scratch_session) == counts_after_first_run
    assert counts_after_first_run[0] == 1


def test_member_and_stage_rows_are_added_for_placed_reports(
    scratch_session: Session,
) -> None:
    speaker_id = seed_speaker(scratch_session, "Ms A")
    report_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", []
    )
    seed_speech(
        scratch_session,
        report_id,
        1,
        None,
        None,
        SpeechKind.PROCEDURAL,
        _FIRST_READING_LINE,
    )
    seed_speech(
        scratch_session,
        report_id,
        2,
        "Ms A",
        speaker_id,
        SpeechKind.SPEECH,
        "I support the Bill.",
    )

    populate_bill_speakers(scratch_session, [report_id])
    scratch_session.commit()

    bill_report_speakers = _get_bill_report_speakers(scratch_session)
    assert len(bill_report_speakers) == 1
    assert bill_report_speakers[0].speech_count == 1
    assert bill_report_speakers[0].printed_speaker == "Ms A"
    bill_stage_lines = _get_bill_stage_lines(scratch_session)
    assert len(bill_stage_lines) == 1
    assert bill_stage_lines[0].stage == BillStage.FIRST_READING


def test_a_report_left_out_gets_no_member_or_stage_rows(
    scratch_session: Session,
) -> None:
    speaker_id = seed_speaker(scratch_session, "Ms A")
    report_id = _seed_bill_report(
        scratch_session, "adjourn-1", _FIRST_DATE, "ADJOURNMENT", []
    )
    seed_speech(
        scratch_session,
        report_id,
        1,
        None,
        None,
        SpeechKind.PROCEDURAL,
        _FIRST_READING_LINE,
    )
    seed_speech(
        scratch_session,
        report_id,
        2,
        "Ms A",
        speaker_id,
        SpeechKind.SPEECH,
        "I support the Bill.",
    )

    populate_bill_speakers(scratch_session, [report_id])
    scratch_session.commit()

    assert _get_bill_report_speakers(scratch_session) == []
    assert _get_bill_stage_lines(scratch_session) == []


def test_populate_issues_no_delete_and_updates_only_three_columns(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    stored_report_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", [_FIRST_READING_LINE]
    )
    seed_stored_bill(
        scratch_session,
        "Alpha Bill",
        [stored_report_id],
        _FIRST_DATE,
        _FIRST_DATE,
        False,
        "alpha-1",
    )
    joining_report_id = _seed_bill_report(
        scratch_session, "alpha-2", _SECOND_DATE, "Alpha Bill", [_THIRD_READING_LINE]
    )
    starting_report_id = _seed_bill_report(
        scratch_session, "beta-1", _THIRD_DATE, "Beta Bill", [_FIRST_READING_LINE]
    )
    recorder = _StatementRecorder()

    event.listen(scratch_engine, "before_cursor_execute", recorder.record_statement)
    try:
        populate_bill_speakers(
            scratch_session, [joining_report_id, starting_report_id]
        )
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", recorder.record_statement)

    normalized_statements = [
        " ".join(statement.split()).upper() for statement in recorder.statements
    ]
    assert [
        statement
        for statement in normalized_statements
        if statement.startswith("DELETE") or statement.startswith("TRUNCATE")
    ] == []
    update_statements = [
        statement
        for statement in recorder.statements
        if statement.lstrip().upper().startswith("UPDATE")
    ]
    assert update_statements
    for update_statement in update_statements:
        assert update_statement.lstrip().upper().startswith("UPDATE BILL ")
        set_clause_match = _SET_CLAUSE_PATTERN.search(update_statement)
        assert set_clause_match is not None
        assert (
            _SET_COLUMN_PATTERN.findall(set_clause_match[1]) == _THREE_UPDATED_COLUMNS
        )


def test_the_summary_line_counts_placed_reports_and_members(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    alpha_1_id = _seed_bill_report(
        scratch_session, "alpha-1", _FIRST_DATE, "Alpha Bill", [_FIRST_READING_LINE]
    )
    alpha_2_id = _seed_bill_report(
        scratch_session, "alpha-2", _SECOND_DATE, "Alpha Bill", [_THIRD_READING_LINE]
    )

    populate_bill_speakers(scratch_session, [alpha_1_id, alpha_2_id])

    assert log_recorder.messages[-1].startswith(_SUMMARY_LINE_START)

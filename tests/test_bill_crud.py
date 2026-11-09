import re
from datetime import datetime

from sqlalchemy import Connection, Engine, event
from sqlmodel import Session

from crud.bill import CRUDBill
from crud.bill_key import CRUDBillKey
from database.bill import Bill
from database.bill_key import BillKey
from enums import BillClass, ReportType
from tests.bill_seed import seed_bill_report
from utils.bill_join_update import BillJoinUpdate

_FIRST_DATE = datetime(2025, 1, 15)
_LAST_DATE = datetime(2025, 3, 5)
_NEW_LAST_DATE = datetime(2025, 4, 9)
_SET_CLAUSE_PATTERN = re.compile(r"\bSET\b(.*?)\bWHERE\b", re.DOTALL | re.IGNORECASE)
_SET_COLUMN_PATTERN = re.compile(r"(\w+)=%\(")
_THREE_UPDATED_COLUMNS = ["title", "last_sitting_date", "is_passed"]
_ALPHA_ACT_COUNT = 3


class _StatementRecorder:
    def __init__(self) -> None:
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


def _add_bill(
    session: Session, title: str, title_key: str, is_passed: bool = False
) -> int:
    bill = Bill(
        title=title,
        title_key=title_key,
        first_sitting_date=_FIRST_DATE,
        last_sitting_date=_LAST_DATE,
        is_passed=is_passed,
    )
    session.add(bill)
    session.commit()
    assert bill.id is not None
    return bill.id


def test_get_rows_by_title_keys_returns_only_the_bills_of_those_keys(
    scratch_session: Session,
) -> None:
    alpha_id = _add_bill(scratch_session, "Alpha Bill", "alphabill")
    _add_bill(scratch_session, "Beta Bill", "betabill")
    gamma_id = _add_bill(scratch_session, "Gamma Bill", "gammabill")

    bill_rows = CRUDBill(scratch_session).get_rows_by_title_keys(
        ["gammabill", "alphabill"]
    )

    assert [bill_row.id for bill_row in bill_rows] == [alpha_id, gamma_id]


def test_get_rows_by_title_keys_with_no_keys_returns_nothing(
    scratch_session: Session,
) -> None:
    _add_bill(scratch_session, "Alpha Bill", "alphabill")

    assert CRUDBill(scratch_session).get_rows_by_title_keys([]) == []


def test_the_three_column_update_changes_only_those_columns(
    scratch_session: Session,
) -> None:
    bill = Bill(
        title="Alpha Bill",
        title_key="alphabill",
        first_sitting_date=_FIRST_DATE,
        last_sitting_date=_LAST_DATE,
        is_passed=False,
        bill_number="9/2024",
        bill_class=BillClass.SUPPLY,
    )
    scratch_session.add(bill)
    scratch_session.commit()
    assert bill.id is not None

    CRUDBill(scratch_session).update_title_and_last_sitting_date_and_is_passed_many(
        [BillJoinUpdate(bill.id, "ALPHA BILL", _NEW_LAST_DATE, True)]
    )
    scratch_session.commit()
    scratch_session.refresh(bill)

    assert bill.title == "ALPHA BILL"
    assert bill.last_sitting_date == _NEW_LAST_DATE
    assert bill.is_passed
    assert bill.title_key == "alphabill"
    assert bill.first_sitting_date == _FIRST_DATE
    assert bill.bill_number == "9/2024"
    assert bill.bill_class == BillClass.SUPPLY


def test_the_three_column_update_updates_every_bill_given(
    scratch_session: Session,
) -> None:
    alpha_id = _add_bill(scratch_session, "Alpha Bill", "alphabill")
    beta_id = _add_bill(scratch_session, "Beta Bill", "betabill")

    CRUDBill(scratch_session).update_title_and_last_sitting_date_and_is_passed_many(
        [
            BillJoinUpdate(alpha_id, "ALPHA BILL", _NEW_LAST_DATE, True),
            BillJoinUpdate(beta_id, "BETA BILL", _NEW_LAST_DATE, False),
        ]
    )
    scratch_session.commit()

    bill_rows = CRUDBill(scratch_session).get_rows_by_title_keys(
        ["alphabill", "betabill"]
    )
    assert [bill_row.title for bill_row in bill_rows] == ["ALPHA BILL", "BETA BILL"]
    assert [bill_row.last_sitting_date for bill_row in bill_rows] == [
        _NEW_LAST_DATE,
        _NEW_LAST_DATE,
    ]
    assert [bill_row.is_passed for bill_row in bill_rows] == [True, False]


def test_the_three_column_update_with_no_updates_sends_no_statement(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    recorder = _StatementRecorder()

    event.listen(scratch_engine, "before_cursor_execute", recorder.record_statement)
    try:
        CRUDBill(scratch_session).update_title_and_last_sitting_date_and_is_passed_many(
            []
        )
    finally:
        event.remove(scratch_engine, "before_cursor_execute", recorder.record_statement)

    assert recorder.statements == []


def test_the_three_column_update_sets_exactly_three_columns(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    bill_id = _add_bill(scratch_session, "Alpha Bill", "alphabill")
    recorder = _StatementRecorder()

    event.listen(scratch_engine, "before_cursor_execute", recorder.record_statement)
    try:
        CRUDBill(scratch_session).update_title_and_last_sitting_date_and_is_passed_many(
            [BillJoinUpdate(bill_id, "ALPHA BILL", _NEW_LAST_DATE, True)]
        )
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", recorder.record_statement)

    update_statements = [
        statement
        for statement in recorder.statements
        if statement.lstrip().upper().startswith("UPDATE BILL ")
    ]
    assert update_statements
    for update_statement in update_statements:
        set_clause_match = _SET_CLAUSE_PATTERN.search(update_statement)
        assert set_clause_match is not None
        assert (
            _SET_COLUMN_PATTERN.findall(set_clause_match[1]) == _THREE_UPDATED_COLUMNS
        )


def test_get_rows_by_bill_ids_returns_the_key_rows_of_those_bills(
    scratch_session: Session,
) -> None:
    seed_bill_report(
        scratch_session, "alpha-1", ReportType.BILL, _FIRST_DATE, "Alpha Bill", []
    )
    seed_bill_report(
        scratch_session, "beta-1", ReportType.BILL, _FIRST_DATE, "Beta Bill", []
    )
    alpha_bill_id = _add_bill(scratch_session, "Alpha Bill", "alphabill")
    beta_bill_id = _add_bill(scratch_session, "Beta Bill", "betabill")
    scratch_session.add(
        BillKey(act_count=_ALPHA_ACT_COUNT, bill_key="alpha-1", bill_id=alpha_bill_id)
    )
    scratch_session.add(BillKey(act_count=0, bill_key="beta-1", bill_id=beta_bill_id))
    scratch_session.commit()

    key_rows = CRUDBillKey(scratch_session).get_rows_by_bill_ids([alpha_bill_id])

    assert len(key_rows) == 1
    assert key_rows[0].bill_key == "alpha-1"
    assert key_rows[0].act_count == _ALPHA_ACT_COUNT
    assert key_rows[0].bill_id == alpha_bill_id

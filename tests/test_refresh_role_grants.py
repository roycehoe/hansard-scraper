from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime

import pytest
from sqlalchemy import Connection, Engine, event
from sqlmodel import Session, SQLModel

from enums import ReportType, SpeechKind
from populate.bill_speakers import populate_bill_speakers
from tests.bill_seed import (
    seed_bill_report,
    seed_speaker,
    seed_speech,
    seed_stored_bill,
)
from tests.refresh_role_grants import (
    RoleGrants,
    get_grant_violations,
    get_role_grants,
    get_write_role_blocks,
)

_TABLE_NAMES = frozenset(table.name for table in SQLModel.metadata.sorted_tables)
_FIRST_READING_LINE = "Bill read a First time."
_THIRD_READING_LINE = "Bill read a Third time and passed."
_FIRST_DATE = datetime(2025, 1, 15)
_SECOND_DATE = datetime(2025, 2, 19)
_THIRD_DATE = datetime(2025, 3, 5)
_NEW_TABLES = (
    "bill",
    "billreport",
    "billkey",
    "billreportspeaker",
    "billstageline",
)
_NEW_SEQUENCES = (
    "bill_id_seq",
    "billreport_id_seq",
    "billkey_id_seq",
    "billreportspeaker_id_seq",
    "billstageline_id_seq",
)
_NEW_BILL_COLUMNS = ("title", "last_sitting_date", "is_passed")
_VERIFICATION_FUNCTIONS = (
    "has_table_privilege",
    "has_column_privilege",
    "has_sequence_privilege",
)


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


def _seed_scenario(session: Session) -> list[int]:
    speaker_id = seed_speaker(session, "Ms A")
    stored_report_id = seed_bill_report(
        session, "alpha-1", ReportType.BILL, _FIRST_DATE, "Alpha Bill", []
    )
    seed_stored_bill(
        session,
        "Alpha Bill",
        [stored_report_id],
        _FIRST_DATE,
        _FIRST_DATE,
        False,
        "alpha-1",
    )
    alpha_2_id = seed_bill_report(
        session,
        "alpha-2",
        ReportType.BILL,
        _SECOND_DATE,
        "Alpha Bill",
        [_THIRD_READING_LINE],
    )
    seed_speech(
        session, alpha_2_id, 2, "Ms A", speaker_id, SpeechKind.SPEECH, "I agree."
    )
    beta_1_id = seed_bill_report(
        session, "beta-1", ReportType.BILL, _THIRD_DATE, "Beta Bill", []
    )
    seed_speech(
        session,
        beta_1_id,
        1,
        None,
        None,
        SpeechKind.PROCEDURAL,
        _FIRST_READING_LINE,
    )
    seed_speech(
        session, beta_1_id, 2, "Ms A", speaker_id, SpeechKind.SPEECH, "I support it."
    )
    adjourn_1_id = seed_bill_report(
        session, "adjourn-1", ReportType.BILL, _THIRD_DATE, "ADJOURNMENT", []
    )
    return [alpha_2_id, beta_1_id, adjourn_1_id]


@pytest.fixture
def recorded_statements(
    scratch_engine: Engine, scratch_session: Session
) -> Iterator[list[str]]:
    report_ids = _seed_scenario(scratch_session)
    recorder = _StatementRecorder()
    event.listen(scratch_engine, "before_cursor_execute", recorder.record_statement)
    try:
        populate_bill_speakers(scratch_session, report_ids)
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", recorder.record_statement)
    yield recorder.statements


def _get_role_grants() -> RoleGrants:
    return get_role_grants(get_write_role_blocks()[0])


def test_the_scenario_sends_the_statements_the_grants_must_cover(
    recorded_statements: list[str],
) -> None:
    for statement_start in (
        "INSERT INTO bill ",
        "INSERT INTO billkey",
        "INSERT INTO billreport ",
        "UPDATE bill SET",
    ):
        assert any(
            statement.startswith(statement_start) for statement in recorded_statements
        )
    assert any(
        "FROM billreport" in statement or "JOIN billreport" in statement
        for statement in recorded_statements
    )


def test_the_stage_statements_pass_the_grants_in_the_doc(
    recorded_statements: list[str],
) -> None:
    assert (
        get_grant_violations(recorded_statements, _TABLE_NAMES, _get_role_grants())
        == []
    )


def test_dropping_is_passed_from_the_column_grant_fails(
    recorded_statements: list[str],
) -> None:
    role_grants = _get_role_grants()
    weakened_grants = replace(
        role_grants,
        column_privileges=role_grants.column_privileges - {"UPDATE bill.is_passed"},
    )

    violations = get_grant_violations(recorded_statements, _TABLE_NAMES, weakened_grants)

    assert "UPDATE on bill.is_passed" in violations


def test_dropping_a_sequence_grant_fails(recorded_statements: list[str]) -> None:
    role_grants = _get_role_grants()
    weakened_grants = replace(
        role_grants,
        sequence_usages=role_grants.sequence_usages - {"billkey_id_seq"},
    )

    violations = get_grant_violations(recorded_statements, _TABLE_NAMES, weakened_grants)

    assert "USAGE on billkey_id_seq" in violations


def test_a_delete_statement_fails() -> None:
    role_grants = _get_role_grants()

    assert get_grant_violations(
        ["DELETE FROM billkey WHERE billkey.id = 1"], _TABLE_NAMES, role_grants
    )
    assert get_grant_violations(["TRUNCATE billkey"], _TABLE_NAMES, role_grants)


def test_the_parser_reads_the_existing_and_new_grants() -> None:
    role_grants = _get_role_grants()

    assert "SELECT billkey" in role_grants.table_privileges
    assert "INSERT billreportspeaker" in role_grants.table_privileges
    assert "UPDATE speech.speaker_id" in role_grants.column_privileges
    assert "UPDATE bill.title" in role_grants.column_privileges
    assert "billstageline_id_seq" in role_grants.sequence_usages
    assert "SELECT refresh_run.id" not in role_grants.column_privileges


def test_the_doc_grants_no_delete_and_only_three_bill_columns() -> None:
    role_grants = _get_role_grants()

    assert not [
        privilege
        for privilege in role_grants.table_privileges | role_grants.column_privileges
        if privilege.startswith("DELETE")
    ]
    assert {
        column_privilege
        for column_privilege in role_grants.column_privileges
        if column_privilege.startswith("UPDATE bill.")
    } == {f"UPDATE bill.{column}" for column in _NEW_BILL_COLUMNS}


def test_the_verification_query_names_every_granted_bill_object() -> None:
    verification_query = get_write_role_blocks()[1]

    for name in _NEW_TABLES + _NEW_SEQUENCES + _NEW_BILL_COLUMNS:
        assert f"'{name}'" in verification_query
    for function_name in _VERIFICATION_FUNCTIONS:
        assert function_name in verification_query

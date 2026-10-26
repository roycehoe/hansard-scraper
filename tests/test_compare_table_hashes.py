import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import InternalError
from sqlmodel import Session

from crud.table_hash import TableHash
from database.sitting import Sitting
from scripts.compare_table_hashes import (
    get_database_label,
    get_lines,
    get_read_only_session,
    get_table_hashes,
)


def _add_sitting(session: Session, sitting_id: int, parlement_no: int) -> None:
    session.add(Sitting(id=sitting_id, parlement_no=parlement_no, sitting_date="1-1-2000"))
    session.commit()


def test_the_same_rows_inserted_in_another_order_hash_equal(scratch_engine: Engine, scratch_session: Session) -> None:
    _add_sitting(scratch_session, 1, 9)
    _add_sitting(scratch_session, 2, 10)
    first = get_table_hashes(scratch_engine)["sitting"]
    scratch_session.execute(text("DELETE FROM sitting"))
    scratch_session.commit()
    _add_sitting(scratch_session, 2, 10)
    _add_sitting(scratch_session, 1, 9)

    assert get_table_hashes(scratch_engine)["sitting"] == first


def test_a_changed_value_changes_the_hash_and_keeps_the_count(scratch_engine: Engine, scratch_session: Session) -> None:
    _add_sitting(scratch_session, 1, 9)
    before = get_table_hashes(scratch_engine)["sitting"]
    scratch_session.execute(text("UPDATE sitting SET parlement_no = 10"))
    scratch_session.commit()
    after = get_table_hashes(scratch_engine)["sitting"]

    assert after.row_count == before.row_count == 1
    assert after.content_hash != before.content_hash


def test_every_table_is_hashed_and_an_empty_one_counts_zero(scratch_engine: Engine, scratch_session: Session) -> None:
    hashes = get_table_hashes(scratch_engine)

    assert {"sitting", "speech", "report", "attendance"} <= hashes.keys()
    assert hashes["speech"].row_count == 0


def test_the_connection_refuses_a_write(scratch_engine: Engine, scratch_session: Session) -> None:
    with get_read_only_session(scratch_engine) as session, pytest.raises(InternalError):
        session.execute(text("DELETE FROM sitting"))


def test_the_label_leaves_out_the_user_and_the_password() -> None:
    assert get_database_label("postgresql://user:secret@db.example.org:6543/hansard") == "db.example.org:6543/hansard"


def test_only_the_differing_table_is_named() -> None:
    same = TableHash(3, "a" * 32)
    first = {"person": same, "report": TableHash(5, "b" * 32), "only_first": same}
    second = {"person": same, "report": TableHash(5, "c" * 32)}

    lines = get_lines("localhost:5435/one", first, "localhost:5435/two", second)

    assert lines[-1] == "Differing tables: only_first, report"
    assert "person | 3 rows " + "a" * 32 + " | 3 rows " + "a" * 32 + " | same" in lines
    assert any(line.startswith("only_first |") and "| missing |" in line for line in lines)

import pytest
from sqlmodel import Session

from crud.vacuum import CRUDVacuum
from database.report import Report
from database.speech import Speech
from exceptions import HansardWriteCheckError
from populate.written_tables import vacuum_analyze_written_tables


def _skip_vacuum_analyze(*args: object) -> None:
    pass


def test_vacuum_runs_on_every_written_table(scratch_session: Session) -> None:
    table_names = [Speech.__tablename__, Report.__tablename__]
    vacuum_counts_before = [CRUDVacuum(scratch_session).get_vacuum_count(table_name) for table_name in table_names]
    scratch_session.commit()

    vacuum_analyze_written_tables(scratch_session, table_names)

    assert [CRUDVacuum(scratch_session).get_vacuum_count(table_name) for table_name in table_names] == [
        vacuum_count + 1 for vacuum_count in vacuum_counts_before
    ]


def test_skipped_vacuum_fails_loudly(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CRUDVacuum, "vacuum_analyze", _skip_vacuum_analyze)

    with pytest.raises(HansardWriteCheckError, match=r"VACUUM \(ANALYZE\) did not run on speech"):
        vacuum_analyze_written_tables(scratch_session, [Speech.__tablename__])

import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"
_DOWN_REVISION = "d9e4f2a7b3c1"
_REVISION = "7b1f3c9a2e40"
_CREATE_TABLE = "CREATE TABLE"
_INDEX_COUNT = 2
_TYPE_COUNT = 2


def _get_upgrade_sql() -> str:
    output = io.StringIO()
    command.upgrade(
        Config(str(_ALEMBIC_INI), output_buffer=output),
        f"{_DOWN_REVISION}:{_REVISION}",
        sql=True,
    )
    return output.getvalue()


def test_upgrade_creates_only_division() -> None:
    upgrade_sql = _get_upgrade_sql()

    assert upgrade_sql.count(_CREATE_TABLE) == 1
    assert f"{_CREATE_TABLE} division" in upgrade_sql
    assert upgrade_sql.count("CREATE TYPE") == _TYPE_COUNT
    assert (
        "CREATE TYPE divisioncountsource AS ENUM ('PRINTED_LINE', 'SPOKEN_TOTAL', 'MINUTES')"
        in upgrade_sql
    )
    assert (
        "CREATE TYPE divisionliststatus AS ENUM ('NOT_PRINTED', 'STORED', 'COUNTS_DISAGREE', 'LAYOUT_UNREADABLE')"
        in upgrade_sql
    )
    assert upgrade_sql.count("CREATE INDEX") == _INDEX_COUNT
    assert "CREATE INDEX ix_division_sitting_date" in upgrade_sql
    assert "CREATE INDEX ix_division_sprs_report_id" in upgrade_sql
    assert (
        "CONSTRAINT uq_division_sprs_report_id_report_division_number UNIQUE (sprs_report_id, report_division_number) DEFERRABLE INITIALLY DEFERRED"
        in upgrade_sql
    )
    assert "FOREIGN KEY(sprs_report_id) REFERENCES report (report_id)" in upgrade_sql
    assert "ALTER TABLE" not in upgrade_sql
    assert "DROP" not in upgrade_sql
    for line in upgrade_sql.splitlines():
        if "UPDATE" in line:
            assert "alembic_version" in line


def test_division_migration_is_the_only_head_after_the_previous_one() -> None:
    assert len(ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_heads()) == 1

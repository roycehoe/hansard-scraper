import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"
_DOWN_REVISION = "7b1f3c9a2e40"
_REVISION = "3e8a6d15c2f7"
_CREATE_TABLE = "CREATE TABLE"
_TABLE_COUNT = 2
_TYPE_COUNT = 3
_INDEX_COUNT = 1


def _get_upgrade_sql() -> str:
    output = io.StringIO()
    command.upgrade(
        Config(str(_ALEMBIC_INI), output_buffer=output),
        f"{_DOWN_REVISION}:{_REVISION}",
        sql=True,
    )
    return output.getvalue()


def test_upgrade_creates_only_the_minutes_tables() -> None:
    upgrade_sql = _get_upgrade_sql()

    assert upgrade_sql.count(_CREATE_TABLE) == _TABLE_COUNT
    assert f"{_CREATE_TABLE} minutes_index_capture" in upgrade_sql
    assert f"{_CREATE_TABLE} minutes (" in upgrade_sql
    assert upgrade_sql.count("CREATE TYPE") == _TYPE_COUNT
    assert (
        "CREATE TYPE minutesstatus AS ENUM ('NOT_YET_LISTED', 'LISTED', 'TEXT_STORED', 'FILE_NOT_FOUND', 'NEEDS_REVIEW')"
        in upgrade_sql
    )
    assert (
        "CREATE TYPE minutesindexsource AS ENUM ('LIVE_PAGE', 'ARCHIVE_INDEX_CAPTURE', 'ARCHIVE_FILE_LISTING')"
        in upgrade_sql
    )
    assert "CREATE TYPE minutesfileformat AS ENUM ('PDF', 'WORD')" in upgrade_sql
    assert upgrade_sql.count("CREATE INDEX") == _INDEX_COUNT
    assert "CREATE INDEX ix_minutes_index_capture_id" in upgrade_sql
    assert "UNIQUE (sitting_date)" in upgrade_sql
    assert "UNIQUE (capture_url)" in upgrade_sql
    assert "fetched_at TIMESTAMP WITH TIME ZONE" in upgrade_sql
    assert "ALTER TABLE" not in upgrade_sql
    assert "DROP" not in upgrade_sql
    for line in upgrade_sql.splitlines():
        if "UPDATE" in line:
            assert "alembic_version" in line


def test_chain_has_one_head() -> None:
    assert len(ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_heads()) == 1

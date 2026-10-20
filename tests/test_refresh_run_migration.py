import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"
_DOWN_REVISION = "c93f77e499cc"
_REVISION = "b8e2f4a61c03"
_CREATE_TABLE = "CREATE TABLE"


def _get_upgrade_sql() -> str:
    output = io.StringIO()
    command.upgrade(Config(str(_ALEMBIC_INI), output_buffer=output), f"{_DOWN_REVISION}:{_REVISION}", sql=True)
    return output.getvalue()


def test_upgrade_creates_only_refresh_run() -> None:
    upgrade_sql = _get_upgrade_sql()

    assert upgrade_sql.count(_CREATE_TABLE) == 1
    assert f"{_CREATE_TABLE} refresh_run" in upgrade_sql
    assert "ALTER TABLE" not in upgrade_sql
    assert "DROP" not in upgrade_sql
    assert "CREATE TYPE" not in upgrade_sql
    assert "CREATE INDEX ix_refresh_run_started_at" in upgrade_sql
    assert "CONSTRAINT ck_refresh_run_status CHECK (status IN ('RUNNING', 'SUCCEEDED', 'HALTED', 'FAILED'))" in upgrade_sql
    for line in upgrade_sql.splitlines():
        if "UPDATE" in line:
            assert "alembic_version" in line


def test_migration_chain_has_one_head() -> None:
    assert len(ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_heads()) == 1

import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"
_DOWN_REVISION = "5fa92d0e8b13"
_REVISION = "a6d3f1b8c2e5"


def _get_upgrade_sql() -> str:
    output = io.StringIO()
    command.upgrade(
        Config(str(_ALEMBIC_INI), output_buffer=output),
        f"{_DOWN_REVISION}:{_REVISION}",
        sql=True,
    )
    return output.getvalue()


def _get_downgrade_sql() -> str:
    output = io.StringIO()
    command.downgrade(
        Config(str(_ALEMBIC_INI), output_buffer=output),
        f"{_REVISION}:{_DOWN_REVISION}",
        sql=True,
    )
    return output.getvalue()


def test_upgrade_adds_only_the_nullable_file_bytes_column() -> None:
    upgrade_sql = _get_upgrade_sql()

    assert upgrade_sql.count("ALTER TABLE") == 1
    assert "ALTER TABLE minutes ADD COLUMN file_bytes BYTEA" in upgrade_sql
    assert "NOT NULL" not in upgrade_sql
    assert "CREATE" not in upgrade_sql
    assert "DROP" not in upgrade_sql
    for line in upgrade_sql.splitlines():
        if "UPDATE" in line:
            assert "alembic_version" in line


def test_downgrade_drops_only_the_file_bytes_column() -> None:
    downgrade_sql = _get_downgrade_sql()

    assert downgrade_sql.count("ALTER TABLE") == 1
    assert "ALTER TABLE minutes DROP COLUMN file_bytes" in downgrade_sql
    assert "DROP TABLE" not in downgrade_sql


def test_file_bytes_migration_is_the_only_head() -> None:
    assert len(ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_heads()) == 1

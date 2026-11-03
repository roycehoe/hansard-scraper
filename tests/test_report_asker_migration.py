import io
from pathlib import Path

from alembic import command
from alembic.config import Config

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"
_DOWN_REVISION = "82478ba59541"
_REVISION = "52f4f7b77f1f"
_CREATE_TABLE = "CREATE TABLE"
_INDEX_COUNT = 2


def _get_upgrade_sql() -> str:
    output = io.StringIO()
    command.upgrade(
        Config(str(_ALEMBIC_INI), output_buffer=output),
        f"{_DOWN_REVISION}:{_REVISION}",
        sql=True,
    )
    return output.getvalue()


def test_upgrade_creates_only_report_asker() -> None:
    upgrade_sql = _get_upgrade_sql()

    assert upgrade_sql.count(_CREATE_TABLE) == 1
    assert f"{_CREATE_TABLE} report_asker" in upgrade_sql
    assert upgrade_sql.count("CREATE TYPE") == 1
    assert (
        "CREATE TYPE reportaskersource AS ENUM ('ASKED_LINE', 'TO_ASK_LINE', 'STOOD_IN_NAME_LINE', 'NAME_IN_TEXT')"
        in upgrade_sql
    )
    assert upgrade_sql.count("CREATE INDEX") == _INDEX_COUNT
    assert "CREATE INDEX ix_report_asker_report_id" in upgrade_sql
    assert "CREATE INDEX ix_report_asker_speaker_id" in upgrade_sql
    assert (
        "CONSTRAINT uq_report_asker_report_id_ordinal UNIQUE (report_id, ordinal)"
        in upgrade_sql
    )
    assert "ALTER TABLE" not in upgrade_sql
    assert "DROP" not in upgrade_sql
    for line in upgrade_sql.splitlines():
        if "UPDATE" in line:
            assert "alembic_version" in line

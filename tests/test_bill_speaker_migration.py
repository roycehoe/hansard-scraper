import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from enums import BillStage

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"
_DOWN_REVISION = "e7b2c4d9f1a6"
_REVISION = "e1a5c7b9d3f2"
_CREATE_TABLE = "CREATE TABLE"
_TABLE_COUNT = 3
_INDEX_COUNT = 3


def _get_upgrade_sql() -> str:
    output = io.StringIO()
    command.upgrade(
        Config(str(_ALEMBIC_INI), output_buffer=output),
        f"{_DOWN_REVISION}:{_REVISION}",
        sql=True,
    )
    return output.getvalue()


def test_upgrade_creates_only_the_three_bill_speaker_tables() -> None:
    upgrade_sql = _get_upgrade_sql()
    stage_list = ", ".join(f"'{stage.value}'" for stage in BillStage)

    assert upgrade_sql.count(_CREATE_TABLE) == _TABLE_COUNT
    assert f"{_CREATE_TABLE} billkey" in upgrade_sql
    assert f"{_CREATE_TABLE} billreportspeaker" in upgrade_sql
    assert f"{_CREATE_TABLE} billstageline" in upgrade_sql
    assert upgrade_sql.count("CREATE TYPE") == 1
    assert f"CREATE TYPE billstage AS ENUM ({stage_list})" in upgrade_sql
    assert upgrade_sql.count("CREATE INDEX") == _INDEX_COUNT
    assert "CREATE INDEX ix_billreportspeaker_sprs_report_id" in upgrade_sql
    assert "CREATE INDEX ix_billreportspeaker_speaker_id" in upgrade_sql
    assert "CREATE INDEX ix_billstageline_sprs_report_id" in upgrade_sql
    assert (
        "CONSTRAINT uq_billreportspeaker_sprs_report_id_speaker_id UNIQUE (sprs_report_id, speaker_id)"
        in upgrade_sql
    )
    assert (
        "CONSTRAINT uq_billstageline_sprs_report_id_ordinal_stage UNIQUE (sprs_report_id, ordinal, stage)"
        in upgrade_sql
    )
    assert "UNIQUE (bill_key)" in upgrade_sql
    assert "UNIQUE (bill_id)" in upgrade_sql
    assert "REFERENCES report (report_id)" in upgrade_sql
    assert "REFERENCES bill (id)" in upgrade_sql
    assert "REFERENCES speaker (id)" in upgrade_sql
    assert "ALTER TABLE" not in upgrade_sql
    assert "DROP" not in upgrade_sql
    assert "CASCADE" not in upgrade_sql
    assert all(
        "alembic_version" in line
        for line in upgrade_sql.splitlines()
        if "UPDATE" in line
    )


def test_the_enum_values_equal_their_names() -> None:
    assert [stage.value for stage in BillStage] == [stage.name for stage in BillStage]
    assert [stage.value for stage in BillStage] == [
        "FIRST_READING",
        "SECOND_READING_ORDER",
        "SECOND_READING_AGREED",
        "THIRD_READING",
    ]


def test_the_revision_chain_has_one_head() -> None:
    assert len(ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_heads()) == 1

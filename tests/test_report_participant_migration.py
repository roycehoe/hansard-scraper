import io
from pathlib import Path

from alembic import command
from alembic.config import Config

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"
_DOWN_REVISION = "52f4f7b77f1f"
_REVISION = "b50219e27a8f"
_CREATE_TABLE = "CREATE TABLE"
_TABLE_COUNT = 2
_TYPE_COUNT = 5
_INDEX_COUNT = 3


def _get_upgrade_sql() -> str:
    output = io.StringIO()
    command.upgrade(
        Config(str(_ALEMBIC_INI), output_buffer=output),
        f"{_DOWN_REVISION}:{_REVISION}",
        sql=True,
    )
    return output.getvalue()


def test_upgrade_creates_only_the_report_participant_tables() -> None:
    upgrade_sql = _get_upgrade_sql()

    assert upgrade_sql.count(_CREATE_TABLE) == _TABLE_COUNT
    assert f"{_CREATE_TABLE} report_participant" in upgrade_sql
    assert f"{_CREATE_TABLE} report_question_state" in upgrade_sql
    assert upgrade_sql.count("CREATE TYPE") == _TYPE_COUNT
    assert (
        "CREATE TYPE participantrole AS ENUM ('ASKER', 'ABSENT_FILER', 'READER', 'ASKER_FOLLOW_UP', 'SUPPLEMENTARY', 'ANSWERER', 'CHAIR', 'UNLABELLED')"
        in upgrade_sql
    )
    assert (
        "CREATE TYPE participantrolesource AS ENUM ('ASKER_RULES', 'CHAIR_LABEL', 'CHAIR_NAME_CALL', 'OFFICE_LABEL', 'OFFICE_ON_THE_DAY', 'POSITION', 'AFTER_ANSWER', 'NO_RULE')"
        in upgrade_sql
    )
    assert (
        "CREATE TYPE officeclass AS ENUM ('PRIME_MINISTER', 'DEPUTY_PRIME_MINISTER', 'MINISTER', 'SENIOR_MINISTER_OF_STATE', 'MINISTER_OF_STATE', 'SENIOR_PARLIAMENTARY_SECRETARY', 'PARLIAMENTARY_SECRETARY', 'OTHER')"
        in upgrade_sql
    )
    assert (
        "CREATE TYPE officesource AS ENUM ('LABEL_IN_REPORT', 'HEADER_IN_REPORT', 'ATTENDANCE_LIST', 'LABEL_SAME_DAY', 'PARLIAMENT_GUESS')"
        in upgrade_sql
    )
    assert (
        "CREATE TYPE questionstate AS ENUM ('NOT_ASKED_ALOUD', 'CORRECTION', 'URGENT', 'NOT_A_QUESTION')"
        in upgrade_sql
    )
    assert upgrade_sql.count("CREATE INDEX") == _INDEX_COUNT
    assert "CREATE INDEX ix_report_participant_report_id" in upgrade_sql
    assert "CREATE INDEX ix_report_participant_speaker_id" in upgrade_sql
    assert "CREATE INDEX ix_report_question_state_report_id" in upgrade_sql
    assert (
        "CONSTRAINT uq_report_participant_report_id_ordinal UNIQUE (report_id, ordinal)"
        in upgrade_sql
    )
    assert (
        "CONSTRAINT uq_report_question_state_report_id_state UNIQUE (report_id, state)"
        in upgrade_sql
    )
    assert "ALTER TABLE" not in upgrade_sql
    assert "DROP" not in upgrade_sql
    for line in upgrade_sql.splitlines():
        if "UPDATE" in line:
            assert "alembic_version" in line


def test_question_number_call_migration_only_adds_the_enum_value() -> None:
    output = io.StringIO()
    command.upgrade(
        Config(str(_ALEMBIC_INI), output_buffer=output),
        "a4c8e1d27f93:287f3a4e2fdd",
        sql=True,
    )
    upgrade_sql = output.getvalue()

    assert (
        "ALTER TYPE participantrolesource ADD VALUE IF NOT EXISTS 'QUESTION_NUMBER_CALL'"
        in upgrade_sql
    )
    assert "CREATE" not in upgrade_sql
    assert "DROP" not in upgrade_sql

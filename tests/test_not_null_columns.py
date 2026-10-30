import uuid
from collections.abc import Iterator
from datetime import datetime
from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from exceptions import HansardTestGuardError
from settings import settings

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"
_DOWN_REVISION = "6b3a29f6f809"
_REVISION = "c5cea5c26a58"
_TEST_SCHEMA_PREFIX = "test_"
_TEST_SCHEMA_SUFFIX_LENGTH = 12
_VERSION_TABLE = "alembic_version"
_NOT_NULL_COLUMNS = frozenset({("sitting", "sitting_date"), ("speech", "report_id"), ("attendance", "sitting_id")})
_NULLABLE = "YES"
_NOT_NULLABLE = "NO"
_MODIFY_NULLABLE = "modify_nullable"
_TABLE_SCHEMA_STATEMENT = text("SELECT relnamespace::regnamespace::text FROM pg_class WHERE oid = to_regclass(:table_name)")
_COLUMN_NULLABILITY_STATEMENT = text(
    "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
    "WHERE table_schema = current_schema() "
    "AND (table_name, column_name) IN (('sitting', 'sitting_date'), ('speech', 'report_id'), ('attendance', 'sitting_id'))"
)


def test_sitting_without_a_date_is_refused(scratch_session: Session) -> None:
    with pytest.raises(IntegrityError, match='null value in column "sitting_date"'):
        scratch_session.execute(text("INSERT INTO sitting DEFAULT VALUES"))
    scratch_session.rollback()


def test_speech_without_a_report_is_refused(scratch_session: Session) -> None:
    statement = text("INSERT INTO speech (ordinal, transcript, sitting_date, report_type) VALUES (1, 'Text', :sitting_date, 'motion')")

    with pytest.raises(IntegrityError, match='null value in column "report_id"'):
        scratch_session.execute(statement, {"sitting_date": datetime(2025, 4, 2)})
    scratch_session.rollback()


def test_attendance_without_a_sitting_is_refused(scratch_session: Session) -> None:
    with pytest.raises(IntegrityError, match='null value in column "sitting_id"'):
        scratch_session.execute(text("INSERT INTO attendance DEFAULT VALUES"))
    scratch_session.rollback()


def _validate_can_migrate_schema(connection: Connection, schema: str) -> None:
    for table_name in (*(table.name for table in SQLModel.metadata.sorted_tables), _VERSION_TABLE):
        table_schema = connection.execute(_TABLE_SCHEMA_STATEMENT, {"table_name": table_name}).scalar_one_or_none()
        if table_schema != schema:
            raise HansardTestGuardError(f"Table {table_name} resolves to schema {table_schema}, not {schema}")


@pytest.fixture
def migration_connection() -> Iterator[Connection]:
    schema = f"{_TEST_SCHEMA_PREFIX}{uuid.uuid4().hex[:_TEST_SCHEMA_SUFFIX_LENGTH]}"
    admin_engine = create_engine(settings.database_url)
    with admin_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS rum"))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(settings.database_url, connect_args={"options": f"-csearch_path={schema},public"})
    try:
        # NOTE: a checked create sees public's tables through the search path and would create nothing
        SQLModel.metadata.create_all(engine, checkfirst=False)
        with engine.connect() as connection:
            connection.execute(text(
                f'CREATE TABLE "{schema}".{_VERSION_TABLE} '
                "(version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            ))
            _validate_can_migrate_schema(connection, schema)
            yield connection
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def _build_config(connection: Connection) -> Config:
    config = Config(str(_ALEMBIC_INI))
    config.attributes["connection"] = connection
    return config


def _get_column_nullability(connection: Connection) -> dict[tuple[str, str], str]:
    return {(table_name, column_name): is_nullable for table_name, column_name, is_nullable in connection.execute(_COLUMN_NULLABILITY_STATEMENT)}


def _collect_metadata_diffs(diffs: list, revision: object, migration_context: MigrationContext) -> list:
    diffs.extend(compare_metadata(migration_context, SQLModel.metadata))
    return []


def _get_nullable_diff_columns(config: Config) -> set[tuple[str, str]]:
    script_directory = ScriptDirectory.from_config(config)
    diffs: list = []
    with EnvironmentContext(config, script_directory, fn=partial(_collect_metadata_diffs, diffs)):
        script_directory.run_env()
    return {
        (table_name, column_name)
        for column_diffs in diffs
        if isinstance(column_diffs, list)
        for operation, _, table_name, column_name, *_ in column_diffs
        if operation == _MODIFY_NULLABLE
    }


def test_migration_sets_not_null_and_downgrade_drops_it(migration_connection: Connection) -> None:
    config = _build_config(migration_connection)
    command.stamp(config, _REVISION)

    command.downgrade(config, _DOWN_REVISION)

    assert _get_column_nullability(migration_connection) == dict.fromkeys(_NOT_NULL_COLUMNS, _NULLABLE)
    assert _get_nullable_diff_columns(config) == _NOT_NULL_COLUMNS

    command.upgrade(config, _REVISION)

    assert _get_column_nullability(migration_connection) == dict.fromkeys(_NOT_NULL_COLUMNS, _NOT_NULLABLE)
    assert _get_nullable_diff_columns(config) == set()

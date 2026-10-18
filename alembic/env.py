from logging.config import fileConfig
from typing import Optional

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import database.attendance  # noqa: F401
import database.hansard_sitting_date_response  # noqa: F401
import database.hansard_website_response  # noqa: F401
import database.party_affiliation  # noqa: F401
import database.person  # noqa: F401
import database.report  # noqa: F401
import database.sitting  # noqa: F401
import database.speaker  # noqa: F401
import database.speech  # noqa: F401
from alembic import context
from alembic.runtime.migration import MigrationContext
from settings import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# VARCHAR and TEXT are both variable-length strings in Postgres — treat as identical.
_TEXT_LIKE = (sa.TEXT, sa.VARCHAR, sqlmodel.sql.sqltypes.AutoString)


def _compare_type(
    context: MigrationContext,
    inspected_column: sa.Column,
    metadata_column: sa.Column,
    inspected_type: sa.types.TypeEngine,
    metadata_type: sa.types.TypeEngine,
) -> Optional[bool]:
    if isinstance(inspected_type, _TEXT_LIKE) and isinstance(metadata_type, _TEXT_LIKE):
        return False
    return None


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=_compare_type,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations_on(connection: sa.Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=_compare_type,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # NOTE: a caller that holds its own transaction passes the connection, and Alembic then neither begins nor commits
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_migrations_on(connection)
        return
    connectable = create_engine(settings.database_url)
    with connectable.connect() as connection:
        _run_migrations_on(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

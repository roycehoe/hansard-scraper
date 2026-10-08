from logging.config import fileConfig

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import database.attendance  # noqa: F401
import database.hansard_sitting_date_response  # noqa: F401
import database.hansard_website_response  # noqa: F401
import database.report  # noqa: F401
import database.sitting  # noqa: F401
import database.speaker  # noqa: F401
import database.speech  # noqa: F401
from alembic import context
from settings import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# VARCHAR and TEXT are both variable-length strings in Postgres — treat as identical.
_TEXT_LIKE = (sa.TEXT, sa.VARCHAR, sqlmodel.sql.sqltypes.AutoString)


def _compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
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


def run_migrations_online() -> None:
    connectable = create_engine(settings.database_url)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=_compare_type,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

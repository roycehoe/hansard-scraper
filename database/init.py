from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from alembic import command
from alembic.config import Config
from settings import settings

_KEEPALIVE_CONNECT_ARGS = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 6,
}
_READ_ONLY_CONNECT_OPTIONS = "-c default_transaction_read_only=on"

engine = create_engine(
    url=settings.database_url, pool_pre_ping=True, connect_args=_KEEPALIVE_CONNECT_ARGS
)

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def build_read_only_engine(database_url: str) -> Engine:
    # NOTE: the connect option is a second guard beside the read only execution option
    return create_engine(
        url=database_url,
        pool_pre_ping=True,
        connect_args={
            **_KEEPALIVE_CONNECT_ARGS,
            "options": _READ_ONLY_CONNECT_OPTIONS,
        },
    ).execution_options(postgresql_readonly=True)


def create_db_and_tables() -> None:
    alembic_config = Config(str(_ALEMBIC_INI))
    command.upgrade(alembic_config, "head")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

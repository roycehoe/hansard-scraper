from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, create_engine

from alembic import command
from alembic.config import Config
from settings import settings

_KEEPALIVE_CONNECT_ARGS = {"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 6}

engine = create_engine(url=settings.database_url, pool_pre_ping=True, connect_args=_KEEPALIVE_CONNECT_ARGS)

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def create_db_and_tables() -> None:
    alembic_config = Config(str(_ALEMBIC_INI))
    command.upgrade(alembic_config, "head")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

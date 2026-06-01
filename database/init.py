from pathlib import Path

from sqlmodel import Session, create_engine

from alembic import command
from alembic.config import Config
from settings import settings

engine = create_engine(url=settings.database_url)

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def create_db_and_tables() -> None:
    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")


def get_session():
    with Session(engine) as session:
        yield session

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

import database.handsard_sitting_date_response  # noqa: F401
import database.handsard_website_response  # noqa: F401
import database.mp  # noqa: F401
import database.parsing_statistics  # noqa: F401
import database.report  # noqa: F401
import database.sitting  # noqa: F401
import database.sitting_a2b  # noqa: F401
import database.sitting_annexure  # noqa: F401
import database.sitting_attendance  # noqa: F401
import database.sitting_ptba  # noqa: F401
import database.sitting_section  # noqa: F401
import database.sitting_vernacular  # noqa: F401
import database.speech  # noqa: F401
from settings import settings

engine = create_engine(url=settings.database_url)

_MP_ID_MIGRATIONS = [
    "ALTER TABLE speech ADD COLUMN IF NOT EXISTS mp_id INTEGER REFERENCES mp(id)",
    "ALTER TABLE sittingattendance ADD COLUMN IF NOT EXISTS mp_id INTEGER REFERENCES mp(id)",
]


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    # create_all() only creates missing tables; ALTER TABLE is required for columns
    # added after the tables were first created.
    with Session(engine) as session:
        for stmt in _MP_ID_MIGRATIONS:
            session.execute(text(stmt))
        session.commit()


def get_session():
    with Session(engine) as session:
        yield session

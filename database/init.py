from dotenv import dotenv_values
from sqlmodel import Session, SQLModel, create_engine

import database.handsard_sitting_date_response  # noqa: F401
import database.handsard_website_response  # noqa: F401
import database.parsing_statistics  # noqa: F401
import database.report  # noqa: F401
import database.speech  # noqa: F401

DATABASE_URL = (
    dotenv_values().get("DATABASE_URL")
    or "postgresql://user:password@localhost:5432/postgres"
)

engine = create_engine(url=DATABASE_URL)


def create_db_and_tables():
    SQLModel.metadata.create_all(
        engine,
    )


def get_session():
    with Session(engine) as session:
        yield session

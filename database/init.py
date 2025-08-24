from dotenv import dotenv_values
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = (
    dotenv_values().get("DATABASE_URL")
    or "postgresql://user:password@localhost:5432/postgres"
)

engine = create_engine(url=DATABASE_URL, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(
        engine,
    )


def get_session():
    with Session(engine) as session:
        yield session

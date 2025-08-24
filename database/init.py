from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = "postgresql://user:password@localhost:5432/postgres"

engine = create_engine(url=DATABASE_URL, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(
        engine,
    )


def get_session():
    with Session(engine) as session:
        yield session

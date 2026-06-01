from sqlalchemy import Integer as _SAInteger
from sqlalchemy import inspect, text
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


def _apply_schema_migrations() -> None:
    """
    Apply column-level migrations that SQLModel create_all() cannot handle
    (it only creates missing tables, not missing columns on existing tables).
    All statements are idempotent.
    """
    insp = inspect(engine)
    with Session(engine) as session:
        # ── handsardsittingdateresponse ───────────────────────────────────
        # 'parl_no' was renamed to 'parlement_no' in the model.
        hdsr_cols = {c["name"] for c in insp.get_columns("handsardsittingdateresponse")}
        if "parl_no" in hdsr_cols and "parlement_no" not in hdsr_cols:
            session.execute(text(
                "ALTER TABLE handsardsittingdateresponse RENAME COLUMN parl_no TO parlement_no"
            ))
            hdsr_cols = (hdsr_cols - {"parl_no"}) | {"parlement_no"}

        for col in SQLModel.metadata.tables["handsardsittingdateresponse"].columns:
            if col.name == "id" or col.name in hdsr_cols:
                continue
            sql_type = "INTEGER" if isinstance(col.type, _SAInteger) else "TEXT"
            session.execute(text(
                f"ALTER TABLE handsardsittingdateresponse"
                f" ADD COLUMN IF NOT EXISTS {col.name} {sql_type}"
            ))

        # ── speech / sittingattendance — mp_id FK added after table creation ─
        session.execute(text(
            "ALTER TABLE speech"
            " ADD COLUMN IF NOT EXISTS mp_id INTEGER REFERENCES mp(id)"
        ))
        session.execute(text(
            "ALTER TABLE sittingattendance"
            " ADD COLUMN IF NOT EXISTS mp_id INTEGER REFERENCES mp(id)"
        ))

        session.commit()


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _apply_schema_migrations()


def get_session():
    with Session(engine) as session:
        yield session

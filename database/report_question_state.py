from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.speech  # noqa: F401 registers Report and Speech so the foreign key resolves
from enums import QuestionState


class ReportQuestionState(SQLModel, table=True):
    __tablename__ = "report_question_state"
    __table_args__ = (
        UniqueConstraint(
            "report_id", "state", name="uq_report_question_state_report_id_state"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    state: QuestionState
    printed_text: str
    first_ordinal: Optional[int] = None

    report_id: int = Field(foreign_key="report.id", index=True)

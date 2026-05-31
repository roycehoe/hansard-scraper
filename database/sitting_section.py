from typing import Optional

from sqlmodel import Field, SQLModel


class SittingSection(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sitting_id: int | None = Field(default=None, foreign_key="handsardsittingdateresponse.id")

    start_pg_no: Optional[int] = None
    end_pg_no: Optional[int] = None
    title: Optional[str] = None
    sub_title: Optional[str] = None
    section_type: Optional[str] = None
    content: Optional[str] = None
    clarification_text: Optional[str] = None
    clarification_title: Optional[str] = None
    clarification_sub_title: Optional[str] = None
    report_type: Optional[str] = None
    question_count: Optional[str] = None
    foot_notes: Optional[str] = None
    foot_note_questions: Optional[str] = None
    question_no: Optional[str] = None

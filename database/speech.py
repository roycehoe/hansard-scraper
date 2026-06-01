from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from database.report import Report


class Speech(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    speaker: Optional[str]
    transcript: str

    report_id: Optional[int] = Field(default=None, foreign_key="report.id")
    report: Report = Relationship(back_populates="speeches")
    mp_id: Optional[int] = Field(default=None, foreign_key="mp.id")

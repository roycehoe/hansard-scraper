from sqlmodel import Field, Relationship, SQLModel

from database.report import Report


class Speech(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    ordinal: int
    speaker: str | None
    transcript: str

    report_id: int | None = Field(default=None, foreign_key="report.id")
    report: Report = Relationship(back_populates="speeches")

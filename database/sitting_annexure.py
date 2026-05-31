from typing import Optional

from sqlmodel import Field, SQLModel


class SittingAnnexure(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sitting_id: int | None = Field(default=None, foreign_key="handsardsittingdateresponse.id")

    annexure_id: Optional[int] = None
    sitting_date: Optional[str] = None
    annexure_title: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    section_type: Optional[str] = None
    file: Optional[str] = None

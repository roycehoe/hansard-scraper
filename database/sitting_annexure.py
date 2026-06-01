from typing import Optional

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from sqlmodel import Field, SQLModel


class SittingAnnexure(SQLModel, table=True):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: Optional[int] = Field(default=None, primary_key=True)
    sitting_id: Optional[int] = Field(default=None, foreign_key="handsardsittingdateresponse.id")

    annexure_id: Optional[int] = Field(default=None, alias="annexureID")
    sitting_date: Optional[str] = None
    annexure_title: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    section_type: Optional[str] = None
    file: Optional[str] = None

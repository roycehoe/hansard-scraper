from typing import Optional

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from sqlmodel import Field, SQLModel


class SittingA2b(SQLModel, table=True):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: int | None = Field(default=None, primary_key=True)
    sitting_id: int | None = Field(default=None, foreign_key="handsardsittingdateresponse.id")

    date: Optional[str] = None
    bill: Optional[str] = None
    atbp_preview_text: Optional[str] = None

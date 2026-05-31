from typing import Optional

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from sqlmodel import Field, SQLModel


class SittingPtba(SQLModel, table=True):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: int | None = Field(default=None, primary_key=True)
    sitting_id: int | None = Field(default=None, foreign_key="handsardsittingdateresponse.id")

    mp_name: Optional[str] = None
    from_date: Optional[str] = Field(default=None, alias="from")
    to_date: Optional[str] = Field(default=None, alias="to")
    start_dt_text: Optional[str] = None
    end_dt_text: Optional[str] = None
    start_dt_flag: Optional[bool] = None
    end_dt_flag: Optional[bool] = None

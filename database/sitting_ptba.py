from typing import Optional

from sqlmodel import Field, SQLModel


class SittingPtba(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sitting_id: int | None = Field(default=None, foreign_key="handsardsittingdateresponse.id")

    mp_name: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    start_dt_text: Optional[str] = None
    end_dt_text: Optional[str] = None
    start_dt_flag: Optional[bool] = None
    end_dt_flag: Optional[bool] = None

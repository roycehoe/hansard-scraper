from datetime import date

from pydantic import BaseModel, ConfigDict, Field, RootModel


class OfficeCheckMinister(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    member_name: str
    speaker_ids: list[int]
    ministry_name: str
    start_date: date
    end_date: date
    source_url: str = Field(pattern=r"^https://")


class OfficeCheckMinisters(RootModel[list[OfficeCheckMinister]]):
    model_config = ConfigDict(frozen=True)

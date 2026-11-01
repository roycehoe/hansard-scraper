from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel

from enums import HandCheckFormOfAddress


class HandCheckOfficeHolder(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    office: str
    holder: str
    form_of_address: HandCheckFormOfAddress
    first_day: date
    last_day: Optional[date]
    source_url: str


class HandCheckOfficeHolders(RootModel[list[HandCheckOfficeHolder]]):
    model_config = ConfigDict(frozen=True)

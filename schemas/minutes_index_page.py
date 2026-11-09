from typing import Optional

from pydantic import BaseModel, ConfigDict


class LiveMinutesFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    filename_download: str
    type: str


class LiveMinutesParliament(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str


class LiveMinutesRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str
    date: str
    report: LiveMinutesFile
    parliaments: Optional[LiveMinutesParliament]


class LiveMinutesIndex(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: list[LiveMinutesRow]

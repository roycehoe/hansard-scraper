from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel

from enums import EgazetteSupplementKind


class EgazetteFetchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    year: int
    supplement_kind: EgazetteSupplementKind
    number: int
    status_code: int
    fetched_at: datetime
    file_path: Optional[str]
    size_bytes: Optional[int]
    sha256: Optional[str]


class EgazetteFetchRecords(RootModel[list[EgazetteFetchRecord]]):
    model_config = ConfigDict(frozen=True)

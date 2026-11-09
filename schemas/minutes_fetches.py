from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel


class MinutesFetchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file_url: str
    request_url: str
    archive_timestamp: Optional[str]
    status_code: int
    size_bytes: int
    sha256: str
    file_name: Optional[str]
    fetched_at: datetime
    is_signature_passed: bool


class MinutesFetches(RootModel[list[MinutesFetchRecord]]):
    model_config = ConfigDict(frozen=True)

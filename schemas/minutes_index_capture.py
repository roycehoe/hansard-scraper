from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel


class MinutesIndexCaptureManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page: Optional[int]
    archive_timestamp: Optional[str]
    original_url: str
    capture_url: str
    file: str
    size: int


class MinutesIndexCaptureManifest(RootModel[list[MinutesIndexCaptureManifestEntry]]):
    model_config = ConfigDict(frozen=True)

from pydantic import BaseModel, ConfigDict, RootModel


class ActsSupplementCaptureManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file_name: str
    original_url: str
    archive_timestamp: str
    capture_url: str


class ActsSupplementCaptureManifest(
    RootModel[list[ActsSupplementCaptureManifestEntry]]
):
    model_config = ConfigDict(frozen=True)

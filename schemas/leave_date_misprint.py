from pydantic import BaseModel, ConfigDict, RootModel


class LeaveDateMisprint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    printed: str
    reading: str
    reason: str


class LeaveDateMisprints(RootModel[list[LeaveDateMisprint]]):
    model_config = ConfigDict(frozen=True)

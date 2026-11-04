from pydantic import BaseModel, ConfigDict, RootModel


class HandKeptActLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sso_code: str
    ordinal: int
    printed_title: str
    report_ids: list[int]
    reason: str


class HandKeptActLinks(RootModel[list[HandKeptActLink]]):
    model_config = ConfigDict(frozen=True)

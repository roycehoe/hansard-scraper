from pydantic import BaseModel, ConfigDict, RootModel


class HarvestedAct(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sso_code: str
    title: str


class HarvestedActs(RootModel[list[HarvestedAct]]):
    model_config = ConfigDict(frozen=True)

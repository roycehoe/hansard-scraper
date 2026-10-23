from pydantic import BaseModel, ConfigDict, RootModel


class HeadOfStateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    parliament_number: int
    comments: str


class HeadsOfState(RootModel[list[HeadOfStateResult]]):
    model_config = ConfigDict(frozen=True)

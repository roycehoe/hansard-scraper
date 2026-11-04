from pydantic import BaseModel, ConfigDict, RootModel


class HandKeptBill(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    report_ids: list[int]
    reason: str


class HandKeptBills(RootModel[list[HandKeptBill]]):
    model_config = ConfigDict(frozen=True)

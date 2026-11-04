from pydantic import BaseModel, ConfigDict, RootModel


class BillTitleCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: int
    printed_title: str
    corrected_title: str
    reason: str


class BillTitleCorrections(RootModel[list[BillTitleCorrection]]):
    model_config = ConfigDict(frozen=True)

from pydantic import BaseModel, ConfigDict, RootModel


class ReportLinkTitleCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    printed_title: str
    corrected_title: str
    reason: str


class ReportLinkTitleCorrections(RootModel[list[ReportLinkTitleCorrection]]):
    model_config = ConfigDict(frozen=True)

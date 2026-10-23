from pydantic import BaseModel, ConfigDict, RootModel


class ExcludedReportId(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    kept_report_id: str
    reason: str


class ExcludedReportIds(RootModel[list[ExcludedReportId]]):
    model_config = ConfigDict(frozen=True)

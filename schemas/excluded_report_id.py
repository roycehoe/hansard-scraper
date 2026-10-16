from pydantic import BaseModel


class ExcludedReportId(BaseModel):
    report_id: str
    kept_report_id: str
    reason: str

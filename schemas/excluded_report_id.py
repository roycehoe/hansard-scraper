from pydantic import BaseModel


class ExcludedReportId(BaseModel):
    report_id: str
    reason: str

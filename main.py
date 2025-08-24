import json
from datetime import date, datetime
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, Field, field_validator

import parliament_report
from parliament_report_parser import parse_parliament_report

with open("parliament_reports.json", "r") as f:
    parliament_reports = json.load(f)

parsed_report = parse_parliament_report(parliament_reports)

with open("parsed_parliament_reports.json", "w") as f:
    json.dump(parsed_report, f, default=str)


EmptyStrNoneInt = Annotated[
    Optional[int],
    BeforeValidator(lambda v: None if isinstance(v, str) and v.strip() == "" else v),
]


class Report(BaseModel):
    volume_number: int = Field(alias="volumeNo")
    parliament_number: int = Field(alias="parlNo")
    sitting_number: EmptyStrNoneInt = Field(None, alias="sittingNo")
    sitting_date: datetime = Field(alias="sittingDate")
    speech_number: int = Field(alias="sno")

    title: str
    subtitle: Optional[str] = None
    # Can be used to obtain raw report via request params
    report_id: str = Field(alias="reportId")
    report_type: str = Field(alias="reportType")

    column_start: Optional[str] = Field(None, alias="columnStart")
    column_end: Optional[str] = Field(None, alias="columnEnd")
    html_file_name: Optional[str] = Field(None, alias="htmlFileName")

    report_version: str = Field(alias="reportVersion")


with open("parsed_parliament_reports.json", "r") as f:
    parliament_reports = json.load(f)

# [Report(**i) for i in parliament_reports]


print([Report(**i).speech_number for i in parliament_reports])

import json

from parliament_report_parser import get_parliament_reports_without_unused_fields

with open("parsed_parliament_reports.json", "r") as f:
    parliament_reports = json.load(f)

with open("parsed_parliament_reports_v1.json", "w") as f:
    parsed_parliament_reports = get_parliament_reports_without_unused_fields(
        parliament_reports
    )
    json.dump(parsed_parliament_reports, f)

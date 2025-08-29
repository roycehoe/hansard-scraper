import json
from typing import Optional

from database.report import Report
from utils.sample import get_strata_sample


def get_start_of_speech_line(
    markdown_content: str, title: str, subtitle: Optional[str], id: int
) -> Optional[int]:
    for line_index, line in enumerate(markdown_content.splitlines()):
        if subtitle and subtitle in line:
            return line_index
        if title in line:
            return line_index
    print(id)
    return None


# sample = get_strata_sample()
#
# with open("sample.json", "w") as json_data:
#     data = json.dump([i.model_dump() for i in sample], json_data, default=str)

with open("sample.json") as json_data:
    data = json.load(json_data)

reports = [Report(**i) for i in data]
for report in reports:
    if report.markdown_content:
        get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.id
        )

# report = [Report(**i) for i in data if i["id"] == 24854][0]
# get_start_of_speech_line(
#     report.markdown_content, report.title, report.subtitle, report.id
# )

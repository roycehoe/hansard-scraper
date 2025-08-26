import json
import random
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from sqlmodel import select

from database.init import create_db_and_tables, get_session
from database.report import Report
from enums import ReportType
from markdown_parser import get_cleaned_handsard_markdown


def get_mps_speaking(report: Report) -> Optional[str]:
    flag = False
    if report.markdown_content is None:
        return None
    if report.content is None:
        return None
    for line in report.markdown_content.splitlines():
        if line.startswith("MPs Speaking:|"):
            return line

    soup = BeautifulSoup(report.content, "html.parser")
    meta = soup.find("meta", {"name": "MP_Speak"})
    if meta is None:
        return None
    if meta.get("content") is None:
        return None
    return meta.get("content")


# def get_strata_sample():
#     session = next(get_session())
#     strata_sample: list[Report] = []
#     MAX_PARLIAMENT_NUMBER = 12
#     for parliament_number in range(MAX_PARLIAMENT_NUMBER):
#         for report_type_enum in ReportType:
#             sample = session.exec(
#                 select(Report)
#                 .where(Report.sitting_date < datetime(2012, 9, 10, 0, 0, 0, 0))
#                 .where(Report.content != None)
#                 .where(Report.report_type == report_type_enum.value)
#                 .where(Report.sitting_number == parliament_number)
#             ).first()
#             if sample is None:
#                 continue
#             strata_sample.append(sample)
#     return strata_sample
#
#
# sample = get_strata_sample()
# with open("sample.json", "w") as f:
#     data = json.dump([i.model_dump() for i in sample], f, default=str)
#
#

# with open("sample.json") as f:
#     data = json.load(f)
# reports = [Report(**i) for i in data]
#
#
# def get_start_of_speech_line(
#     markdown_content: str, title: str, subtitle: Optional[str], id: int
# ) -> Optional[int]:
#     for i, line in enumerate(markdown_content.splitlines()):
#         if subtitle:
#             if subtitle in line:
#                 return i
#         if title in line:
#             return i
#     print(id)
#     return None
#
#
# output = [
#     get_start_of_speech_line(i.markdown_content, i.title, i.subtitle, i.id)
#     for i in reports
# ]
#
#
# print(output)

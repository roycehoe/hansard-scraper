import json
from datetime import date, datetime
from typing import Annotated, Optional

import requests
from pydantic import BaseModel, BeforeValidator, Field
from sqlmodel import select

from database.init import create_db_and_tables, get_session
from database.report import Report

with open("parsed_parliament_reports.json", "r") as f:
    parliament_reports = json.load(f)

URL = "https://sprs.parl.gov.sg/search/getHansardTopic/?id="


def get_topic_html_content(report_id: str) -> dict:
    response = requests.post(url=f"{URL}{report_id}")
    return response.json()


session = next(get_session())

all_reports = session.exec(
    select(Report)
    .where(Report.sitting_date < datetime(2012, 9, 10, 0, 0, 0, 0))
    .where(Report.content == None)
).all()

for report in all_reports:
    print(report.id)
    response = get_topic_html_content(
        report.html_file_name if report.html_file_name is not None else report.report_id
    )
    print(response)
    # html_content = response.get("htmlContent")
    # print(html_content)
    # report.content = html_content.replace("\x00", "\uFFFD")
    # session.add(report)
    # session.commit()

# for report in all_reports:
#     try:
#         response = get_topic_html_content(
#             report.html_file_name
#             if report.html_file_name is not None
#             else report.report_id
#         )
#         html_content = response.get("htmlContent")
#         print(html_content)
#         report.content = html_content.replace("\x00", "\uFFFD")
#         session.add(report)
#         session.commit()
#     except Exception as e:
#         print(e)

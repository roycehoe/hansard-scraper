from datetime import datetime

from sqlmodel import select

from database.init import create_db_and_tables, get_session
from database.report import Report
from markdown_parser import get_cleaned_handsard_markdown

create_db_and_tables()
session = next(get_session())
all_reports = session.exec(
    select(Report)
    .where(Report.sitting_date < datetime(2012, 9, 10, 0, 0, 0, 0))
    .where(Report.content != None)
).all()


for report in all_reports:
    try:
        if report.content is None:
            continue
        markdown_content = get_cleaned_handsard_markdown(report.content)
        report.markdown_content = markdown_content
        session.add(report)
        session.commit()
    except Exception as e:
        print(e)

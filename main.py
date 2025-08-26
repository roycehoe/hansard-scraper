from datetime import datetime

from sqlmodel import select

from database.init import get_session
from database.report import Report
from parliament_topic import get_handsard_topic_response

session = next(get_session())
all_reports = session.exec(
    select(Report)
    .where(Report.sitting_date < datetime(2012, 9, 10, 0, 0, 0, 0))
    .where(Report.content == None)
    .where(Report.report_id != None and Report.html_file_name != None)
).all()


for report in all_reports:
    try:
        response = get_handsard_topic_response(
            report.html_file_name
            if report.html_file_name is not None
            else report.report_id
        )
        html_content = response.get("htmlContent")
        report.content = html_content.replace("\x00", "\ufffd")
        session.add(report)
        session.commit()
    except Exception as e:
        print(e)

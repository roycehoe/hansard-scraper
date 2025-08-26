from datetime import datetime

from sqlmodel import select

from database.init import get_session
from database.report import Report
from services import get_db_report_content_in

session = next(get_session())
all_reports = session.exec(
    select(Report)
    .where(Report.sitting_date < datetime(2012, 9, 10, 0, 0, 0, 0))
    .where(Report.content == None)
    .where(Report.report_id != None and Report.html_file_name != None)
).all()


for report in all_reports:
    try:
        get_db_report_content_in(report)
        session.add(report)
        session.commit()
    except Exception as e:
        print(e)

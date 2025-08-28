from datetime import datetime

from sqlmodel import or_, select

from database.init import create_db_and_tables, get_session
from database.report import Report
from handsard_search_result import get_all_handsard_search_results
from schemas import HandsardSearchResult
from services import get_cleaned_db_report_in, get_db_report_in

create_db_and_tables()

all_handsard_search_results = [
    HandsardSearchResult(**result) for result in get_all_handsard_search_results()
]
handsard_reports_in = [
    get_db_report_in(result) for result in all_handsard_search_results
]


session = next(get_session())
for handsard_report_in in handsard_reports_in:
    session.add(handsard_report_in)
session.commit()
handsard_reports_in = session.exec(
    select(Report).where(Report.sitting_date < datetime(2012, 9, 10, 0, 0, 0, 0))
).all()

cleaned_handsard_reports = [
    get_cleaned_db_report_in(handsard_report) for handsard_report in handsard_reports_in
]
for cleaned_handsard_report in cleaned_handsard_reports:
    session.add(cleaned_handsard_report)
session.commit()

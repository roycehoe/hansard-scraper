from sqlmodel import select

from database.init import create_db_and_tables, get_session
from database.report import Report
from gateway.handsard_search import get_all_handsard_search_results
from schemas import HandsardSearchResult
from services.report import get_db_report_in

create_db_and_tables()

all_handsard_search_results = [
    HandsardSearchResult(**result) for result in get_all_handsard_search_results()
]
handsard_reports_in = []

for i, result in enumerate(all_handsard_search_results):
    print(f"reports in: {i}/{len(all_handsard_search_results)}")
    handsard_reports_in.append(get_db_report_in(result))


session = next(get_session())
for handsard_report_in in handsard_reports_in:
    session.add(handsard_report_in)
session.commit()

handsard_reports_in = session.exec(select(Report).where(Report.subtitle is not None))
for handsard_report_in in handsard_reports_in:
    handsard_report_in.title = handsard_report_in.title.strip()
    if handsard_report_in.subtitle is not None:
        handsard_report_in.subtitle = handsard_report_in.subtitle.strip()
    session.add(handsard_report_in)
session.commit()

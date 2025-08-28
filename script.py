from database.init import create_db_and_tables, get_session
from gateway.handsard_search import get_all_handsard_search_results
from schemas import HandsardSearchResult
from services.report import get_db_report_in

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
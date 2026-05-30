from sqlmodel import Session

from gateway.handsard_search import get_all_handsard_search_results
from schemas import HandsardSearchResult
from services.handsard_website import get_handsard_website_result_in


def populate_handsard_responses(session: Session):
    all_search_results = [
        HandsardSearchResult(**r) for r in get_all_handsard_search_results()
    ]
    for i, result in enumerate(all_search_results, start=1):
        print(f"{i}/{len(all_search_results)}")
        session.add(get_handsard_website_result_in(result))
    session.commit()

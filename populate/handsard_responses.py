from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from gateway.handsard_search import get_all_handsard_search_results
from logs import logger
from schemas.handsard_search_result import HandsardSearchResult
from services.handsard_website import build_handsard_website_response


def populate_handsard_responses(session: Session):
    all_search_results = [HandsardSearchResult(**r) for r in get_all_handsard_search_results()]
    crud = CRUDHandsardWebsiteResponse(session)
    for i, result in enumerate(all_search_results, start=1):
        logger.info(f"{i}/{len(all_search_results)}")
        crud.create(build_handsard_website_response(result))

from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from gateway.handsard_search import get_all_handsard_search_results
from logs import logger
from schemas.handsard_search_result import HandsardSearchResult
from services.handsard_website import build_handsard_website_response


def populate_handsard_responses(session: Session):
    all_search_results = [HandsardSearchResult(**r) for r in get_all_handsard_search_results()]
    crud = CRUDHandsardWebsiteResponse(session)
    existing_ids = crud.get_all_report_ids()
    to_fetch = [r for r in all_search_results if r.report_id not in existing_ids]
    logger.info(f"Fetching {len(to_fetch)}/{len(all_search_results)} ({len(existing_ids)} already in DB)")
    for i, result in enumerate(to_fetch, start=1):
        logger.info(f"{i}/{len(to_fetch)}")
        crud.create(build_handsard_website_response(result))

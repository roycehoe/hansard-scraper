import asyncio
from typing import Optional

import httpx
from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from exceptions import HansardGatewayError
from gateway.handsard_search import get_all_handsard_search_results
from gateway.handsard_topic import get_handsard_topic_response_async
from logs import logger
from schemas.handsard_search_result import HandsardSearchResult
from services.handsard_website import build_handsard_website_response

_CONCURRENCY = 20


async def _fetch_html_content(
    result: HandsardSearchResult,
    client: httpx.AsyncClient,
) -> Optional[str]:
    try:
        response = await get_handsard_topic_response_async(
            result.html_file_name or result.report_id,
            client,
        )
    except HansardGatewayError as e:
        logger.warning(f"No content for {result.report_id}: {e}")
        return None
    html_content = response.get("htmlContent")
    if html_content is None:
        return None
    return html_content.replace("\x00", "�")


async def _fetch_all(results: list[HandsardSearchResult]) -> list:
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    completed = 0
    total = len(results)

    async with httpx.AsyncClient(timeout=30) as client:
        async def fetch_one(result):
            nonlocal completed
            async with semaphore:
                content = await _fetch_html_content(result, client)
                response = build_handsard_website_response(result, content)
            completed += 1
            logger.info(f"{completed}/{total}")
            return response

        return await asyncio.gather(*[fetch_one(r) for r in results])


def populate_handsard_responses(session: Session):
    all_search_results = [HandsardSearchResult(**r) for r in get_all_handsard_search_results()]
    crud = CRUDHandsardWebsiteResponse(session)
    existing_ids = crud.get_all_report_ids()
    to_fetch = [r for r in all_search_results if r.report_id not in existing_ids]
    logger.info(f"Fetching {len(to_fetch)}/{len(all_search_results)} ({len(existing_ids)} already in DB)")

    responses = asyncio.run(_fetch_all(to_fetch))
    crud.create_many(responses)

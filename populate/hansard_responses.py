import asyncio
from typing import Optional

import httpx
from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from exceptions import HansardGatewayError
from gateway.hansard_search import get_all_hansard_search_results
from gateway.hansard_topic import get_hansard_topic_response_async
from logs import logger
from schemas.hansard_search_result import HansardSearchResult
from services.hansard_website import build_hansard_website_response

_CONCURRENCY = 20


async def _fetch_html_content(
    result: HansardSearchResult,
    client: httpx.AsyncClient,
) -> Optional[str]:
    try:
        response = await get_hansard_topic_response_async(
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


async def _fetch_all(results: list[HansardSearchResult]) -> list:
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    completed = 0
    total = len(results)

    async with httpx.AsyncClient(timeout=30) as client:
        async def fetch_one(result):
            nonlocal completed
            async with semaphore:
                content = await _fetch_html_content(result, client)
                response = build_hansard_website_response(result, content)
            completed += 1
            logger.info(f"{completed}/{total}")
            return response

        return await asyncio.gather(*[fetch_one(r) for r in results])


def populate_hansard_responses(session: Session):
    all_search_results = [HansardSearchResult(**r) for r in get_all_hansard_search_results()]
    crud = CRUDHansardWebsiteResponse(session)
    existing_ids = crud.get_all_report_ids()
    to_fetch = [r for r in all_search_results if r.report_id not in existing_ids]
    logger.info(f"Fetching {len(to_fetch)}/{len(all_search_results)} ({len(existing_ids)} already in DB)")

    responses = asyncio.run(_fetch_all(to_fetch))
    crud.create_many(responses)

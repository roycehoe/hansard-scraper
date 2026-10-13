import asyncio
import itertools
from collections.abc import Iterator
from typing import Optional

import httpx
from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from database.hansard_website_response import HansardWebsiteResponse
from exceptions import HansardGatewayError
from gateway.hansard_search import get_all_hansard_search_results
from gateway.hansard_topic import get_hansard_topic_response_async
from logs import logger
from schemas.hansard_search_result import HansardSearchResult
from services.hansard_website import build_hansard_website_response

_CONCURRENCY = 20
_HTTP_TIMEOUT_SECONDS = 30


async def _fetch_html_content(
    search_result: HansardSearchResult,
    client: httpx.AsyncClient,
) -> Optional[str]:
    try:
        hansard_topic_response = await get_hansard_topic_response_async(
            search_result.html_file_name or search_result.report_id,
            client,
        )
    except HansardGatewayError as error:
        logger.warning(f"No content for {search_result.report_id}: {error}")
        return None
    html_content = hansard_topic_response.html_content
    if html_content is None:
        return None
    return html_content.replace("\x00", "�")


async def _fetch_website_response(
    search_result: HansardSearchResult,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    progress: Iterator[int],
    total: int,
) -> HansardWebsiteResponse:
    async with semaphore:
        html_content = await _fetch_html_content(search_result, client)
        hansard_website_response = build_hansard_website_response(search_result, html_content)
    completed = next(progress)
    logger.info(f"{completed}/{total}")
    return hansard_website_response


async def _fetch_all(search_results: list[HansardSearchResult]) -> list[HansardWebsiteResponse]:
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    progress = itertools.count(1)
    total = len(search_results)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        return await asyncio.gather(
            *[_fetch_website_response(search_result, client, semaphore, progress, total) for search_result in search_results]
        )


def populate_hansard_responses(session: Session) -> None:
    all_search_results = get_all_hansard_search_results()
    existing_report_ids = CRUDHansardWebsiteResponse(session).get_all_report_ids()
    # NOTE: the search can return one hit twice, so keep the first hit per report_id.
    report_id_to_first_search_result = {}
    for search_result in all_search_results:
        report_id_to_first_search_result.setdefault(search_result.report_id, search_result)
    search_results_to_fetch = [search_result for search_result in report_id_to_first_search_result.values() if search_result.report_id not in existing_report_ids]
    logger.info(f"Fetching {len(search_results_to_fetch)}/{len(all_search_results)} ({len(existing_report_ids)} already in DB)")

    hansard_website_responses = asyncio.run(_fetch_all(search_results_to_fetch))
    CRUDHansardWebsiteResponse(session).create_many(hansard_website_responses)

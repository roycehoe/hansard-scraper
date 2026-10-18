import asyncio
from typing import Optional

import httpx
from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from database.hansard_website_response import HansardWebsiteResponse
from enums import ReportType, ReportVersion
from exceptions import HansardGatewayError
from gateway.hansard_topic import get_hansard_topic_response_async
from logs import logger
from services.hansard_website import get_topic_html_content, get_topic_id
from settings import settings
from utils.sitting_dates import parse_sitting_date

_BATCH_SIZE = 200
_HTTP_TIMEOUT_SECONDS = 60


async def _fetch_content(
    hansard_website_response: HansardWebsiteResponse,
    client: httpx.AsyncClient,
) -> Optional[str]:
    try:
        hansard_topic_response = await get_hansard_topic_response_async(
            get_topic_id(
                hansard_website_response.report_id,
                hansard_website_response.html_file_name,
                hansard_website_response.report_version,
            ),
            client,
        )
    except HansardGatewayError as error:
        logger.warning(f"No content for {hansard_website_response.report_id}: {error}")
        return None
    content = get_topic_html_content(hansard_topic_response, hansard_website_response.report_version)
    if content is None:
        logger.warning(f"No content for {hansard_website_response.report_id}: the response holds no text")
    return content


async def _fetch_all_contents(hansard_website_responses: list[HansardWebsiteResponse]) -> list[Optional[str]]:
    contents: list[Optional[str]] = []

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        for start in range(0, len(hansard_website_responses), _BATCH_SIZE):
            batch = hansard_website_responses[start : start + _BATCH_SIZE]
            contents.extend(await asyncio.gather(*[_fetch_content(response, client) for response in batch]))
    return contents


def populate_hansard_response_contents(session: Session) -> None:
    hansard_website_responses = CRUDHansardWebsiteResponse(session).get_by_content_null_and_report_version(ReportVersion.SPRS3)
    # NOTE: duplicate rows share a report_id, and set_content_by_report_id fills all of them from one fetch.
    report_id_to_first_response: dict[str, HansardWebsiteResponse] = {}
    for hansard_website_response in hansard_website_responses:
        if hansard_website_response.report_type == ReportType.ATBP:
            continue
        if parse_sitting_date(hansard_website_response.sitting_date).date() > settings.search_to_date:
            continue
        report_id_to_first_response.setdefault(hansard_website_response.report_id, hansard_website_response)
    responses_to_fetch = list(report_id_to_first_response.values())
    logger.info(f"Fetching {len(responses_to_fetch)}/{len(hansard_website_responses)} rows without content")

    contents = asyncio.run(_fetch_all_contents(responses_to_fetch))

    filled = 0
    failed = 0
    for i, (hansard_website_response, content) in enumerate(zip(responses_to_fetch, contents), start=1):
        if content is None:
            failed += 1
            continue
        logger.info(f"{i}/{len(responses_to_fetch)}: {hansard_website_response.report_id}")
        CRUDHansardWebsiteResponse(session).set_content_by_report_id(hansard_website_response.report_id, content)
        filled += 1
    session.commit()
    logger.info(f"Hansard response contents: {filled} ids filled, {failed} ids failed")

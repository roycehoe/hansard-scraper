import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx
from sqlmodel import Session

from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from crud.hansard_website_response import CRUDHansardWebsiteResponse
from exceptions import HansardGatewayError
from gateway.hansard_report import get_hansard_report_response_async
from logs import logger
from services.hansard_sitting_date_response import (
    build_new_hansard_sitting_date_response,
    build_old_hansard_sitting_date_response,
)
from settings import settings

_CONCURRENCY = 20
_HTTP_TIMEOUT_SECONDS = 30


def _parse_sitting_date(sitting_date: str) -> datetime:
    return datetime.strptime(sitting_date, "%d-%m-%Y")


def _strip_nul(value_tree: object) -> object:
    if isinstance(value_tree, str):
        return value_tree.replace("\x00", "")
    if isinstance(value_tree, dict):
        return {key: _strip_nul(value) for key, value in value_tree.items()}
    if isinstance(value_tree, list):
        return [_strip_nul(value) for value in value_tree]
    return value_tree


@dataclass(frozen=True)
class FetchedSittingDate:
    sitting_date: str
    result: Optional[dict]


async def _fetch_sitting_date_response(
    sitting_date: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> FetchedSittingDate:
    async with semaphore:
        try:
            result = await get_hansard_report_response_async(sitting_date, client)
            return FetchedSittingDate(sitting_date, result)
        except HansardGatewayError as error:
            logger.warning(f"Skipping {sitting_date}: {error}")
            return FetchedSittingDate(sitting_date, None)


async def _fetch_all_sitting_dates(dates: list[str]) -> list[FetchedSittingDate]:
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        return await asyncio.gather(
            *[_fetch_sitting_date_response(sitting_date, client, semaphore) for sitting_date in dates]
        )


def populate_hansard_sitting_dates(session: Session) -> None:
    all_sitting_dates = CRUDHansardWebsiteResponse(session).get_all_sitting_dates()
    existing_sitting_dates = CRUDHansardSittingDateResponse(
        session
    ).get_all_sitting_dates()
    dates_to_fetch = list(all_sitting_dates - existing_sitting_dates)

    fetched = asyncio.run(_fetch_all_sitting_dates(dates_to_fetch))

    for i, fetched_sitting_date in enumerate(fetched, start=1):
        sitting_date = fetched_sitting_date.sitting_date
        if fetched_sitting_date.result is None:
            continue
        logger.info(f"{i}/{len(dates_to_fetch)}: {sitting_date}")

        result = _strip_nul(fetched_sitting_date.result)
        if _parse_sitting_date(sitting_date) >= settings.sitting_date_format_change:
            sitting_date_data = build_new_hansard_sitting_date_response(result, sitting_date)
        else:
            sitting_date_data = build_old_hansard_sitting_date_response(result, sitting_date)

        CRUDHansardSittingDateResponse(session).create(sitting_date_data.response)

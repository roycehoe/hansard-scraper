import asyncio
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


def _parse_sitting_date(sitting_date: str) -> datetime:
    return datetime.strptime(sitting_date, "%d-%m-%Y")


def _strip_nul(obj):
    if isinstance(obj, str):
        return obj.replace("\x00", "")
    if isinstance(obj, dict):
        return {k: _strip_nul(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_nul(v) for v in obj]
    return obj


async def _fetch_all_sitting_dates(dates: list[str]) -> list[tuple[str, Optional[dict]]]:
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(timeout=30) as client:

        async def fetch_one(sitting_date):
            async with semaphore:
                try:
                    result = await get_hansard_report_response_async(
                        sitting_date, client
                    )
                    return sitting_date, result
                except HansardGatewayError as e:
                    logger.warning(f"Skipping {sitting_date}: {e}")
                    return sitting_date, None

        return await asyncio.gather(*[fetch_one(d) for d in dates])


def populate_hansard_sitting_dates(session: Session):
    all_sitting_dates = CRUDHansardWebsiteResponse(session).get_all_sitting_dates()
    existing_sitting_dates = CRUDHansardSittingDateResponse(
        session
    ).get_all_sitting_dates()
    dates_to_fetch = list(all_sitting_dates - existing_sitting_dates)

    fetched = asyncio.run(_fetch_all_sitting_dates(dates_to_fetch))

    sitting_crud = CRUDHansardSittingDateResponse(session)

    for i, (sitting_date, result) in enumerate(fetched, start=1):
        if result is None:
            continue
        logger.info(f"{i}/{len(dates_to_fetch)}: {sitting_date}")

        result = _strip_nul(result)
        if _parse_sitting_date(sitting_date) >= settings.sitting_date_format_change:
            data = build_new_hansard_sitting_date_response(result, sitting_date)
        else:
            data = build_old_hansard_sitting_date_response(result, sitting_date)

        sitting_crud.create(data.response)

import asyncio
from dataclasses import dataclass
from typing import Optional, Union

import httpx
from sqlmodel import Session

from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from crud.hansard_website_response import CRUDHansardWebsiteResponse
from exceptions import HansardGatewayError
from gateway.hansard_report import get_hansard_report_response_async
from logs import logger
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from services.hansard_sitting_date_response import build_hansard_sitting_date_response

_HTTP_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class FetchedSittingDate:
    sitting_date: str
    hansard_report_response: Optional[Union[HansardReportOldResponse, HansardReportNewResponse]]


async def _fetch_sitting_date_response(
    sitting_date: str,
    client: httpx.AsyncClient,
) -> FetchedSittingDate:
    try:
        hansard_report_response = await get_hansard_report_response_async(sitting_date, client)
        return FetchedSittingDate(sitting_date, hansard_report_response)
    except HansardGatewayError as error:
        logger.warning(f"Skipping {sitting_date}: {error}")
        return FetchedSittingDate(sitting_date, None)


async def _fetch_all_sitting_dates(sitting_dates: list[str]) -> list[FetchedSittingDate]:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        return await asyncio.gather(
            *[_fetch_sitting_date_response(sitting_date, client) for sitting_date in sitting_dates]
        )


def populate_hansard_sitting_dates(session: Session) -> None:
    all_sitting_dates = CRUDHansardWebsiteResponse(session).get_all_sitting_dates()
    existing_sitting_dates = CRUDHansardSittingDateResponse(
        session
    ).get_all_sitting_dates()
    sitting_dates_to_fetch = list(all_sitting_dates - existing_sitting_dates)

    fetched_sitting_dates = asyncio.run(_fetch_all_sitting_dates(sitting_dates_to_fetch))

    for i, fetched_sitting_date in enumerate(fetched_sitting_dates, start=1):
        sitting_date = fetched_sitting_date.sitting_date
        if fetched_sitting_date.hansard_report_response is None:
            continue
        logger.info(f"{i}/{len(sitting_dates_to_fetch)}: {sitting_date}")

        hansard_report_response = fetched_sitting_date.hansard_report_response
        hansard_sitting_date_response = build_hansard_sitting_date_response(hansard_report_response, sitting_date)

        CRUDHansardSittingDateResponse(session).create(hansard_sitting_date_response)

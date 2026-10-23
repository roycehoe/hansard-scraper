import asyncio
from dataclasses import dataclass
from typing import Optional, Union

import httpx
from sqlmodel import Session

from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from crud.sitting import CRUDSitting
from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.sitting import Sitting
from exceptions import HansardGatewayError
from gateway.hansard_report import get_hansard_report_response_async
from logs import logger
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from services.hansard_sitting_date_response import (
    build_new_hansard_sitting_date_response,
)
from services.sitting import build_sitting
from settings import settings
from utils.json_columns import get_json_column
from utils.sitting_dates import parse_sitting_date

_HTTP_TIMEOUT_SECONDS = 120
_SITTING_NESTED_COLUMNS = frozenset({"markdown_content", "sections", "annexures", "vernaculars", "a2b"})


@dataclass(frozen=True)
class FetchedSittingDetails:
    sitting: Sitting
    hansard_report_response: Optional[Union[HansardReportOldResponse, HansardReportNewResponse]]


async def _fetch_report_response(
    sitting: Sitting,
    client: httpx.AsyncClient,
) -> FetchedSittingDetails:
    try:
        hansard_report_response = await get_hansard_report_response_async(sitting.sitting_date, client)
        return FetchedSittingDetails(sitting, hansard_report_response)
    except HansardGatewayError as error:
        logger.warning(f"Skipping {sitting.sitting_date}: {error}")
        return FetchedSittingDetails(sitting, None)


async def _fetch_all_report_responses(sittings: list[Sitting]) -> list[FetchedSittingDetails]:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        return await asyncio.gather(*[_fetch_report_response(sitting, client) for sitting in sittings])


def _fill_null_fields(
    stored: Union[HansardSittingDateResponse, Sitting],
    built_values: dict[str, object],
    sitting_date: str,
) -> None:
    for field, built_value in built_values.items():
        if built_value is None:
            continue
        stored_value = getattr(stored, field)
        if stored_value is None:
            setattr(stored, field, built_value)
            continue
        if stored_value != built_value:
            logger.warning(f"Sitting {sitting_date}: {field} differs, keeping {stored_value!r} over {built_value!r}")


def populate_sitting_details(session: Session) -> None:
    sittings = CRUDSitting(session).get_by_html_full_content_null_and_sections_null()
    sittings_to_fetch = [
        sitting
        for sitting in sittings
        if sitting.sitting_date is not None and parse_sitting_date(sitting.sitting_date).date() <= settings.search_to_date
    ]
    logger.info(f"Fetching {len(sittings_to_fetch)}/{len(sittings)} sittings without details")

    fetched_sittings = asyncio.run(_fetch_all_report_responses(sittings_to_fetch))

    filled = 0
    skipped = 0
    failed_fetches = 0
    for i, fetched_sitting in enumerate(fetched_sittings, start=1):
        sitting = fetched_sitting.sitting
        hansard_report_response = fetched_sitting.hansard_report_response
        sitting_date = sitting.sitting_date
        if hansard_report_response is None:
            failed_fetches += 1
            skipped += 1
            continue
        if not isinstance(hansard_report_response, HansardReportNewResponse):
            logger.warning(f"Skipping {sitting_date}: the response is not the newer format")
            skipped += 1
            continue
        stored_hansard_sitting_date_response = CRUDHansardSittingDateResponse(session).get_by_sitting_date(sitting_date)
        if stored_hansard_sitting_date_response is None:
            logger.warning(f"Skipping {sitting_date}: no raw sitting date response")
            skipped += 1
            continue
        logger.info(f"{i}/{len(sittings_to_fetch)}: {sitting_date}")

        built_hansard_sitting_date_response = build_new_hansard_sitting_date_response(hansard_report_response, sitting_date)
        _fill_null_fields(stored_hansard_sitting_date_response, built_hansard_sitting_date_response.model_dump(exclude={"id"}), sitting_date)
        CRUDHansardSittingDateResponse(session).update(stored_hansard_sitting_date_response)

        rebuilt_sitting = build_sitting(stored_hansard_sitting_date_response)
        _fill_null_fields(sitting, rebuilt_sitting.model_dump(exclude={"id"} | _SITTING_NESTED_COLUMNS), sitting_date)
        if sitting.sections is None:
            sitting.sections = get_json_column(hansard_report_response.takes_section_vo_list)
        if sitting.annexures is None:
            sitting.annexures = get_json_column(hansard_report_response.annexure_list)
        if sitting.vernaculars is None:
            sitting.vernaculars = get_json_column(hansard_report_response.vernacular_list)
        if sitting.a2b is None:
            sitting.a2b = get_json_column(hansard_report_response.a2b_list)
        CRUDSitting(session).update(sitting)
        filled += 1
    session.commit()
    logger.info(f"Sitting details: {filled} sittings filled, {skipped} sittings skipped, {failed_fetches} fetches failed")

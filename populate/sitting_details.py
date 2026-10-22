import asyncio
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


async def _fetch_report_response(
    sitting_date: str,
    client: httpx.AsyncClient,
) -> Optional[Union[HansardReportOldResponse, HansardReportNewResponse]]:
    try:
        return await get_hansard_report_response_async(sitting_date, client)
    except HansardGatewayError as error:
        logger.warning(f"Skipping {sitting_date}: {error}")
        return None


async def _fetch_all_report_responses(
    sitting_dates: list[str],
) -> list[Optional[Union[HansardReportOldResponse, HansardReportNewResponse]]]:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        return await asyncio.gather(*[_fetch_report_response(sitting_date, client) for sitting_date in sitting_dates])


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

    responses = asyncio.run(_fetch_all_report_responses([sitting.sitting_date for sitting in sittings_to_fetch]))

    filled = 0
    skipped = 0
    for i, (sitting, response) in enumerate(zip(sittings_to_fetch, responses), start=1):
        sitting_date = sitting.sitting_date
        if response is None:
            skipped += 1
            continue
        if not isinstance(response, HansardReportNewResponse):
            logger.warning(f"Skipping {sitting_date}: the response is not the newer format")
            skipped += 1
            continue
        raw = CRUDHansardSittingDateResponse(session).get_by_sitting_date(sitting_date)
        if raw is None:
            logger.warning(f"Skipping {sitting_date}: no raw sitting date response")
            skipped += 1
            continue
        logger.info(f"{i}/{len(sittings_to_fetch)}: {sitting_date}")

        built = build_new_hansard_sitting_date_response(response, sitting_date)
        _fill_null_fields(raw, built.model_dump(exclude={"id"}), sitting_date)
        CRUDHansardSittingDateResponse(session).update(raw)

        rebuilt = build_sitting(raw)
        _fill_null_fields(sitting, rebuilt.model_dump(exclude={"id"} | _SITTING_NESTED_COLUMNS), sitting_date)
        column_to_value = {
            "sections": response.takes_section_vo_list,
            "annexures": response.annexure_list,
            "vernaculars": response.vernacular_list,
            "a2b": response.a2b_list,
        }
        for column, value in column_to_value.items():
            if getattr(sitting, column) is None:
                setattr(sitting, column, get_json_column(value))
        CRUDSitting(session).update(sitting)
        filled += 1
    session.commit()
    logger.info(f"Sitting details: {filled} sittings filled, {skipped} sittings skipped")

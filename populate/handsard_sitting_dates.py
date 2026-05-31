import asyncio
from datetime import datetime

import httpx
from sqlmodel import Session

from crud.handsard_sitting_date_response import CRUDHandsardSittingDateResponse
from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.sitting_a2b import CRUDSittingA2b
from crud.sitting_annexure import CRUDSittingAnnexure
from crud.sitting_attendance import CRUDSittingAttendance
from crud.sitting_ptba import CRUDSittingPtba
from crud.sitting_section import CRUDSittingSection
from crud.sitting_vernacular import CRUDSittingVernacular
from exceptions import HansardGatewayError
from gateway.handsard_report import get_handsard_report_response_async
from logs import logger
from services.handsard_sitting_date_response import (
    build_new_handsard_sitting_date_response,
    build_old_handsard_sitting_date_response,
)
from settings import settings

_CONCURRENCY = 20


def _parse_sitting_date(sitting_date: str) -> datetime:
    return datetime.strptime(sitting_date, "%d-%m-%Y")


async def _fetch_all_sitting_dates(dates: list[str]) -> list[tuple[str, dict | None]]:
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(timeout=30) as client:
        async def fetch_one(sitting_date):
            async with semaphore:
                try:
                    result = await get_handsard_report_response_async(sitting_date, client)
                    return sitting_date, result
                except HansardGatewayError as e:
                    logger.warning(f"Skipping {sitting_date}: {e}")
                    return sitting_date, None

        return await asyncio.gather(*[fetch_one(d) for d in dates])


def populate_handsard_sitting_dates(session: Session):
    all_sitting_dates = CRUDHandsardWebsiteResponse(session).get_all_sitting_dates()
    existing_sitting_dates = CRUDHandsardSittingDateResponse(session).get_all_sitting_dates()
    dates_to_fetch = list(all_sitting_dates - existing_sitting_dates)

    fetched = asyncio.run(_fetch_all_sitting_dates(dates_to_fetch))

    sitting_crud = CRUDHandsardSittingDateResponse(session)
    attendance_crud = CRUDSittingAttendance(session)
    ptba_crud = CRUDSittingPtba(session)
    section_crud = CRUDSittingSection(session)
    annexure_crud = CRUDSittingAnnexure(session)
    vernacular_crud = CRUDSittingVernacular(session)
    a2b_crud = CRUDSittingA2b(session)

    for i, (sitting_date, result) in enumerate(fetched, start=1):
        if result is None:
            continue
        logger.info(f"{i}/{len(dates_to_fetch)}: {sitting_date}")

        if _parse_sitting_date(sitting_date) >= settings.sitting_date_format_change:
            data = build_new_handsard_sitting_date_response(result, sitting_date)
        else:
            data = build_old_handsard_sitting_date_response(result, sitting_date)

        sitting_crud.create(data.response)
        sitting_id = data.response.id

        for record in data.attendance:
            record.sitting_id = sitting_id
            attendance_crud.create(record)
        for record in data.ptba:
            record.sitting_id = sitting_id
            ptba_crud.create(record)
        for record in data.sections:
            record.sitting_id = sitting_id
            section_crud.create(record)
        for record in data.annexures:
            record.sitting_id = sitting_id
            annexure_crud.create(record)
        for record in data.vernaculars:
            record.sitting_id = sitting_id
            vernacular_crud.create(record)
        for record in data.a2b:
            record.sitting_id = sitting_id
            a2b_crud.create(record)

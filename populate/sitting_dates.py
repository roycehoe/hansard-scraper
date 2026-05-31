from datetime import datetime

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
from gateway.handsard_report import get_handsard_report_response
from logs import logger
from services.handsard_sitting_date_response import (
    build_new_handsard_sitting_date_response,
    build_old_handsard_sitting_date_response,
)
from settings import settings


def _parse_sitting_date(sitting_date: str) -> datetime:
    return datetime.strptime(sitting_date, "%d-%m-%Y")


def populate_sitting_dates(session: Session):
    all_sitting_dates = CRUDHandsardWebsiteResponse(session).get_all_sitting_dates()
    existing_sitting_dates = CRUDHandsardSittingDateResponse(session).get_all_sitting_dates()
    dates_to_fetch = list(all_sitting_dates - existing_sitting_dates)

    sitting_crud = CRUDHandsardSittingDateResponse(session)
    attendance_crud = CRUDSittingAttendance(session)
    ptba_crud = CRUDSittingPtba(session)
    section_crud = CRUDSittingSection(session)
    annexure_crud = CRUDSittingAnnexure(session)
    vernacular_crud = CRUDSittingVernacular(session)
    a2b_crud = CRUDSittingA2b(session)

    for i, sitting_date in enumerate(dates_to_fetch, start=1):
        logger.info(f"{i}/{len(dates_to_fetch)}: {sitting_date}")
        try:
            result = get_handsard_report_response(sitting_date)
        except HansardGatewayError as e:
            logger.warning(f"Skipping {sitting_date}: {e}")
            continue

        if _parse_sitting_date(sitting_date) >= settings.sitting_date_format_change:
            data = build_new_handsard_sitting_date_response(result)
        else:
            data = build_old_handsard_sitting_date_response(result)

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

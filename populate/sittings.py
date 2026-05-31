from datetime import datetime

from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.sitting import CRUDSitting
from exceptions import HansardGatewayError
from gateway.handsard_report import get_handsard_report_response
from logs import logger
from services.handsard_sitting_date_response import (
    build_new_handsard_sitting_date_response,
    build_old_handsard_sitting_date_response,
)
from services.sitting import build_sitting
from settings import settings


def _parse_sitting_date(sitting_date: str) -> datetime:
    return datetime.strptime(sitting_date, "%d-%m-%Y")


def populate_sittings(session: Session):
    sitting_dates = list(CRUDHandsardWebsiteResponse(session).get_all_sitting_dates())
    crud = CRUDSitting(session)
    for i, sitting_date in enumerate(sitting_dates, start=1):
        logger.info(f"{i}/{len(sitting_dates)}: {sitting_date}")
        if crud.exists_by_sitting_date(sitting_date):
            logger.info(f"Already exists, skipping")
            continue

        try:
            result = get_handsard_report_response(sitting_date)
        except HansardGatewayError as e:
            logger.warning(f"Skipping {sitting_date}: {e}")
            continue

        if _parse_sitting_date(sitting_date) >= settings.sitting_date_format_change:
            data = build_new_handsard_sitting_date_response(result)
        else:
            data = build_old_handsard_sitting_date_response(result)

        crud.create(build_sitting(data.response))

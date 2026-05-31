from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.sitting import CRUDSitting
from exceptions import HansardGatewayError
from gateway.handsard_report import get_handsard_report_response
from logs import logger
from services.handsard_sitting_date_response import build_handsard_sitting_date_response
from services.sitting import build_sitting


def populate_sittings(session: Session):
    sitting_dates = list(CRUDHandsardWebsiteResponse(session).get_all_sitting_dates())
    crud = CRUDSitting(session)
    for i, sitting_date in enumerate(sitting_dates, start=1):
        logger.info(f"{i}/{len(sitting_dates)}: {sitting_date}")
        try:
            result = get_handsard_report_response(sitting_date)
        except HansardGatewayError as e:
            logger.warning(f"Skipping {sitting_date}: {e}")
            continue
        crud.create(build_sitting(build_handsard_sitting_date_response(result)))

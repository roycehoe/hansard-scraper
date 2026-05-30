from sqlmodel import Session

from crud.handsard_sitting_date_response import CRUDHandsardSittingDateResponse
from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from exceptions import HansardGatewayError
from gateway.handsard_report import get_handsard_report_response
from logs import logger
from services.handsard_sitting_date_response import build_handsard_sitting_date_response


def populate_sitting_dates(session: Session):
    all_sitting_dates = CRUDHandsardWebsiteResponse(session).get_all_sitting_dates()
    existing_sitting_dates = CRUDHandsardSittingDateResponse(session).get_all_sitting_dates()

    dates_to_fetch = list(all_sitting_dates - existing_sitting_dates)
    crud = CRUDHandsardSittingDateResponse(session)
    for i, sitting_date in enumerate(dates_to_fetch, start=1):
        logger.info(f"{i}/{len(dates_to_fetch)}: {sitting_date}")
        try:
            result = get_handsard_report_response(sitting_date)
        except HansardGatewayError as e:
            logger.warning(f"Skipping {sitting_date}: {e}")
            continue
        crud.create(build_handsard_sitting_date_response(result))

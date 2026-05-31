from sqlmodel import Session

from crud.handsard_sitting_date_response import CRUDHandsardSittingDateResponse
from crud.sitting import CRUDSitting
from logs import logger
from services.sitting import build_sitting


def populate_sittings(session: Session):
    all_responses = CRUDHandsardSittingDateResponse(session).get_all()
    crud = CRUDSitting(session)
    for i, response in enumerate(all_responses, start=1):
        logger.info(f"{i}/{len(all_responses)}: {response.sitting_date}")
        if crud.exists_by_sitting_date(response.sitting_date):
            logger.info("Already exists, skipping")
            continue
        crud.create(build_sitting(response))

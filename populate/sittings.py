from sqlmodel import Session

from crud.handsard_sitting_date_response import CRUDHandsardSittingDateResponse
from crud.sitting import CRUDSitting
from logs import logger
from services.sitting import build_sitting


def populate_sittings(session: Session):
    responses = CRUDHandsardSittingDateResponse(session).get_all()
    crud = CRUDSitting(session)
    for i, response in enumerate(responses, start=1):
        logger.info(f"{i}/{len(responses)}")
        crud.create(build_sitting(response))

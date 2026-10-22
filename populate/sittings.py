from sqlmodel import Session

from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from crud.sitting import CRUDSitting
from logs import logger
from services.sitting import build_sitting


def populate_sittings(session: Session) -> None:
    hansard_sitting_date_responses = CRUDHansardSittingDateResponse(session).get_all()
    existing_dates = CRUDSitting(session).get_sitting_dates_by_sitting_date_not_null()
    responses_to_process = [hansard_sitting_date_response for hansard_sitting_date_response in hansard_sitting_date_responses if hansard_sitting_date_response.sitting_date not in existing_dates]
    logger.info(f"Building {len(responses_to_process)}/{len(hansard_sitting_date_responses)} sittings ({len(existing_dates)} already in DB)")

    sittings = []
    for i, hansard_sitting_date_response in enumerate(responses_to_process, start=1):
        logger.info(f"{i}/{len(responses_to_process)}: {hansard_sitting_date_response.sitting_date}")
        sittings.append(build_sitting(hansard_sitting_date_response))
    if sittings:
        CRUDSitting(session).create_many(sittings)

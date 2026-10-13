from sqlmodel import Session

from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from crud.sitting import CRUDSitting
from logs import logger
from services.sitting import build_sitting


def populate_sittings(session: Session) -> None:
    all_responses = CRUDHansardSittingDateResponse(session).get_all()
    existing_dates = CRUDSitting(session).get_all_sitting_dates()
    sittings_to_process = [response for response in all_responses if response.sitting_date not in existing_dates]
    logger.info(f"Building {len(sittings_to_process)}/{len(all_responses)} sittings ({len(existing_dates)} already in DB)")

    sittings = []
    for i, response in enumerate(sittings_to_process, start=1):
        logger.info(f"{i}/{len(sittings_to_process)}: {response.sitting_date}")
        sittings.append(build_sitting(response))
    if sittings:
        CRUDSitting(session).create_many(sittings)

from sqlmodel import Session

from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from crud.sitting import CRUDSitting
from logs import logger
from services.sitting import build_sitting


def populate_sittings(session: Session):
    all_responses = CRUDHansardSittingDateResponse(session).get_all()
    crud = CRUDSitting(session)
    existing_dates = crud.get_all_sitting_dates()
    to_process = [r for r in all_responses if r.sitting_date not in existing_dates]
    logger.info(f"Building {len(to_process)}/{len(all_responses)} sittings ({len(existing_dates)} already in DB)")

    sittings = []
    for i, response in enumerate(to_process, start=1):
        logger.info(f"{i}/{len(to_process)}: {response.sitting_date}")
        sittings.append(build_sitting(response))
    if sittings:
        crud.create_many(sittings)

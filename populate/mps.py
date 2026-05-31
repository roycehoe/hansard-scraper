from sqlmodel import Session

from crud.mp import CRUDMp
from gateway.mps_by_parliament import get_all_mps
from logs import logger
from services.mp import build_mp


def populate_mps(session: Session) -> None:
    crud = CRUDMp(session)
    mps = get_all_mps()
    for i, mp_result in enumerate(mps, start=1):
        logger.info(f"{i}/{len(mps)}: {mp_result.name} (Parliament {mp_result.parliament_number})")
        crud.create(build_mp(mp_result))

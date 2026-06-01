from sqlmodel import Session

from crud.mp import CRUDMp
from crud.sitting import CRUDSitting
from crud.sitting_attendance import CRUDSittingAttendance
from logs import logger
from services.sitting_attendance import build_mp_lookups, get_sitting_attendance


def populate_sitting_attendances(session: Session):
    lookups = build_mp_lookups(CRUDMp(session).get_all())
    sittings = CRUDSitting(session).get_all()
    crud = CRUDSittingAttendance(session)
    done = crud.get_sitting_ids_with_attendance()
    to_process = [sitting for sitting in sittings if sitting.id not in done]
    logger.info(
        f"Extracting attendance for {len(to_process)}/{len(sittings)} sittings "
        f"({len(done)} already done)"
    )
    for sitting_index, sitting in enumerate(to_process, start=1):
        logger.info(f"{sitting_index}/{len(to_process)}: {sitting.sitting_date}")
        for record in get_sitting_attendance(sitting, lookups):
            crud.create(record)

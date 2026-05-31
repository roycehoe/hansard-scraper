from sqlmodel import Session

from crud.sitting import CRUDSitting
from crud.sitting_attendance import CRUDSittingAttendance
from logs import logger
from services.sitting_attendance import get_sitting_attendance


def populate_sitting_attendances(session: Session):
    sittings = CRUDSitting(session).get_all()
    crud = CRUDSittingAttendance(session)
    done = crud.get_sitting_ids_with_attendance()
    to_process = [s for s in sittings if s.id not in done]
    logger.info(
        f"Extracting attendance for {len(to_process)}/{len(sittings)} sittings "
        f"({len(done)} already done)"
    )
    for i, sitting in enumerate(to_process, start=1):
        logger.info(f"{i}/{len(to_process)}: {sitting.sitting_date}")
        for record in get_sitting_attendance(sitting):
            crud.create(record)

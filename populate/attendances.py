from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from logs import logger
from services.attendance import build_speaker_lookups, get_sitting_attendance


def populate_attendances(session: Session):
    lookups = build_speaker_lookups(CRUDSpeaker(session).get_all())
    sittings = CRUDSitting(session).get_all()
    crud = CRUDAttendance(session)
    done = crud.get_sitting_ids_with_attendance()
    to_process = [sitting for sitting in sittings if sitting.id not in done]
    logger.info(
        f"Extracting attendance for {len(to_process)}/{len(sittings)} sittings "
        f"({len(done)} already done)"
    )
    for sitting_index, sitting in enumerate(to_process, start=1):
        logger.info(f"{sitting_index}/{len(to_process)}: {sitting.sitting_date}")
        records = list(get_sitting_attendance(sitting, lookups))
        if records:
            crud.create_many(records)

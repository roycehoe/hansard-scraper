from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from logs import logger
from services.attendance import (
    build_constituency_lookups,
    build_sitting_attendances,
    build_speaker_lookups,
)
from utils.data_files import get_constituency_names


def populate_attendances(session: Session) -> None:
    lookups = build_speaker_lookups(CRUDSpeaker(session).get_all())
    constituency_lookups = build_constituency_lookups(get_constituency_names())
    sittings = CRUDSitting(session).get_all()
    sitting_ids_done = CRUDAttendance(session).get_distinct_sitting_ids_by_sitting_id_not_null()
    sittings_to_process = [sitting for sitting in sittings if sitting.id not in sitting_ids_done]
    logger.info(
        f"Extracting attendance for {len(sittings_to_process)}/{len(sittings)} sittings "
        f"({len(sitting_ids_done)} already done)"
    )
    for sitting_index, sitting in enumerate(sittings_to_process, start=1):
        logger.info(f"{sitting_index}/{len(sittings_to_process)}: {sitting.sitting_date}")
        attendances = build_sitting_attendances(sitting, lookups, constituency_lookups)
        if attendances:
            CRUDAttendance(session).create_many(attendances)

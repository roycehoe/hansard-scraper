from sqlmodel import Session, select

from database.mp import Mp
from database.report import Report
from database.sitting import Sitting
from database.sitting_attendance import SittingAttendance
from database.speech import Speech
from logs import logger
from services.sitting_attendance import (
    _normalize_name,
    _strip_title,
    infer_parliament,
    resolve_canonical_name,
)


def _build_mp_id_lookup(session: Session) -> dict[tuple[str, int], int]:
    mps = session.exec(select(Mp)).all()
    return {(mp.name, mp.parliament_number): mp.id for mp in mps if mp.id is not None}


def _populate_attendance_mp_ids(session: Session, mp_id_lookup: dict[tuple[str, int], int]) -> None:
    records = session.exec(
        select(SittingAttendance).where(SittingAttendance.mp_id == None)  # noqa: E711
    ).all()
    sittings_by_id: dict[int, Sitting] = {
        s.id: s for s in session.exec(select(Sitting)).all() if s.id is not None
    }

    updated = 0
    for record in records:
        if not record.mp_name or record.sitting_id is None:
            continue
        sitting = sittings_by_id.get(record.sitting_id)
        if sitting is None:
            continue
        parliament = infer_parliament(sitting)
        if parliament is None:
            continue
        mp_id = mp_id_lookup.get((record.mp_name, parliament))
        if mp_id:
            record.mp_id = mp_id
            session.add(record)
            updated += 1

    session.commit()
    logger.info(f"SittingAttendance: set mp_id on {updated}/{len(records)} records")


def _populate_speech_mp_ids(session: Session, mp_id_lookup: dict[tuple[str, int], int]) -> None:
    rows = session.exec(
        select(Speech, Report)
        .join(Report)
        .where(Speech.mp_id == None)  # noqa: E711
    ).all()

    updated = 0
    for speech, report in rows:
        if not speech.speaker:
            continue
        parliament = report.parliament_number
        # Strip trailing colon (artifact of bold-speaker markup "**Name:**") and title prefix.
        name = _strip_title(speech.speaker.rstrip(":").strip())
        name = _normalize_name(name)
        if not name:
            continue
        canonical = resolve_canonical_name(name, parliament)
        if canonical is None:
            continue
        mp_id = mp_id_lookup.get((canonical, parliament))
        if mp_id:
            speech.mp_id = mp_id
            session.add(speech)
            updated += 1

    session.commit()
    logger.info(f"Speech: set mp_id on {updated}/{len(rows)} records")


def populate_mp_links(session: Session) -> None:
    mp_id_lookup = _build_mp_id_lookup(session)
    _populate_attendance_mp_ids(session, mp_id_lookup)
    _populate_speech_mp_ids(session, mp_id_lookup)

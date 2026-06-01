import re

from sqlmodel import Session, select, update

from database.mp import Mp
from database.report import Report
from database.sitting import Sitting
from database.sitting_attendance import SittingAttendance
from database.speech import Speech
from logs import logger
from services.sitting_attendance import (
    infer_parliament,
    normalize_name,
    resolve_canonical_name,
    strip_title,
)

_BATCH = 1000


def _build_mp_id_lookup(session: Session) -> dict[tuple[str, int], int]:
    mps = session.exec(select(Mp)).all()
    return {(mp.name, mp.parliament_number): mp.id for mp in mps if mp.id is not None}


def _populate_attendance_mp_ids(session: Session, mp_id_lookup: dict[tuple[str, int], int]) -> None:
    sittings_by_id: dict[int, Sitting] = {
        s.id: s for s in session.exec(select(Sitting)).all() if s.id is not None
    }

    unresolved_ids: list[int] = [
        row
        for row in session.exec(
            select(SittingAttendance.id).where(SittingAttendance.mp_id == None)  # noqa: E711
        ).all()
    ]
    total = len(unresolved_ids)
    updated = 0

    for i in range(0, total, _BATCH):
        batch_ids = unresolved_ids[i : i + _BATCH]
        records = session.exec(
            select(SittingAttendance).where(SittingAttendance.id.in_(batch_ids))
        ).all()

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

            if not mp_id:
                name = normalize_name(strip_title(record.mp_name))
                canonical = resolve_canonical_name(name, parliament)
                if canonical is None and parliament == 0:
                    for fallback in [1, 2, 3]:
                        c = resolve_canonical_name(name, fallback)
                        if c and (c, fallback) in mp_id_lookup:
                            canonical = c
                            parliament = fallback
                            break
                if canonical:
                    mp_id = mp_id_lookup.get((canonical, parliament))

            if mp_id:
                record.mp_id = mp_id
                session.add(record)
                updated += 1

        session.commit()
        session.expire_all()
        logger.info(f"SittingAttendance: {min(i + _BATCH, total)}/{total} processed, {updated} resolved")

    logger.info(f"SittingAttendance: set mp_id on {updated}/{total} records")


def _populate_speech_mp_ids(session: Session, mp_id_lookup: dict[tuple[str, int], int]) -> None:
    _NON_SPEAKERS = {
        "An hon. Member", "Some hon. Members", "Non-Residents",
        "Tributes by Leader of the House and Opposition Leaders",
    }
    _INNER_TITLE = re.compile(
        r"^(?:Mr|Mrs|Dr|Miss|Ms|Mdm|Prof|Madam|Inche|Encik|Tuan Haji|Haji)\b"
    )

    unresolved_ids: list[int] = [
        row
        for row in session.exec(
            select(Speech.id).where(Speech.mp_id == None)  # noqa: E711
        ).all()
    ]
    total = len(unresolved_ids)
    updated = 0

    for i in range(0, total, _BATCH):
        batch_ids = unresolved_ids[i : i + _BATCH]

        # Only fetch columns needed for resolution — avoids loading transcript/markdown_content.
        rows = session.exec(
            select(Speech.id, Speech.speaker, Report.parliament_number)
            .join(Report)
            .where(Speech.id.in_(batch_ids))
        ).all()

        for speech_id, speaker, parliament in rows:
            if not speaker:
                continue
            if speaker in _NON_SPEAKERS or speaker.startswith("(") or speaker.startswith("_"):
                continue

            raw = speaker.rstrip(":").strip()
            m = re.search(r"\s*\(([^)]+)\)\s*$", raw)
            if m:
                inner = m.group(1).strip()
                if _INNER_TITLE.match(inner):
                    raw = inner
                else:
                    raw = raw[: m.start()]
            raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
            name = strip_title(raw)
            name = normalize_name(name)
            if not name:
                continue

            canonical = resolve_canonical_name(name, parliament)
            if canonical is None and parliament == 0:
                for fallback in [1, 2, 3]:
                    c = resolve_canonical_name(name, fallback)
                    if c and (c, fallback) in mp_id_lookup:
                        canonical = c
                        parliament = fallback
                        break

            if canonical is None:
                continue

            mp_id = mp_id_lookup.get((canonical, parliament))
            if mp_id:
                session.exec(update(Speech).where(Speech.id == speech_id).values(mp_id=mp_id))
                updated += 1

        session.commit()
        logger.info(f"Speech: {min(i + _BATCH, total)}/{total} processed, {updated} resolved")

    logger.info(f"Speech: set mp_id on {updated}/{total} records")


def populate_mp_links(session: Session) -> None:
    mp_id_lookup = _build_mp_id_lookup(session)
    _populate_attendance_mp_ids(session, mp_id_lookup)
    _populate_speech_mp_ids(session, mp_id_lookup)

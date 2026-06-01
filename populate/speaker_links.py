import re
from typing import Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from logs import logger
from services.attendance import (
    SpeakerLookups,
    build_speaker_lookups,
    infer_parliament,
    normalize_name,
    resolve_canonical_name,
    strip_title,
)

_BATCH = 1000
_COLONIAL_PARLIAMENT_FALLBACKS = [1, 2, 3]

_NON_SPEAKERS = {
    "An hon. Member", "Some hon. Members", "Non-Residents",
    "Tributes by Leader of the House and Opposition Leaders",
}

def _resolve_with_parliament_fallback(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> tuple[Optional[str], int]:
    canonical = resolve_canonical_name(name, parliament, lookups)
    if canonical is not None or parliament != 0:
        return canonical, parliament
    for fallback in _COLONIAL_PARLIAMENT_FALLBACKS:
        candidate = resolve_canonical_name(name, fallback, lookups)
        if candidate and (candidate, fallback) in speaker_id_lookup:
            return candidate, fallback
    return None, parliament


def _populate_attendance_speaker_ids(
    session: Session,
    speaker_id_lookup: dict[tuple[str, int], int],
    lookups: SpeakerLookups,
) -> None:
    crud_sitting = CRUDSitting(session)
    crud = CRUDAttendance(session)

    sittings_by_id = {sitting.id: sitting for sitting in crud_sitting.get_all() if sitting.id is not None}
    unresolved_ids = crud.get_unresolved_ids()
    total = len(unresolved_ids)
    updated = 0

    for batch_start in range(0, total, _BATCH):
        batch_ids = unresolved_ids[batch_start : batch_start + _BATCH]
        records = crud.get_by_ids(batch_ids)

        for record in records:
            if not record.mp_name or record.sitting_id is None:
                continue
            sitting = sittings_by_id.get(record.sitting_id)
            if sitting is None:
                continue
            parliament = infer_parliament(sitting)
            if parliament is None:
                continue

            speaker_id = speaker_id_lookup.get((record.mp_name, parliament))

            if not speaker_id:
                name = normalize_name(strip_title(record.mp_name))
                canonical, parliament = _resolve_with_parliament_fallback(name, parliament, lookups, speaker_id_lookup)
                if canonical:
                    speaker_id = speaker_id_lookup.get((canonical, parliament))

            if speaker_id:
                crud.mark_speaker_id(record, speaker_id)
                updated += 1

        session.commit()
        session.expire_all()
        logger.info(f"Attendance: {min(batch_start + _BATCH, total)}/{total} processed, {updated} resolved")

    logger.info(f"Attendance: set speaker_id on {updated}/{total} records")


def _populate_speech_speaker_ids(
    session: Session,
    speaker_id_lookup: dict[tuple[str, int], int],
    lookups: SpeakerLookups,
) -> None:
    crud = CRUDSpeech(session)
    unresolved_ids = crud.get_unresolved_ids()
    total = len(unresolved_ids)
    updated = 0

    for batch_start in range(0, total, _BATCH):
        batch_ids = unresolved_ids[batch_start : batch_start + _BATCH]
        rows = crud.get_speaker_info_by_ids(batch_ids)

        for speech_id, speaker, parliament in rows:
            if not speaker:
                continue
            if speaker in _NON_SPEAKERS or speaker.startswith("(") or speaker.startswith("_"):
                continue

            raw = speaker.rstrip(":").strip()
            paren_match = re.search(r"\s*\(([^)]+)\)\s*$", raw)
            if paren_match:
                inner = paren_match.group(1).strip()
                if strip_title(inner) != inner:
                    raw = inner
                else:
                    raw = raw[: paren_match.start()]
            raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
            name = normalize_name(strip_title(raw))
            if not name:
                continue

            canonical, parliament = _resolve_with_parliament_fallback(name, parliament, lookups, speaker_id_lookup)

            if canonical is None:
                continue

            speaker_id = speaker_id_lookup.get((canonical, parliament))
            if speaker_id:
                crud.set_speaker_id(speech_id, speaker_id)
                updated += 1

        session.commit()
        logger.info(f"Speech: {min(batch_start + _BATCH, total)}/{total} processed, {updated} resolved")

    logger.info(f"Speech: set speaker_id on {updated}/{total} records")


def populate_speaker_links(session: Session) -> None:
    speakers = CRUDSpeaker(session).get_all()
    speaker_id_lookup = {(s.name, s.parliament_number): s.id for s in speakers if s.id is not None}
    lookups = build_speaker_lookups(speakers)
    _populate_attendance_speaker_ids(session, speaker_id_lookup, lookups)
    _populate_speech_speaker_ids(session, speaker_id_lookup, lookups)

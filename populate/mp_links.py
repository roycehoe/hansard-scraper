import re
from typing import Optional

from sqlmodel import Session

from crud.mp import CRUDMp
from crud.sitting import CRUDSitting
from crud.sitting_attendance import CRUDSittingAttendance
from crud.speech import CRUDSpeech
from logs import logger
from services.sitting_attendance import (
    MpLookups,
    build_mp_lookups,
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
_INNER_TITLE = re.compile(
    r"^(?:Mr|Mrs|Dr|Miss|Ms|Mdm|Prof|Madam|Inche|Encik|Tuan Haji|Haji)\b"
)


def _resolve_with_parliament_fallback(
    name: str,
    parliament: int,
    lookups: MpLookups,
    mp_id_lookup: dict[tuple[str, int], int],
) -> tuple[Optional[str], int]:
    canonical = resolve_canonical_name(name, parliament, lookups)
    if canonical is not None or parliament != 0:
        return canonical, parliament
    for fallback in _COLONIAL_PARLIAMENT_FALLBACKS:
        candidate = resolve_canonical_name(name, fallback, lookups)
        if candidate and (candidate, fallback) in mp_id_lookup:
            return candidate, fallback
    return None, parliament


def _populate_attendance_mp_ids(
    session: Session,
    mp_id_lookup: dict[tuple[str, int], int],
    lookups: MpLookups,
) -> None:
    crud_sitting = CRUDSitting(session)
    crud = CRUDSittingAttendance(session)

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

            mp_id = mp_id_lookup.get((record.mp_name, parliament))

            if not mp_id:
                name = normalize_name(strip_title(record.mp_name))
                canonical, parliament = _resolve_with_parliament_fallback(name, parliament, lookups, mp_id_lookup)
                if canonical:
                    mp_id = mp_id_lookup.get((canonical, parliament))

            if mp_id:
                crud.mark_mp_id(record, mp_id)
                updated += 1

        session.commit()
        session.expire_all()
        logger.info(f"SittingAttendance: {min(batch_start + _BATCH, total)}/{total} processed, {updated} resolved")

    logger.info(f"SittingAttendance: set mp_id on {updated}/{total} records")


def _populate_speech_mp_ids(
    session: Session,
    mp_id_lookup: dict[tuple[str, int], int],
    lookups: MpLookups,
) -> None:
    crud = CRUDSpeech(session)
    unresolved_ids = crud.get_unresolved_ids()
    total = len(unresolved_ids)
    updated = 0

    for batch_start in range(0, total, _BATCH):
        batch_ids = unresolved_ids[batch_start : batch_start + _BATCH]

        # Only fetch columns needed for resolution -- avoids loading transcript/markdown_content.
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
                if _INNER_TITLE.match(inner):
                    raw = inner
                else:
                    raw = raw[: paren_match.start()]
            raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
            name = normalize_name(strip_title(raw))
            if not name:
                continue

            canonical, parliament = _resolve_with_parliament_fallback(name, parliament, lookups, mp_id_lookup)

            if canonical is None:
                continue

            mp_id = mp_id_lookup.get((canonical, parliament))
            if mp_id:
                crud.set_mp_id(speech_id, mp_id)
                updated += 1

        session.commit()
        logger.info(f"Speech: {min(batch_start + _BATCH, total)}/{total} processed, {updated} resolved")

    logger.info(f"Speech: set mp_id on {updated}/{total} records")


def populate_mp_links(session: Session) -> None:
    mps = CRUDMp(session).get_all()
    mp_id_lookup = {(mp.name, mp.parliament_number): mp.id for mp in mps if mp.id is not None}
    lookups = build_mp_lookups(mps)
    _populate_attendance_mp_ids(session, mp_id_lookup, lookups)
    _populate_speech_mp_ids(session, mp_id_lookup, lookups)

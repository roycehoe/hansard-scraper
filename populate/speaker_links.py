import re
from typing import Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from logs import logger
from services.attendance import (
    VOLUME_TO_PARLIAMENT,
    SpeakerLookups,
    build_speaker_lookups,
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

_PRESIDING_OFFICERS: dict[tuple[str, int], str] = {
    ("SPEAKER", 0): "George Oehlers",
    ("SPEAKER", 1): "George Oehlers",
    ("SPEAKER", 2): "Coomaraswamy, P.",
    ("SPEAKER", 3): "Yeoh Ghim Seng",
    ("SPEAKER", 4): "Yeoh Ghim Seng",
    ("SPEAKER", 5): "Yeoh Ghim Seng",
    ("SPEAKER", 6): "Yeoh Ghim Seng",
    ("DEPUTY SPEAKER", 6): "Tan Soo Khoon",
    ("SPEAKER", 7): "Tan Soo Khoon",
    ("SPEAKER", 8): "Tan Soo Khoon",
    ("SPEAKER", 9): "Tan Soo Khoon",
    ("SPEAKER", 10): "Abdullah Bin Tarmugi",
    ("DEPUTY SPEAKER", 10): "Chew Heng Ching",
    ("SPEAKER", 11): "Abdullah Bin Tarmugi",
    ("SPEAKER", 12): "Michael Palmer",
}

_ROLE_ONLY_SPEAKERS: dict[tuple[str, int], str] = {
    ("The Prime Minister", 0): "Lee Kuan Yew",
    ("The Prime Minister", 1): "Lee Kuan Yew",
    ("The Prime Minister", 2): "Lee Kuan Yew",
    ("The Prime Minister", 3): "Lee Kuan Yew",
    ("The Prime Minister", 5): "Lee Kuan Yew",
    ("The Prime Minister", 6): "Lee Kuan Yew",
    ("The Prime Minister", 8): "Goh Chok Tong",
    ("The Prime Minister", 11): "Lee Hsien Loong",
    ("The Minister for Health", 11): "Khaw Boon Wan",
}


def _resolve_presiding_officer(
    raw: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    if raw in ("Mr Speaker", "Mdm Speaker"):
        role = "SPEAKER"
    elif raw.startswith("Mr Deputy Speaker") or raw.startswith("The Deputy Speaker"):
        role = "DEPUTY SPEAKER"
    else:
        return None
    parl = parliament if parliament != 0 else next(
        (p for p in _COLONIAL_PARLIAMENT_FALLBACKS if (role, p) in _PRESIDING_OFFICERS),
        parliament,
    )
    name = _PRESIDING_OFFICERS.get((role, parl))
    if not name:
        return None
    canonical, resolved_parl = _resolve_with_parliament_fallback(name, parl, lookups, speaker_id_lookup)
    return speaker_id_lookup.get((canonical, resolved_parl)) if canonical else None



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

    parliament_by_sitting_id: dict[int, int] = {}
    for sitting_id, parlement_no, volume_no in crud_sitting.get_parliament_columns():
        if parlement_no is not None:
            parliament_by_sitting_id[sitting_id] = parlement_no
        elif volume_no is not None and volume_no in VOLUME_TO_PARLIAMENT:
            parliament_by_sitting_id[sitting_id] = VOLUME_TO_PARLIAMENT[volume_no]

    unresolved_ids = crud.get_unresolved_ids()
    total = len(unresolved_ids)
    updated = 0

    for batch_start in range(0, total, _BATCH):
        batch_ids = unresolved_ids[batch_start : batch_start + _BATCH]
        records = crud.get_by_ids(batch_ids)

        batch_updates: dict[int, int] = {}
        for record in records:
            if not record.speaker_name or record.sitting_id is None:
                continue
            parliament = parliament_by_sitting_id.get(record.sitting_id)
            if parliament is None:
                continue

            speaker_id = speaker_id_lookup.get((record.speaker_name, parliament))

            if not speaker_id:
                name = normalize_name(strip_title(record.speaker_name))
                canonical, parliament = _resolve_with_parliament_fallback(name, parliament, lookups, speaker_id_lookup)
                if canonical:
                    speaker_id = speaker_id_lookup.get((canonical, parliament))

            if speaker_id and record.id is not None:
                batch_updates[record.id] = speaker_id
                updated += 1

        crud.set_speaker_ids_bulk(batch_updates)
        session.commit()
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

        batch_updates: dict[int, int] = {}
        for speech_id, speaker, parliament in rows:
            if not speaker:
                continue
            if speaker in _NON_SPEAKERS or speaker.startswith("(") or speaker.startswith("_"):
                continue

            raw = speaker.rstrip(":").strip()

            po_sid = _resolve_presiding_officer(raw, parliament, lookups, speaker_id_lookup)
            if po_sid is not None:
                batch_updates[speech_id] = po_sid
                updated += 1
            if raw in ("Mr Speaker", "Mdm Speaker") or raw.startswith(("Mr Deputy Speaker", "The Deputy Speaker")):
                continue  # always skip cascade for presiding officers

            role_key: tuple[str, int] | None = (raw, parliament) if parliament != 0 else None
            if role_key is None:
                for fb in _COLONIAL_PARLIAMENT_FALLBACKS:
                    if (raw, fb) in _ROLE_ONLY_SPEAKERS:
                        role_key = (raw, fb)
                        break
            if role_key and role_key in _ROLE_ONLY_SPEAKERS:
                role_name = _ROLE_ONLY_SPEAKERS[role_key]
                role_canonical, role_parl = _resolve_with_parliament_fallback(
                    role_name, role_key[1], lookups, speaker_id_lookup
                )
                if role_canonical:
                    role_sid = speaker_id_lookup.get((role_canonical, role_parl))
                    if role_sid:
                        batch_updates[speech_id] = role_sid
                        updated += 1
                continue  # role-only strings are never resolvable via the name cascade

            parens = list(re.finditer(r"\(([^)]+)\)", raw))
            if parens:
                def _has_title(m: re.Match) -> bool:
                    inner = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", m.group(1).strip())
                    return strip_title(inner) != inner

                title_paren = next(
                    (m for m in reversed(parens) if _has_title(m)),
                    None,
                )
                if title_paren:
                    raw = title_paren.group(1).strip()
                else:
                    raw = raw[: parens[0].start()].strip()
            raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
            name = normalize_name(strip_title(raw))
            if not name:
                continue

            canonical, parliament = _resolve_with_parliament_fallback(name, parliament, lookups, speaker_id_lookup)

            if canonical is None:
                continue

            speaker_id = speaker_id_lookup.get((canonical, parliament))
            if speaker_id:
                batch_updates[speech_id] = speaker_id
                updated += 1

        crud.set_speaker_ids_bulk(batch_updates)
        session.commit()
        logger.info(f"Speech: {min(batch_start + _BATCH, total)}/{total} processed, {updated} resolved")

    logger.info(f"Speech: set speaker_id on {updated}/{total} records")


def populate_speaker_links(session: Session) -> None:
    speakers = CRUDSpeaker(session).get_all()
    speaker_id_lookup = {(s.name, s.parliament_number): s.id for s in speakers if s.id is not None}
    lookups = build_speaker_lookups(speakers)
    _populate_attendance_speaker_ids(session, speaker_id_lookup, lookups)
    _populate_speech_speaker_ids(session, speaker_id_lookup, lookups)

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
            if not record.speaker_name or record.sitting_id is None:
                continue
            sitting = sittings_by_id.get(record.sitting_id)
            if sitting is None:
                continue
            parliament = infer_parliament(sitting)
            if parliament is None:
                continue

            speaker_id = speaker_id_lookup.get((record.speaker_name, parliament))

            if not speaker_id:
                name = normalize_name(strip_title(record.speaker_name))
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

            # Presiding officer strings carry no individual name — resolve by parliament lookup.
            _po_role: str | None = None
            if raw in ("Mr Speaker", "Mdm Speaker"):
                _po_role = "SPEAKER"
            elif raw.startswith("Mr Deputy Speaker") or raw.startswith("The Deputy Speaker"):
                _po_role = "DEPUTY SPEAKER"
            if _po_role is not None:
                _po_parl = parliament if parliament != 0 else next(
                    (p for p in _COLONIAL_PARLIAMENT_FALLBACKS if (_po_role, p) in _PRESIDING_OFFICERS),
                    parliament,
                )
                _po_name = _PRESIDING_OFFICERS.get((_po_role, _po_parl))
                if _po_name:
                    _po_canonical, _po_resolved_parl = _resolve_with_parliament_fallback(
                        _po_name, _po_parl, lookups, speaker_id_lookup
                    )
                    if _po_canonical:
                        _po_sid = speaker_id_lookup.get((_po_canonical, _po_resolved_parl))
                        if _po_sid:
                            crud.set_speaker_id(speech_id, _po_sid)
                            updated += 1
                continue  # always skip cascade for presiding officers

            # Role-only strings — resolve by parliament→person mapping.
            _role_key: tuple[str, int] | None = (raw, parliament) if parliament != 0 else None
            if _role_key is None:
                for _fb in _COLONIAL_PARLIAMENT_FALLBACKS:
                    if (raw, _fb) in _ROLE_ONLY_SPEAKERS:
                        _role_key = (raw, _fb)
                        break
            if _role_key and _role_key in _ROLE_ONLY_SPEAKERS:
                _role_name = _ROLE_ONLY_SPEAKERS[_role_key]
                _role_canonical, _role_parl = _resolve_with_parliament_fallback(
                    _role_name, _role_key[1], lookups, speaker_id_lookup
                )
                if _role_canonical:
                    _role_sid = speaker_id_lookup.get((_role_canonical, _role_parl))
                    if _role_sid:
                        crud.set_speaker_id(speech_id, _role_sid)
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

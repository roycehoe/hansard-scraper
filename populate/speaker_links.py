import re
from datetime import date, datetime
from typing import Iterable, Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from logs import logger
from populate.speaker_resolution_constants import (
    CHIEF_MINISTER_TERMS,
    COLONIAL_PARLIAMENT_FALLBACKS,
    DEPUTY_SPEAKER_TERMS,
    NON_SPEAKERS,
    ROLE_ONLY_SPEAKERS,
    SPEAKER_TERMS,
)
from services.attendance import (
    VOLUME_TO_PARLIAMENT,
    SpeakerLookups,
    build_speaker_lookups,
    normalize_name,
    resolve_canonical_name,
    strip_title,
)

_WRITE_BATCH = 50_000

# Only these roles resolve by sitting date; every other string resolves the same
# way for every sitting in a parliament, so it is memoised on (string, parliament).
_DATE_DEPENDENT_ROLES = (
    "The Chief Minister",
    "Mr Speaker",
    "Mdm Speaker",
    "Mr Deputy Speaker",
    "The Deputy Speaker",
)


def _paren_contains_title(m: re.Match) -> bool:
    inner = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", m.group(1).strip())
    return strip_title(inner) != inner


def _holder_on(
    terms: list[tuple[date, date, str]], sitting_date: Optional[datetime]
) -> Optional[str]:
    """The single person holding the office on the sitting day, or None when there
    was none, more than one, or the day is unknown."""
    if sitting_date is None:
        return None
    day = sitting_date.date()
    holders = [name for first, last, name in terms if first <= day <= last]
    return holders[0] if len(holders) == 1 else None


def _resolve_presiding_officer(
    raw: str,
    parliament: int,
    sitting_date: Optional[datetime],
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    if raw in ("Mr Speaker", "Mdm Speaker"):
        name = _holder_on(SPEAKER_TERMS, sitting_date)
    elif raw.startswith(("Mr Deputy Speaker", "The Deputy Speaker")):
        # "Mr Deputy Speaker (Mr Matthias Yao Chih)" names the person; a bare string
        # falls back to the one holder in office that day.
        named = re.search(r"\(([^)]+)\)", raw)
        name = (
            normalize_name(strip_title(named.group(1).strip()))
            if named
            else _holder_on(DEPUTY_SPEAKER_TERMS, sitting_date)
        )
    else:
        return None
    if not name:
        return None
    canonical, resolved_parl = _resolve_with_parliament_fallback(
        name, parliament, lookups, speaker_id_lookup
    )
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
    for fallback in COLONIAL_PARLIAMENT_FALLBACKS:
        candidate = resolve_canonical_name(name, fallback, lookups)
        if candidate and (candidate, fallback) in speaker_id_lookup:
            return candidate, fallback
    return None, parliament


def _resolve_attendance_speaker_id(
    speaker_name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    speaker_id = speaker_id_lookup.get((speaker_name, parliament))
    if speaker_id:
        return speaker_id
    name = normalize_name(strip_title(speaker_name))
    canonical, parliament = _resolve_with_parliament_fallback(
        name, parliament, lookups, speaker_id_lookup
    )
    return speaker_id_lookup.get((canonical, parliament)) if canonical else None


def _resolve_speech_speaker_id(
    speaker: str,
    parliament: int,
    sitting_date: Optional[datetime],
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    if speaker in NON_SPEAKERS or speaker.startswith("(") or speaker.startswith("_"):
        return None

    raw = speaker.rstrip(":").strip()

    if raw in ("Mr Speaker", "Mdm Speaker") or raw.startswith(
        ("Mr Deputy Speaker", "The Deputy Speaker")
    ):
        # Presiding officers never go through the name cascade.
        return _resolve_presiding_officer(
            raw, parliament, sitting_date, lookups, speaker_id_lookup
        )

    # Chief Minister (colonial era): Marshall or Lim by sitting date.
    if raw == "The Chief Minister" and parliament in (0, 1, 2, 3):
        cm_name = _holder_on(CHIEF_MINISTER_TERMS, sitting_date)
        if not cm_name:
            return None
        cm_canonical, cm_parl = _resolve_with_parliament_fallback(
            cm_name, 0, lookups, speaker_id_lookup
        )
        return speaker_id_lookup.get((cm_canonical, cm_parl)) if cm_canonical else None

    role_key: Optional[tuple[str, int]] = (
        (raw, parliament) if parliament != 0 else None
    )
    if role_key is None:
        for fb in COLONIAL_PARLIAMENT_FALLBACKS:
            if (raw, fb) in ROLE_ONLY_SPEAKERS:
                role_key = (raw, fb)
                break
    if role_key and role_key in ROLE_ONLY_SPEAKERS:
        # Role-only strings are never resolvable via the name cascade.
        role_name = ROLE_ONLY_SPEAKERS[role_key]
        role_canonical, role_parl = _resolve_with_parliament_fallback(
            role_name, role_key[1], lookups, speaker_id_lookup
        )
        return speaker_id_lookup.get((role_canonical, role_parl)) if role_canonical else None

    parens = list(re.finditer(r"\(([^)]+)\)", raw))
    if parens:
        title_paren = next(
            (m for m in reversed(parens) if _paren_contains_title(m)),
            None,
        )
        if title_paren:
            raw = title_paren.group(1).strip()
        else:
            raw = raw[: parens[0].start()].strip()
    raw = re.sub(r"^(Mr|Mrs|Dr|Ms|Mdm)([A-Z])", r"\1 \2", raw)
    raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
    name = normalize_name(strip_title(raw))
    if not name:
        return None

    canonical, parliament = _resolve_with_parliament_fallback(
        name, parliament, lookups, speaker_id_lookup
    )
    return speaker_id_lookup.get((canonical, parliament)) if canonical else None


def resolve_attendance_rows(
    rows: Iterable[tuple[int, Optional[str], Optional[int], Optional[int]]],
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> dict[int, int]:
    """Map attendance id -> speaker id for every row the cascade can resolve.
    Rows are (id, speaker_name, sitting.parlement_no, sitting.volume_no)."""
    memo: dict[tuple[str, int], Optional[int]] = {}
    updates: dict[int, int] = {}
    total = 0
    for attendance_id, speaker_name, parlement_no, volume_no in rows:
        total += 1
        if not speaker_name:
            continue
        parliament = (
            parlement_no if parlement_no is not None else VOLUME_TO_PARLIAMENT.get(volume_no)
        )
        if parliament is None:
            continue
        key = (speaker_name, parliament)
        if key not in memo:
            memo[key] = _resolve_attendance_speaker_id(
                speaker_name, parliament, lookups, speaker_id_lookup
            )
        if memo[key]:
            updates[attendance_id] = memo[key]
    logger.info(f"Attendance: set speaker_id on {len(updates)}/{total} records")
    return updates


def resolve_speech_rows(
    rows: Iterable[tuple[int, Optional[str], int, Optional[datetime]]],
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> dict[int, int]:
    """Map speech id -> speaker id for every row the cascade can resolve.
    Rows are (id, speaker, report.parliament_number, report.sitting_date)."""
    memo: dict[tuple[str, int, Optional[datetime]], Optional[int]] = {}
    updates: dict[int, int] = {}
    total = 0
    for speech_id, speaker, parliament, sitting_date in rows:
        total += 1
        if not speaker:
            continue
        date_key = sitting_date if speaker.startswith(_DATE_DEPENDENT_ROLES) else None
        key = (speaker, parliament, date_key)
        if key not in memo:
            memo[key] = _resolve_speech_speaker_id(
                speaker, parliament, sitting_date, lookups, speaker_id_lookup
            )
        if memo[key]:
            updates[speech_id] = memo[key]
    logger.info(f"Speech: set speaker_id on {len(updates)}/{total} records")
    return updates


def _write_in_batches(set_speaker_ids_bulk, updates: dict[int, int]) -> None:
    items = list(updates.items())
    for start in range(0, len(items), _WRITE_BATCH):
        set_speaker_ids_bulk(dict(items[start : start + _WRITE_BATCH]))


def populate_speaker_links(session: Session) -> None:
    speakers = CRUDSpeaker(session).get_all()
    speaker_id_lookup = {
        (s.name, s.parliament_number): s.id for s in speakers if s.id is not None
    }
    lookups = build_speaker_lookups(speakers)

    crud_attendance = CRUDAttendance(session)
    attendance_updates = resolve_attendance_rows(
        crud_attendance.get_unresolved_speaker_info(), lookups, speaker_id_lookup
    )
    _write_in_batches(crud_attendance.set_speaker_ids_bulk, attendance_updates)
    session.commit()

    crud_speech = CRUDSpeech(session)
    speech_updates = resolve_speech_rows(
        crud_speech.get_unresolved_speaker_info(), lookups, speaker_id_lookup
    )
    _write_in_batches(crud_speech.set_speaker_ids_bulk, speech_updates)
    session.commit()

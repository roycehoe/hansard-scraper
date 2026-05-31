import re

from sqlmodel import Session, select

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

    # Collective references, presiding-officer announcements, and markdown artifacts
    # that are never in the Mp table. Skip before expensive resolution.
    _NON_SPEAKERS = {
        "An hon. Member", "Some hon. Members", "Non-Residents",
        "Tributes by Leader of the House and Opposition Leaders",
    }

    updated = 0
    for speech, report in rows:
        if not speech.speaker:
            continue
        spk = speech.speaker
        if spk in _NON_SPEAKERS:
            continue
        if spk.startswith("(") or spk.startswith("_"):
            continue
        parliament = report.parliament_number
        # Strip trailing colon, then handle parenthetical in speaker string:
        # - role+name "The Minister (Mr Name)" → use the inner name directly
        # - constituency suffix "Dr Tan (Ayer Rajah)" → strip the parenthetical
        _INNER_TITLE = re.compile(
            r"^(?:Mr|Mrs|Dr|Miss|Ms|Mdm|Prof|Madam|Inche|Encik|Tuan Haji|Haji)\b"
        )
        raw = speech.speaker.rstrip(":").strip()
        m = re.search(r"\s*\(([^)]+)\)\s*$", raw)
        if m:
            inner = m.group(1).strip()
            if _INNER_TITLE.match(inner):
                raw = inner  # role+name: resolve the person named inside parens
            else:
                raw = raw[: m.start()]  # constituency/descriptor: strip it
        # Normalize "Mr." / "Dr." / "Mrs." OCR artifacts after any parens extraction.
        raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
        name = strip_title(raw)
        name = normalize_name(name)
        if not name:
            continue
        canonical = resolve_canonical_name(name, parliament)
        # parliament_number=0 means the report's volume wasn't mapped to a parliament.
        # These speeches are from the colonial/LA era; MPs are stored at parliaments 1-3.
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
            speech.mp_id = mp_id
            session.add(speech)
            updated += 1

    session.commit()
    logger.info(f"Speech: set mp_id on {updated}/{len(rows)} records")


def populate_mp_links(session: Session) -> None:
    mp_id_lookup = _build_mp_id_lookup(session)
    _populate_attendance_mp_ids(session, mp_id_lookup)
    _populate_speech_mp_ids(session, mp_id_lookup)

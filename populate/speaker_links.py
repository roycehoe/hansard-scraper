import re
from datetime import date, datetime
from typing import Iterable, Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from database.report import Report
from logs import logger
from populate.speaker_resolution_constants import (
    COLONIAL_PARLIAMENT_FALLBACKS,
    DATED_ROLE_TERMS,
    DEPUTY_SPEAKER_TERMS,
    DEPUTY_SPEAKER_WOMEN,
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
from services.role_context import (
    BARE_DEPUTY_RE,
    CARRIED_ROLES,
    CHAIRMAN_RE,
    carried_role_names,
    chairman_names,
    deputy_speaker_names,
    deputy_speaker_names_in_text,
)

_WRITE_BATCH = 50_000
_REPORT_BATCH = 200

# Only these roles resolve by sitting date; every other string resolves the same
# way for every sitting in a parliament, so it is memoised on (string, parliament).
_DATE_DEPENDENT_ROLES = (
    "The Chief Minister",
    "The Prime Minister",
    "Mr Speaker",
    "Mdm Speaker",
    "Mr Deputy Speaker",
    "Mdm Deputy Speaker",
    "Mdm DeputySpeaker",
    "The Deputy Speaker",
)

_DEPUTY_SPEAKER_LABELS = ("Mr Deputy Speaker", "Mdm Deputy Speaker", "Mdm DeputySpeaker", "The Deputy Speaker")

_TITLED_RE = re.compile(r"^(?:Mr|Mrs|Ms|Mdm|Dr|Miss|Inche|Encik|Assoc|Prof|Er)\b")


def _preclean(raw: str) -> str:
    """Remove parse debris from a speaker string before resolution: list numbers and
    stray punctuation, rank qualifiers such as "(NS)", a trailing "Mr Speaker," that
    belongs to the transcript, an unclosed parenthesis, an inverted two-part name and
    a label printed twice."""
    raw = raw.replace("\ufeff", "").strip()
    raw = re.sub(r"^\d+\\?\.\s*", "", raw)
    raw = re.sub(r"^\.\s+", "", raw)
    raw = re.sub(r"\bAssoc\.Prof\.", "Assoc. Prof.", raw)
    raw = re.sub(r"\s*[\[(](?:NS|Res)[\])]\s*", " ", raw)
    raw = re.sub(r"\s+Mr Speaker,?$", "", raw)
    raw = re.sub(r"\s+", " ", raw).rstrip(";, ").strip()
    if raw.count("(") > raw.count(")"):
        cut = raw.rfind("(")
        inner = raw[cut + 1 :].strip()
        raw = f"{raw[:cut]}({inner})" if _TITLED_RE.match(inner) else raw[:cut].strip()
    inverted = re.match(r"^([A-Z][a-z]+), ([A-Z][a-z]+)$", raw)
    if inverted:
        raw = f"{inverted.group(2)} {inverted.group(1)}"
    doubled = re.match(r"^(.{6,}?)\s+\1$", raw)
    return doubled.group(1) if doubled else raw


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
    elif raw.startswith(_DEPUTY_SPEAKER_LABELS):
        # "Mr Deputy Speaker (Mr Matthias Yao Chih)" names the person; a bare string
        # falls back to the one holder in office that day.
        # "Mdm" names the only woman holding the office in her window; a bare "Mr" on a
        # two-holder day is settled from the report by `_populate_deputy_speaker_links`.
        named = re.search(r"\(([^)]+)\)", raw)
        terms = (
            [t for t in DEPUTY_SPEAKER_TERMS if t[2] in DEPUTY_SPEAKER_WOMEN]
            if raw.startswith("Mdm")
            else DEPUTY_SPEAKER_TERMS
        )
        name = (
            normalize_name(strip_title(named.group(1).strip()))
            if named
            else _holder_on(terms, sitting_date)
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

    raw = _preclean(speaker.rstrip(":").strip())

    if raw in ("Mr Speaker", "Mdm Speaker") or raw.startswith(_DEPUTY_SPEAKER_LABELS):
        # Presiding officers never go through the name cascade.
        return _resolve_presiding_officer(
            raw, parliament, sitting_date, lookups, speaker_id_lookup
        )

    # Roles whose holder changed within a parliament resolve by sitting date.
    if raw in DATED_ROLE_TERMS:
        holder = _holder_on(DATED_ROLE_TERMS[raw], sitting_date)
        if not holder:
            return None
        canonical, parl = _resolve_with_parliament_fallback(
            holder, parliament, lookups, speaker_id_lookup
        )
        return speaker_id_lookup.get((canonical, parl)) if canonical else None

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


def _populate_role_context_links(
    session: Session,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> None:
    """Link role-only strings that the report itself resolves: "The Chairman" from the
    chair annotations, closing line and header, and carried roles from an earlier
    row that names the holder."""
    crud_speech = CRUDSpeech(session)
    pattern = "|".join([CHAIRMAN_RE.pattern] + [f"^{re.escape(role)}$" for role in CARRIED_ROLES])
    report_ids = crud_speech.get_report_ids_with_unlinked_speaker(pattern)
    memo: dict[tuple[str, int, Optional[datetime]], Optional[int]] = {}
    updates: dict[int, int] = {}
    total = 0
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch = report_ids[start : start + _REPORT_BATCH]
        reports = {r.id: r for r in CRUDReport(session).get_by_ids(batch)}
        rows_by_report: dict[int, list] = {}
        for row in crud_speech.get_rows_by_report_ids(batch):
            rows_by_report.setdefault(row[4], []).append(row)
        for report_id, rows in rows_by_report.items():
            report = reports[report_id]
            unlinked = {row[0] for row in rows if row[5] is None}
            speech_rows = [row[:4] for row in rows]
            names = chairman_names(report.markdown_content or "", speech_rows)
            names.update(carried_role_names(speech_rows))
            for speech_id, name in names.items():
                if speech_id not in unlinked:
                    continue
                total += 1
                key = (name, report.parliament_number, report.sitting_date)
                if key not in memo:
                    memo[key] = _resolve_speech_speaker_id(
                        name, report.parliament_number, report.sitting_date, lookups, speaker_id_lookup
                    )
                if memo[key]:
                    updates[speech_id] = memo[key]
    _write_in_batches(crud_speech.set_speaker_ids_bulk, updates)
    session.commit()
    logger.info(f"Speech: set speaker_id on {len(updates)}/{total} role-context records")


def _name_to_speaker_id(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    canonical, resolved_parl = _resolve_with_parliament_fallback(
        normalize_name(strip_title(name)), parliament, lookups, speaker_id_lookup
    )
    return speaker_id_lookup.get((canonical, resolved_parl)) if canonical else None


def _populate_deputy_speaker_links(
    session: Session,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> None:
    """Link bare "Mr Deputy Speaker" rows on days with two Deputies in office, from the report.
    With one man and one woman in office the printed "Mr" leaves the man, unless the report
    shows the woman taking part. With two men the row links only when the chair annotation
    before it, or a "Mr Deputy Speaker (Name)" speaker row in the report, names one of them
    and nothing else printed that day (other reports, the sitting text) names the other."""
    crud_speech, crud_report = CRUDSpeech(session), CRUDReport(session)
    report_ids = crud_speech.get_report_ids_with_unlinked_speaker(BARE_DEPUTY_RE.pattern)
    updates: dict[int, int] = {}
    total = 0
    text_ids: dict[object, set[int]] = {}  # holder ids named by a sitting or report text; a date has one parliament

    def ids_of(names: Iterable[str], parliament: int) -> set[int]:
        found = (_name_to_speaker_id(n, parliament, lookups, speaker_id_lookup) for n in names)
        return {i for i in found if i is not None}

    def day_ids(key: object, text: str, parliament: int) -> set[int]:
        if key not in text_ids:
            text_ids[key] = ids_of(deputy_speaker_names_in_text(text), parliament)
        return text_ids[key]

    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch = report_ids[start : start + _REPORT_BATCH]
        reports = {r.id: r for r in crud_report.get_by_ids(batch)}
        rows_by_report: dict[int, list] = {}
        for row in crud_speech.get_rows_by_report_ids(batch):
            rows_by_report.setdefault(row[4], []).append(row)
        pending = []  # (report, two-man candidates by speech id, holder ids)
        for report_id, rows in rows_by_report.items():
            report = reports[report_id]
            bare = [r for r in rows if r[5] is None and BARE_DEPUTY_RE.match(r[2] or "")]
            day = report.sitting_date.date()
            holders = [name for first, last, name in DEPUTY_SPEAKER_TERMS if first <= day <= last]
            if not bare or len(holders) != 2:
                continue
            total += len(bare)
            parl = report.parliament_number
            holder_ids = {h: _name_to_speaker_id(h, parl, lookups, speaker_id_lookup) for h in holders}
            if None in holder_ids.values():
                continue
            valid = set(holder_ids.values())
            row_names, labelled, mentioned = deputy_speaker_names(
                report.markdown_content or "", [r[:4] for r in rows]
            )
            named = ids_of(mentioned, parl) & valid
            if len(named) > 1:
                continue
            men = [h for h in holders if h not in DEPUTY_SPEAKER_WOMEN]
            if len(men) == 1:
                if named <= {holder_ids[men[0]]}:
                    updates.update({r[0]: holder_ids[men[0]] for r in bare})
                continue
            if len(men) != 2:
                continue
            labelled_ids = ids_of(labelled, parl) & valid
            candidates = {}
            for r in bare:
                if r[0] in row_names:
                    found = ids_of([row_names[r[0]]], parl) & valid
                    candidate = next(iter(found)) if found else None
                else:
                    candidate = next(iter(labelled_ids)) if len(labelled_ids) == 1 else None
                if candidate is not None:
                    candidates[r[0]] = candidate
            if candidates:
                pending.append((report, candidates, valid))
        if not pending:
            continue
        dates = {r.sitting_date for r, _, _ in pending}
        by_date: dict[datetime, list[Report]] = {}
        for other in crud_report.get_by_sitting_dates(list(dates)):
            by_date.setdefault(other.sitting_date, []).append(other)
        sittings = CRUDSitting(session).get_markdown_by_dates(
            [f"{d.day}-{d.month}-{d.year}" for d in dates]
        )
        for report, candidates, valid in pending:
            d, parl = report.sitting_date, report.parliament_number
            named_today = day_ids(("sitting", d), sittings.get(f"{d.day}-{d.month}-{d.year}", ""), parl)
            for other in by_date.get(d, []):
                if other.id != report.id:
                    named_today = named_today | day_ids(other.id, other.markdown_content or "", parl)
            for speech_id, candidate in candidates.items():
                if not (named_today & valid) - {candidate}:
                    updates[speech_id] = candidate
    _write_in_batches(crud_speech.set_speaker_ids_bulk, updates)
    session.commit()
    logger.info(f"Speech: set speaker_id on {len(updates)}/{total} deputy-speaker records")


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
    _populate_role_context_links(session, lookups, speaker_id_lookup)
    _populate_deputy_speaker_links(session, lookups, speaker_id_lookup)

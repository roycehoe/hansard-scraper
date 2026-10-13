import re
from datetime import date, datetime
from typing import Callable, Iterable, Optional, Sequence

from sqlmodel import Session

from crud.attendance import AttendanceSpeakerRow, CRUDAttendance
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechRow, SpeechSpeakerRow
from database.report import Report
from logs import logger
from populate.speaker_resolution_constants import (
    COLONIAL_PARLIAMENT_FALLBACKS,
    DATED_ROLE_TERMS,
    DEPUTY_SPEAKER_TERMS,
    DEPUTY_SPEAKER_WOMEN,
    HEAD_OF_STATE_TERMS,
    NON_SPEAKERS,
    ROLE_ONLY_SPEAKERS,
    SPEAKER_TERMS,
)
from services.attendance import (
    VOLUME_TO_PARLIAMENT,
    SpeakerLookups,
    build_speaker_lookups,
    resolve_canonical_name,
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
from utils.names import (
    normalize_name,
    strip_title,
)

_WRITE_BATCH = 50_000
_REPORT_BATCH = 200
_DEPUTY_SPEAKER_PAIR_SIZE = 2
_SPEAKER_LABELS = ("Mr Speaker", "Mdm Speaker")

# NOTE: only these roles resolve by sitting date; every other string is memoised on (string, parliament).
_DATE_DEPENDENT_ROLES = (
    "The Chief Minister",
    "The Prime Minister",
    *_SPEAKER_LABELS,
    "Mr Deputy Speaker",
    "Mdm Deputy Speaker",
    "Mdm DeputySpeaker",
    "The Deputy Speaker",
)

_DEPUTY_SPEAKER_LABELS = ("Mr Deputy Speaker", "Mdm Deputy Speaker", "Mdm DeputySpeaker", "The Deputy Speaker")

_LEADING_LIST_NUMBER_RE = re.compile(r"^\d+\\?\.\s*")
_LEADING_DOT_RE = re.compile(r"^\.\s+")
_ASSOC_PROF_RE = re.compile(r"\bAssoc\.Prof\.")
_RANK_QUALIFIER_RE = re.compile(r"\s*[\[(](?:NS|Res)[\])]\s*")
_TRAILING_MR_SPEAKER_RE = re.compile(r"\s+Mr Speaker,?$")
_WHITESPACE_RE = re.compile(r"\s+")
_INVERTED_NAME_RE = re.compile(r"^([A-Z][a-z]+), ([A-Z][a-z]+)$")
_DOUBLED_LABEL_RE = re.compile(r"^(.{6,}?)\s+\1$")
_PARENTHESIS_RE = re.compile(r"\(([^)]+)\)")
_TITLE_DOT_PREFIX_RE = re.compile(r"^(Mr|Mrs|Dr|Ms)\.\s+")
_GLUED_TITLE_RE = re.compile(r"^(Mr|Mrs|Dr|Ms|Mdm)([A-Z])")
_TITLED_RE = re.compile(r"^(?:Mr|Mrs|Ms|Mdm|Dr|Miss|Inche|Encik|Assoc|Prof|Er)\b")

_ADDRESS_TITLES = ("GOVERNOR'S ADDRESS", "PRESIDENT'S ADDRESS", "YANG DI-PERTUAN NEGARA'S SPEECH")


def _preclean(raw: str) -> str:
    raw = raw.replace("\ufeff", "").strip()
    raw = _LEADING_LIST_NUMBER_RE.sub("", raw)
    raw = _LEADING_DOT_RE.sub("", raw)
    raw = _ASSOC_PROF_RE.sub("Assoc. Prof.", raw)
    raw = _RANK_QUALIFIER_RE.sub(" ", raw)
    raw = _TRAILING_MR_SPEAKER_RE.sub("", raw)
    raw = _WHITESPACE_RE.sub(" ", raw).rstrip(";, ").strip()
    if raw.count("(") > raw.count(")"):
        cut = raw.rfind("(")
        inner = raw[cut + 1 :].strip()
        raw = f"{raw[:cut]}({inner})" if _TITLED_RE.match(inner) else raw[:cut].strip()
    inverted = _INVERTED_NAME_RE.match(raw)
    if inverted is not None:
        raw = f"{inverted.group(2)} {inverted.group(1)}"
    doubled = _DOUBLED_LABEL_RE.match(raw)
    return doubled.group(1) if doubled is not None else raw


def _is_title_in_parentheses(match: re.Match) -> bool:
    inner = _TITLE_DOT_PREFIX_RE.sub(r"\1 ", match.group(1).strip())
    return strip_title(inner) != inner


def _get_holder_on(
    terms: Sequence[tuple[date, date, str]], sitting_date: Optional[datetime]
) -> Optional[str]:
    if sitting_date is None:
        return None
    day = sitting_date.date()
    holders = [name for first, last, name in terms if first <= day <= last]
    return holders[0] if len(holders) == 1 else None


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


def _get_presiding_officer_id(
    name: Optional[str],
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    if not name:
        return None
    canonical, resolved_parliament = _resolve_with_parliament_fallback(
        name, parliament, lookups, speaker_id_lookup
    )
    return speaker_id_lookup.get((canonical, resolved_parliament)) if canonical else None


def _resolve_presiding_officer(
    raw: str,
    parliament: int,
    sitting_date: Optional[datetime],
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    if raw in _SPEAKER_LABELS:
        return _get_presiding_officer_id(
            _get_holder_on(SPEAKER_TERMS, sitting_date), parliament, lookups, speaker_id_lookup
        )
    if raw.startswith(_DEPUTY_SPEAKER_LABELS):
        named_match = _PARENTHESIS_RE.search(raw)
        terms = (
            [term for term in DEPUTY_SPEAKER_TERMS if term[2] in DEPUTY_SPEAKER_WOMEN]
            if raw.startswith("Mdm")
            else DEPUTY_SPEAKER_TERMS
        )
        name = (
            normalize_name(strip_title(named_match.group(1).strip()))
            if named_match is not None
            else _get_holder_on(terms, sitting_date)
        )
        return _get_presiding_officer_id(name, parliament, lookups, speaker_id_lookup)
    return None


def _resolve_attendance_speaker_id(
    speaker_name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    speaker_id = speaker_id_lookup.get((speaker_name, parliament))
    if speaker_id is not None:
        return speaker_id
    name = normalize_name(strip_title(speaker_name))
    canonical, parliament = _resolve_with_parliament_fallback(
        name, parliament, lookups, speaker_id_lookup
    )
    return speaker_id_lookup.get((canonical, parliament)) if canonical else None


def _get_role_key(raw: str, parliament: int) -> Optional[tuple[str, int]]:
    if parliament != 0:
        return (raw, parliament)
    for fallback_parliament in COLONIAL_PARLIAMENT_FALLBACKS:
        if (raw, fallback_parliament) in ROLE_ONLY_SPEAKERS:
            return (raw, fallback_parliament)
    return None


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

    if raw in _SPEAKER_LABELS or raw.startswith(_DEPUTY_SPEAKER_LABELS):
        return _resolve_presiding_officer(
            raw, parliament, sitting_date, lookups, speaker_id_lookup
        )

    if raw in DATED_ROLE_TERMS:
        holder = _get_holder_on(DATED_ROLE_TERMS[raw], sitting_date)
        if not holder:
            return None
        canonical, resolved_parliament = _resolve_with_parliament_fallback(
            holder, parliament, lookups, speaker_id_lookup
        )
        return speaker_id_lookup.get((canonical, resolved_parliament)) if canonical else None

    role_key = _get_role_key(raw, parliament)
    if role_key is not None and role_key in ROLE_ONLY_SPEAKERS:
        role_name = ROLE_ONLY_SPEAKERS[role_key]
        role_canonical, role_parliament = _resolve_with_parliament_fallback(
            role_name, role_key[1], lookups, speaker_id_lookup
        )
        return speaker_id_lookup.get((role_canonical, role_parliament)) if role_canonical else None

    parenthesised_matches = list(_PARENTHESIS_RE.finditer(raw))
    if parenthesised_matches:
        title_match = next(
            (match for match in reversed(parenthesised_matches) if _is_title_in_parentheses(match)),
            None,
        )
        if title_match is not None:
            raw = title_match.group(1).strip()
        else:
            raw = raw[: parenthesised_matches[0].start()].strip()
    raw = _GLUED_TITLE_RE.sub(r"\1 \2", raw)
    raw = _TITLE_DOT_PREFIX_RE.sub(r"\1 ", raw)
    name = normalize_name(strip_title(raw))
    if not name:
        return None

    canonical, parliament = _resolve_with_parliament_fallback(
        name, parliament, lookups, speaker_id_lookup
    )
    return speaker_id_lookup.get((canonical, parliament)) if canonical else None


def resolve_attendance_rows(
    attendance_rows: Iterable[AttendanceSpeakerRow],
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> dict[int, int]:
    key_to_speaker_id: dict[tuple[str, int], Optional[int]] = {}
    attendance_id_to_speaker_id: dict[int, int] = {}
    total = 0
    for attendance_row in attendance_rows:
        total += 1
        if not attendance_row.speaker_name:
            continue
        parliament = (
            attendance_row.parlement_no if attendance_row.parlement_no is not None else VOLUME_TO_PARLIAMENT.get(attendance_row.volume_no)
        )
        if parliament is None:
            continue
        key = (attendance_row.speaker_name, parliament)
        if key not in key_to_speaker_id:
            key_to_speaker_id[key] = _resolve_attendance_speaker_id(
                attendance_row.speaker_name, parliament, lookups, speaker_id_lookup
            )
        if key_to_speaker_id[key] is not None:
            attendance_id_to_speaker_id[attendance_row.id] = key_to_speaker_id[key]
    logger.info(f"Attendance: set speaker_id on {len(attendance_id_to_speaker_id)}/{total} records")
    return attendance_id_to_speaker_id


def resolve_speech_rows(
    speech_rows: Iterable[SpeechSpeakerRow],
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> dict[int, int]:
    key_to_speaker_id: dict[tuple[str, int, Optional[datetime]], Optional[int]] = {}
    speech_id_to_speaker_id: dict[int, int] = {}
    total = 0
    for speech_row in speech_rows:
        total += 1
        if not speech_row.speaker:
            continue
        date_key = speech_row.sitting_date if speech_row.speaker.startswith(_DATE_DEPENDENT_ROLES) else None
        key = (speech_row.speaker, speech_row.parliament_number, date_key)
        if key not in key_to_speaker_id:
            key_to_speaker_id[key] = _resolve_speech_speaker_id(
                speech_row.speaker, speech_row.parliament_number, speech_row.sitting_date, lookups, speaker_id_lookup
            )
        if key_to_speaker_id[key] is not None:
            speech_id_to_speaker_id[speech_row.id] = key_to_speaker_id[key]
    logger.info(f"Speech: set speaker_id on {len(speech_id_to_speaker_id)}/{total} records")
    return speech_id_to_speaker_id


def _write_in_batches(set_speaker_ids_bulk: Callable[[dict[int, int]], None], id_to_speaker_id: dict[int, int]) -> None:
    items = list(id_to_speaker_id.items())
    for start in range(0, len(items), _WRITE_BATCH):
        set_speaker_ids_bulk(dict(items[start : start + _WRITE_BATCH]))


# NOTE: a bare head-of-state string is the holder only in the Address itself; the same strings in addenda and adjournment reports are parser errors and stay unlinked.
def _get_head_of_state_names(title: str, sitting_date: datetime, speech_rows: list[SpeechRow]) -> dict[int, str]:
    if not title.upper().startswith(_ADDRESS_TITLES):
        return {}
    speech_id_to_name = {}
    for speech_row in speech_rows:
        if speech_row.speaker in HEAD_OF_STATE_TERMS:
            holder = _get_holder_on(HEAD_OF_STATE_TERMS[speech_row.speaker], sitting_date)
            if holder:
                speech_id_to_name[speech_row.id] = holder
    return speech_id_to_name


def _get_speaker_id_for_name(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    canonical, resolved_parliament = _resolve_with_parliament_fallback(
        normalize_name(strip_title(name)), parliament, lookups, speaker_id_lookup
    )
    return speaker_id_lookup.get((canonical, resolved_parliament)) if canonical else None


def _get_sitting_date_key(sitting_date: datetime) -> str:
    return f"{sitting_date.day}-{sitting_date.month}-{sitting_date.year}"


def _get_speaker_ids_for_names(
    names: Iterable[str],
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> set[int]:
    found = (_get_speaker_id_for_name(name, parliament, lookups, speaker_id_lookup) for name in names)
    return {speaker_id for speaker_id in found if speaker_id is not None}


def _get_day_speaker_ids(
    key: object,
    text: str,
    parliament: int,
    text_key_to_speaker_ids: dict[object, set[int]],
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> set[int]:
    if key not in text_key_to_speaker_ids:
        text_key_to_speaker_ids[key] = _get_speaker_ids_for_names(
            deputy_speaker_names_in_text(text), parliament, lookups, speaker_id_lookup
        )
    return text_key_to_speaker_ids[key]


def _populate_role_context_links(
    session: Session,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> None:
    pattern = "|".join(
        [CHAIRMAN_RE.pattern] + [f"^{re.escape(role)}$" for role in (*CARRIED_ROLES, *HEAD_OF_STATE_TERMS)]
    )
    report_ids = CRUDSpeech(session).get_report_ids_by_speaker_id_null_and_speaker_regex(pattern)
    key_to_speaker_id: dict[tuple[str, int, Optional[datetime]], Optional[int]] = {}
    speech_id_to_speaker_id: dict[int, int] = {}
    total = 0
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch = report_ids[start : start + _REPORT_BATCH]
        report_id_to_report = {report.id: report for report in CRUDReport(session).get_by_ids(batch)}
        report_id_to_speech_rows: dict[int, list[SpeechRow]] = {}
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(batch):
            report_id_to_speech_rows.setdefault(speech_row.report_id, []).append(speech_row)
        for report_id, speech_rows in report_id_to_speech_rows.items():
            report = report_id_to_report[report_id]
            unlinked = {speech_row.id for speech_row in speech_rows if speech_row.speaker_id is None}
            speech_id_to_name = chairman_names(report.markdown_content or "", speech_rows)
            speech_id_to_name.update(carried_role_names(speech_rows))
            speech_id_to_name.update(_get_head_of_state_names(report.title, report.sitting_date, speech_rows))
            for speech_id, name in speech_id_to_name.items():
                if speech_id not in unlinked:
                    continue
                total += 1
                key = (name, report.parliament_number, report.sitting_date)
                if key not in key_to_speaker_id:
                    key_to_speaker_id[key] = _resolve_speech_speaker_id(
                        name, report.parliament_number, report.sitting_date, lookups, speaker_id_lookup
                    )
                if key_to_speaker_id[key] is not None:
                    speech_id_to_speaker_id[speech_id] = key_to_speaker_id[key]
    _write_in_batches(CRUDSpeech(session).set_speaker_ids_bulk, speech_id_to_speaker_id)
    session.commit()
    logger.info(f"Speech: set speaker_id on {len(speech_id_to_speaker_id)}/{total} role-context records")


# NOTE: with one man and one woman in office the "Mr" row goes to the man unless the report shows the woman taking part. With two men the row links only when the report names one of them and nothing else printed that day names the other.
def _populate_deputy_speaker_links(
    session: Session,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> None:
    report_ids = CRUDSpeech(session).get_report_ids_by_speaker_id_null_and_speaker_regex(BARE_DEPUTY_RE.pattern)
    speech_id_to_speaker_id: dict[int, int] = {}
    total = 0
    text_key_to_speaker_ids: dict[object, set[int]] = {}

    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch = report_ids[start : start + _REPORT_BATCH]
        report_id_to_report = {report.id: report for report in CRUDReport(session).get_by_ids(batch)}
        report_id_to_speech_rows: dict[int, list[SpeechRow]] = {}
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(batch):
            report_id_to_speech_rows.setdefault(speech_row.report_id, []).append(speech_row)
        pending_reports = []
        for report_id, speech_rows in report_id_to_speech_rows.items():
            report = report_id_to_report[report_id]
            bare_deputy_rows = [speech_row for speech_row in speech_rows if speech_row.speaker_id is None and BARE_DEPUTY_RE.match(speech_row.speaker or "")]
            day = report.sitting_date.date()
            holders = [name for first, last, name in DEPUTY_SPEAKER_TERMS if first <= day <= last]
            if not bare_deputy_rows or len(holders) != _DEPUTY_SPEAKER_PAIR_SIZE:
                continue
            total += len(bare_deputy_rows)
            parliament = report.parliament_number
            holder_to_speaker_id = {holder: _get_speaker_id_for_name(holder, parliament, lookups, speaker_id_lookup) for holder in holders}
            if None in holder_to_speaker_id.values():
                continue
            valid_holder_ids = set(holder_to_speaker_id.values())
            deputy_names = deputy_speaker_names(report.markdown_content or "", speech_rows)
            named_holder_ids = _get_speaker_ids_for_names(deputy_names.mentioned, parliament, lookups, speaker_id_lookup) & valid_holder_ids
            if len(named_holder_ids) > 1:
                continue
            male_holders = [holder for holder in holders if holder not in DEPUTY_SPEAKER_WOMEN]
            if len(male_holders) == 1:
                if named_holder_ids <= {holder_to_speaker_id[male_holders[0]]}:
                    speech_id_to_speaker_id.update({speech_row.id: holder_to_speaker_id[male_holders[0]] for speech_row in bare_deputy_rows})
                continue
            if len(male_holders) != _DEPUTY_SPEAKER_PAIR_SIZE:
                continue
            labelled_ids = _get_speaker_ids_for_names(deputy_names.labelled, parliament, lookups, speaker_id_lookup) & valid_holder_ids
            speech_id_to_candidate_id = {}
            for speech_row in bare_deputy_rows:
                if speech_row.id in deputy_names.speech_id_to_deputy_name:
                    found = _get_speaker_ids_for_names([deputy_names.speech_id_to_deputy_name[speech_row.id]], parliament, lookups, speaker_id_lookup) & valid_holder_ids
                    candidate = next(iter(found)) if found else None
                else:
                    candidate = next(iter(labelled_ids)) if len(labelled_ids) == 1 else None
                if candidate is not None:
                    speech_id_to_candidate_id[speech_row.id] = candidate
            if speech_id_to_candidate_id:
                pending_reports.append((report, speech_id_to_candidate_id, valid_holder_ids))
        if not pending_reports:
            continue
        dates = {report.sitting_date for report, _, _ in pending_reports}
        sitting_date_to_reports: dict[datetime, list[Report]] = {}
        for other in CRUDReport(session).get_by_sitting_dates(list(dates)):
            sitting_date_to_reports.setdefault(other.sitting_date, []).append(other)
        sitting_date_key_to_markdown = CRUDSitting(session).get_markdown_by_dates(
            [_get_sitting_date_key(sitting_date) for sitting_date in dates]
        )
        for report, speech_id_to_candidate_id, valid_holder_ids in pending_reports:
            sitting_date, parliament = report.sitting_date, report.parliament_number
            named_today = _get_day_speaker_ids(("sitting", sitting_date), sitting_date_key_to_markdown.get(_get_sitting_date_key(sitting_date), ""), parliament, text_key_to_speaker_ids, lookups, speaker_id_lookup)
            for other in sitting_date_to_reports.get(sitting_date, []):
                if other.id != report.id:
                    named_today = named_today | _get_day_speaker_ids(other.id, other.markdown_content or "", parliament, text_key_to_speaker_ids, lookups, speaker_id_lookup)
            for speech_id, candidate in speech_id_to_candidate_id.items():
                if not (named_today & valid_holder_ids) - {candidate}:
                    speech_id_to_speaker_id[speech_id] = candidate
    _write_in_batches(CRUDSpeech(session).set_speaker_ids_bulk, speech_id_to_speaker_id)
    session.commit()
    logger.info(f"Speech: set speaker_id on {len(speech_id_to_speaker_id)}/{total} deputy-speaker records")


def populate_speaker_links(session: Session) -> None:
    speakers = CRUDSpeaker(session).get_all()
    speaker_id_lookup = {
        (speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None
    }
    lookups = build_speaker_lookups(speakers)

    attendance_id_to_speaker_id = resolve_attendance_rows(
        CRUDAttendance(session).get_speaker_rows_by_speaker_id_null(), lookups, speaker_id_lookup
    )
    _write_in_batches(CRUDAttendance(session).set_speaker_ids_bulk, attendance_id_to_speaker_id)
    session.commit()

    speech_id_to_speaker_id = resolve_speech_rows(
        CRUDSpeech(session).get_speaker_rows_by_speaker_id_null(), lookups, speaker_id_lookup
    )
    _write_in_batches(CRUDSpeech(session).set_speaker_ids_bulk, speech_id_to_speaker_id)
    session.commit()
    _populate_role_context_links(session, lookups, speaker_id_lookup)
    _populate_deputy_speaker_links(session, lookups, speaker_id_lookup)

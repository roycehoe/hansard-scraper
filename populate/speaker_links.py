import re
from datetime import datetime
from typing import Callable, Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechRow
from database.report import Report
from logs import logger
from services.attendance import build_speaker_lookups
from services.speaker_link import (
    BARE_DEPUTY_RE,
    CARRIED_ROLES,
    CHAIRMAN_RE,
    SittingText,
    build_sitting_text_from_markdown,
    build_sitting_text_from_sections,
    carried_role_names,
    chairman_names,
    deputy_speaker_names,
    deputy_speaker_names_in_text,
    get_head_of_state_names,
    get_speaker_id_for_name,
    get_speaker_ids_for_names,
    resolve_attendance_rows,
    resolve_speech_rows,
    resolve_speech_speaker_id,
    sitting_deputy_speaker_names,
)
from utils.sitting_dates import get_sitting_date_key
from utils.speaker_resolution import SpeakerLookups
from utils.speaker_resolution_constants import (
    DEPUTY_SPEAKER_TERMS,
    DEPUTY_SPEAKER_WOMEN,
    HEAD_OF_STATE_TERMS,
)

_WRITE_BATCH = 50_000
_REPORT_BATCH = 200
_DEPUTY_SPEAKER_PAIR_SIZE = 2

_ROLE_CONTEXT_PATTERN = "|".join(
    [CHAIRMAN_RE.pattern] + [f"^{re.escape(role)}$" for role in (*CARRIED_ROLES, *HEAD_OF_STATE_TERMS)]
)


def _write_in_batches(set_speaker_ids_bulk: Callable[[dict[int, int]], None], id_to_speaker_id: dict[int, int]) -> None:
    items = list(id_to_speaker_id.items())
    for start in range(0, len(items), _WRITE_BATCH):
        set_speaker_ids_bulk(dict(items[start : start + _WRITE_BATCH]))


def _get_day_speaker_ids(
    key: object,
    text: str,
    parliament: int,
    text_key_to_speaker_ids: dict[object, set[int]],
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> set[int]:
    if key not in text_key_to_speaker_ids:
        text_key_to_speaker_ids[key] = get_speaker_ids_for_names(
            deputy_speaker_names_in_text(text), parliament, lookups, name_parliament_number_to_speaker_id
        )
    return text_key_to_speaker_ids[key]


def _get_role_context_speaker_ids_for_report_ids(
    session: Session,
    report_ids: list[int],
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> dict[int, int]:
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
            speech_id_to_name.update(get_head_of_state_names(report.title, report.sitting_date, speech_rows))
            for speech_id, name in speech_id_to_name.items():
                if speech_id not in unlinked:
                    continue
                total += 1
                key = (name, report.parliament_number, report.sitting_date)
                if key not in key_to_speaker_id:
                    key_to_speaker_id[key] = resolve_speech_speaker_id(
                        name, report.parliament_number, report.sitting_date, lookups, name_parliament_number_to_speaker_id
                    )
                if key_to_speaker_id[key] is not None:
                    speech_id_to_speaker_id[speech_id] = key_to_speaker_id[key]
    logger.info(f"Speech: set speaker_id on {len(speech_id_to_speaker_id)}/{total} role-context records")
    return speech_id_to_speaker_id


def get_role_context_speaker_ids(
    session: Session,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> dict[int, int]:
    report_ids = CRUDSpeech(session).get_report_ids_by_speaker_id_null_and_speaker_regex(_ROLE_CONTEXT_PATTERN)
    return _get_role_context_speaker_ids_for_report_ids(session, report_ids, lookups, name_parliament_number_to_speaker_id)


def _populate_role_context_links(
    session: Session,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> None:
    speech_id_to_speaker_id = get_role_context_speaker_ids(session, lookups, name_parliament_number_to_speaker_id)
    _write_in_batches(CRUDSpeech(session).set_speaker_ids_bulk, speech_id_to_speaker_id)
    session.commit()


def _get_deputy_speaker_ids_for_report_ids(
    session: Session,
    report_ids: list[int],
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> dict[int, int]:
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
            holder_to_speaker_id = {holder: get_speaker_id_for_name(holder, parliament, lookups, name_parliament_number_to_speaker_id) for holder in holders}
            if None in holder_to_speaker_id.values():
                continue
            valid_holder_ids = set(holder_to_speaker_id.values())
            deputy_names = deputy_speaker_names(report.markdown_content or "", speech_rows)
            named_holder_ids = get_speaker_ids_for_names(deputy_names.mentioned, parliament, lookups, name_parliament_number_to_speaker_id) & valid_holder_ids
            if len(named_holder_ids) > 1:
                continue
            male_holders = [holder for holder in holders if holder not in DEPUTY_SPEAKER_WOMEN]
            if len(male_holders) == 1:
                if named_holder_ids <= {holder_to_speaker_id[male_holders[0]]}:
                    speech_id_to_speaker_id.update({speech_row.id: holder_to_speaker_id[male_holders[0]] for speech_row in bare_deputy_rows})
                continue
            if len(male_holders) != _DEPUTY_SPEAKER_PAIR_SIZE:
                continue
            labelled_ids = get_speaker_ids_for_names(deputy_names.labelled, parliament, lookups, name_parliament_number_to_speaker_id) & valid_holder_ids
            speech_id_to_candidate_id = {}
            for speech_row in bare_deputy_rows:
                if speech_row.id in deputy_names.speech_id_to_deputy_name:
                    found = get_speaker_ids_for_names([deputy_names.speech_id_to_deputy_name[speech_row.id]], parliament, lookups, name_parliament_number_to_speaker_id) & valid_holder_ids
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
        sitting_date_key_to_markdown = {
            date_markdown_row.sitting_date: date_markdown_row.markdown_content
            for date_markdown_row in CRUDSitting(session).get_date_markdown_rows_by_sitting_dates_and_markdown_content_not_null(
                [get_sitting_date_key(sitting_date) for sitting_date in dates]
            )
        }
        for report, speech_id_to_candidate_id, valid_holder_ids in pending_reports:
            sitting_date, parliament = report.sitting_date, report.parliament_number
            named_today = _get_day_speaker_ids(("sitting", sitting_date), sitting_date_key_to_markdown.get(get_sitting_date_key(sitting_date), ""), parliament, text_key_to_speaker_ids, lookups, name_parliament_number_to_speaker_id)
            for other in sitting_date_to_reports.get(sitting_date, []):
                if other.id != report.id:
                    named_today = named_today | _get_day_speaker_ids(other.id, other.markdown_content or "", parliament, text_key_to_speaker_ids, lookups, name_parliament_number_to_speaker_id)
            for speech_id, candidate in speech_id_to_candidate_id.items():
                if not (named_today & valid_holder_ids) - {candidate}:
                    speech_id_to_speaker_id[speech_id] = candidate
    logger.info(f"Speech: set speaker_id on {len(speech_id_to_speaker_id)}/{total} deputy-speaker records")
    return speech_id_to_speaker_id


# NOTE: with one man and one woman in office the "Mr" row goes to the man unless the report shows the woman taking part. With two men the row links only when the report names one of them and nothing else printed that day names the other.
def get_deputy_speaker_ids(
    session: Session,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> dict[int, int]:
    report_ids = CRUDSpeech(session).get_report_ids_by_speaker_id_null_and_speaker_regex(BARE_DEPUTY_RE.pattern)
    return _get_deputy_speaker_ids_for_report_ids(session, report_ids, lookups, name_parliament_number_to_speaker_id)


def _populate_deputy_speaker_links(
    session: Session,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> None:
    speech_id_to_speaker_id = get_deputy_speaker_ids(session, lookups, name_parliament_number_to_speaker_id)
    _write_in_batches(CRUDSpeech(session).set_speaker_ids_bulk, speech_id_to_speaker_id)
    session.commit()


def _build_sitting_text(markdown: Optional[str], sections: Optional[str]) -> Optional[SittingText]:
    if markdown is not None:
        return build_sitting_text_from_markdown(markdown)
    if sections is not None:
        return build_sitting_text_from_sections(sections)
    return None


def _get_sitting_deputy_speaker_ids_for_report_ids(
    session: Session,
    report_ids: list[int],
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> dict[int, int]:
    speech_id_to_speaker_id: dict[int, int] = {}
    total = 0

    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch = report_ids[start : start + _REPORT_BATCH]
        report_id_to_report = {report.id: report for report in CRUDReport(session).get_by_ids(batch)}
        report_id_to_speech_rows: dict[int, list[SpeechRow]] = {}
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(batch):
            report_id_to_speech_rows.setdefault(speech_row.report_id, []).append(speech_row)
        date_keys = list({get_sitting_date_key(report.sitting_date) for report in report_id_to_report.values()})
        date_key_to_markdown = {
            date_markdown_row.sitting_date: date_markdown_row.markdown_content
            for date_markdown_row in CRUDSitting(session).get_date_markdown_rows_by_sitting_dates_and_markdown_content_not_null(date_keys)
        }
        date_key_to_sections = {
            date_sections_row.sitting_date: date_sections_row.sections
            for date_sections_row in CRUDSitting(session).get_date_sections_rows_by_sitting_dates_and_sections_not_null(date_keys)
        }
        date_key_to_sitting_text: dict[str, Optional[SittingText]] = {}
        for report_id, speech_rows in report_id_to_speech_rows.items():
            report = report_id_to_report[report_id]
            bare_deputy_rows = [speech_row for speech_row in speech_rows if speech_row.speaker_id is None and BARE_DEPUTY_RE.match(speech_row.speaker or "")]
            day = report.sitting_date.date()
            holders = [name for first, last, name in DEPUTY_SPEAKER_TERMS if first <= day <= last]
            if not bare_deputy_rows or len(holders) != _DEPUTY_SPEAKER_PAIR_SIZE:
                continue
            total += len(bare_deputy_rows)
            holder_to_speaker_id = {holder: get_speaker_id_for_name(holder, report.parliament_number, lookups, name_parliament_number_to_speaker_id) for holder in holders}
            if None in holder_to_speaker_id.values():
                continue
            male_holder_ids = {speaker_id for holder, speaker_id in holder_to_speaker_id.items() if holder not in DEPUTY_SPEAKER_WOMEN}
            date_key = get_sitting_date_key(report.sitting_date)
            if date_key not in date_key_to_sitting_text:
                date_key_to_sitting_text[date_key] = _build_sitting_text(date_key_to_markdown.get(date_key), date_key_to_sections.get(date_key))
            sitting_text = date_key_to_sitting_text[date_key]
            if sitting_text is None:
                continue
            speech_id_to_deputy_name = sitting_deputy_speaker_names(sitting_text, report.title, speech_rows)
            for speech_row in bare_deputy_rows:
                if speech_row.id not in speech_id_to_deputy_name:
                    continue
                found = get_speaker_ids_for_names([speech_id_to_deputy_name[speech_row.id]], report.parliament_number, lookups, name_parliament_number_to_speaker_id) & male_holder_ids
                if len(found) == 1:
                    speech_id_to_speaker_id[speech_row.id] = next(iter(found))
    logger.info(f"Sitting-level deputy speaker: {len(speech_id_to_speaker_id)}/{total} bare records resolved")
    return speech_id_to_speaker_id


# NOTE: the record does not print a bracket at every change of chair, so this pass can credit the wrong one of two Deputies; ADR 0002 accepts that risk for the rows the report-level pass leaves unlinked.
def get_sitting_deputy_speaker_ids(
    session: Session,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> dict[int, int]:
    report_ids = CRUDSpeech(session).get_report_ids_by_speaker_id_null_and_speaker_regex(BARE_DEPUTY_RE.pattern)
    return _get_sitting_deputy_speaker_ids_for_report_ids(session, report_ids, lookups, name_parliament_number_to_speaker_id)


def _populate_sitting_deputy_speaker_links(
    session: Session,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> None:
    speech_id_to_speaker_id = get_sitting_deputy_speaker_ids(session, lookups, name_parliament_number_to_speaker_id)
    _write_in_batches(CRUDSpeech(session).set_speaker_ids_bulk, speech_id_to_speaker_id)
    session.commit()
    logger.info(f"Speech: set speaker_id on {len(speech_id_to_speaker_id)} sitting-level deputy-speaker records")


def populate_speaker_links(session: Session) -> None:
    speakers = CRUDSpeaker(session).get_all()
    name_parliament_number_to_speaker_id = {
        (speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None
    }
    lookups = build_speaker_lookups(speakers)

    resolved_attendance_speaker_ids = resolve_attendance_rows(
        CRUDAttendance(session).get_speaker_rows_by_speaker_id_null(), lookups, name_parliament_number_to_speaker_id
    )
    logger.info(
        f"Attendance: set speaker_id on {len(resolved_attendance_speaker_ids.id_to_speaker_id)}/{resolved_attendance_speaker_ids.row_count} records"
    )
    _write_in_batches(CRUDAttendance(session).set_speaker_ids_bulk, resolved_attendance_speaker_ids.id_to_speaker_id)
    session.commit()

    resolved_speech_speaker_ids = resolve_speech_rows(
        CRUDSpeech(session).get_speaker_rows_by_speaker_id_null(), lookups, name_parliament_number_to_speaker_id
    )
    logger.info(f"Speech: set speaker_id on {len(resolved_speech_speaker_ids.id_to_speaker_id)}/{resolved_speech_speaker_ids.row_count} records")
    _write_in_batches(CRUDSpeech(session).set_speaker_ids_bulk, resolved_speech_speaker_ids.id_to_speaker_id)
    session.commit()
    _populate_role_context_links(session, lookups, name_parliament_number_to_speaker_id)
    _populate_deputy_speaker_links(session, lookups, name_parliament_number_to_speaker_id)
    _populate_sitting_deputy_speaker_links(session, lookups, name_parliament_number_to_speaker_id)


def link_speakers_by_report_ids_and_sitting_ids(session: Session, report_ids: list[int], sitting_ids: list[int]) -> None:
    speakers = CRUDSpeaker(session).get_all()
    name_parliament_number_to_speaker_id = {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None}
    lookups = build_speaker_lookups(speakers)

    resolved_attendance_speaker_ids = resolve_attendance_rows(
        CRUDAttendance(session).get_speaker_rows_by_sitting_ids_and_speaker_id_null(sitting_ids), lookups, name_parliament_number_to_speaker_id
    )
    logger.info(
        f"Attendance: set speaker_id on {len(resolved_attendance_speaker_ids.id_to_speaker_id)}/{resolved_attendance_speaker_ids.row_count} records"
    )
    _write_in_batches(CRUDAttendance(session).set_speaker_ids_bulk, resolved_attendance_speaker_ids.id_to_speaker_id)
    resolved_speech_speaker_ids = resolve_speech_rows(
        CRUDSpeech(session).get_speaker_rows_by_report_ids_and_speaker_id_null(report_ids), lookups, name_parliament_number_to_speaker_id
    )
    logger.info(f"Speech: set speaker_id on {len(resolved_speech_speaker_ids.id_to_speaker_id)}/{resolved_speech_speaker_ids.row_count} records")
    _write_in_batches(CRUDSpeech(session).set_speaker_ids_bulk, resolved_speech_speaker_ids.id_to_speaker_id)
    session.flush()
    for pattern, get_pass_speaker_ids in (
        (_ROLE_CONTEXT_PATTERN, _get_role_context_speaker_ids_for_report_ids),
        (BARE_DEPUTY_RE.pattern, _get_deputy_speaker_ids_for_report_ids),
        (BARE_DEPUTY_RE.pattern, _get_sitting_deputy_speaker_ids_for_report_ids),
    ):
        candidate_report_ids = CRUDSpeech(session).get_report_ids_by_report_ids_and_speaker_id_null_and_speaker_regex(report_ids, pattern)
        _write_in_batches(CRUDSpeech(session).set_speaker_ids_bulk, get_pass_speaker_ids(session, candidate_report_ids, lookups, name_parliament_number_to_speaker_id))
        session.flush()

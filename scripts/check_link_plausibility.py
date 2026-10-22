import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from enum import StrEnum
from statistics import median
from typing import Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.report import CRUDReport, ReportHeaderRow
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeakerStringCount
from database.init import engine
from database.speaker import Speaker
from enums import ReportType
from logs import logger
from services.attribution import HEADLINE_GROUP, get_group
from services.speaker_link import BARE_DEPUTY_RE, CHAIRMAN_RE
from utils.parliament_numbers import infer_parliament
from utils.sitting_dates import parse_sitting_date

_SHORT_LIST_MEDIAN_SHARE = 0.5
_MIN_ALLCAPS_HEADER_LETTERS = 4
_FIRST_LINE_MAX_LENGTH = 200
_FAULT_LOG_LIMIT = 40

_PRESIDING_SPEAKER_RE = re.compile(r"^(?:Mr|Mdm)\s*(?:Deputy\s*)?Speaker\b", re.IGNORECASE)
_QUESTION_OPENER_RE = re.compile(r"^\s*(?:\d+\\?\.\s+)?(?:asked the|to ask)\b", re.IGNORECASE)
_HON_MEMBERS_RE = re.compile(r"hon\.? members?", re.IGNORECASE)
_LETTER_RE = re.compile(r"[A-Za-z]")


class _PresenceStatus(StrEnum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNLISTED = "UNLISTED"
    NO_ATTENDANCE = "NO_ATTENDANCE"


class _Exemption(StrEnum):
    WRITTEN_ANSWER = "WRITTEN_ANSWER"
    QUESTION_LINE = "QUESTION_LINE"
    NOT_MEMBER = "NOT_MEMBER"
    PRESIDING_OFFICER = "PRESIDING_OFFICER"
    NO_LETTERS = "NO_LETTERS"


@dataclass(frozen=True)
class _ShortSitting:
    sitting_date: date
    parliament_number: int
    attendance_row_count: int
    parliament_median: float


@dataclass
class _Pair:
    report_id: int
    sitting_date: date
    report_type: str
    title: str
    speaker: str
    person_id: int
    canonical_name: str
    status: _PresenceStatus
    row_count: int
    first_ordinal: int
    first_transcript_line: str
    is_short_list_sitting: bool


# NOTE: chairman strings are not exempt because they resolve to a named member, whose absence is a real signal.
def _is_presiding_speaker(speaker: str) -> bool:
    return _PRESIDING_SPEAKER_RE.match(speaker) is not None or BARE_DEPUTY_RE.match(speaker) is not None


def _get_exemption(report_type: str, speaker: str, transcript: str, is_member: bool) -> Optional[_Exemption]:
    if report_type == ReportType.WRITTEN_ANSWER or report_type == ReportType.WRITTEN_ANSWER_NOT_AVAILABLE:
        return _Exemption.WRITTEN_ANSWER
    if _QUESTION_OPENER_RE.match(transcript) is not None:
        return _Exemption.QUESTION_LINE
    if not is_member:
        return _Exemption.NOT_MEMBER
    if _is_presiding_speaker(speaker):
        return _Exemption.PRESIDING_OFFICER
    if _LETTER_RE.search(transcript) is None:
        return _Exemption.NO_LETTERS
    return None


def _is_unlinkable(speaker: str) -> bool:
    letters = "".join(_LETTER_RE.findall(speaker))
    return (
        CHAIRMAN_RE.match(speaker) is not None
        or BARE_DEPUTY_RE.match(speaker) is not None
        or _HON_MEMBERS_RE.search(speaker) is not None
        or speaker.startswith(("(", "_"))
        or (len(letters) >= _MIN_ALLCAPS_HEADER_LETTERS and letters == letters.upper())
    )


def _get_status(person_id: int, sitting_date: date, date_to_person_to_is_present: dict[date, dict[int, bool]]) -> _PresenceStatus:
    person_to_is_present = date_to_person_to_is_present.get(sitting_date)
    if person_to_is_present is None:
        return _PresenceStatus.NO_ATTENDANCE
    is_present = person_to_is_present.get(person_id)
    if is_present is None:
        return _PresenceStatus.UNLISTED
    if is_present:
        return _PresenceStatus.PRESENT
    return _PresenceStatus.ABSENT


def _get_first_line(transcript: str) -> str:
    return transcript.strip().split("\n", 1)[0][:_FIRST_LINE_MAX_LENGTH]


def _get_date_to_person_to_is_present(
    session: Session, sitting_id_to_date: dict[int, date], speaker_id_to_person_id: dict[int, Optional[int]]
) -> dict[date, dict[int, bool]]:
    sitting_ids_with_attendance = {count.sitting_id for count in CRUDAttendance(session).get_sitting_counts()}
    date_to_person_to_is_present: dict[date, dict[int, bool]] = {
        sitting_id_to_date[sitting_id]: {} for sitting_id in sitting_ids_with_attendance if sitting_id in sitting_id_to_date
    }
    for attendance in CRUDAttendance(session).get_presence_rows_by_speaker_id_not_null():
        sitting_date = sitting_id_to_date.get(attendance.sitting_id)
        person_id = speaker_id_to_person_id.get(attendance.speaker_id)
        if sitting_date is None or person_id is None:
            continue
        person_to_is_present = date_to_person_to_is_present[sitting_date]
        person_to_is_present[person_id] = person_to_is_present.get(person_id, False) or attendance.is_present is True
    return date_to_person_to_is_present


def _get_short_sittings(
    session: Session, sitting_id_to_date: dict[int, date], sitting_id_to_parliament: dict[int, int]
) -> list[_ShortSitting]:
    sitting_id_to_row_count = {
        count.sitting_id: count.row_count for count in CRUDAttendance(session).get_sitting_counts()
        if count.sitting_id in sitting_id_to_date and count.sitting_id in sitting_id_to_parliament
    }
    parliament_to_row_counts: defaultdict[int, list[int]] = defaultdict(list)
    for sitting_id, row_count in sitting_id_to_row_count.items():
        parliament_to_row_counts[sitting_id_to_parliament[sitting_id]].append(row_count)
    parliament_to_median = {
        parliament_number: median(row_counts) for parliament_number, row_counts in parliament_to_row_counts.items()
    }
    return [
        _ShortSitting(sitting_id_to_date[sitting_id], sitting_id_to_parliament[sitting_id], row_count, parliament_to_median[sitting_id_to_parliament[sitting_id]])
        for sitting_id, row_count in sitting_id_to_row_count.items()
        if row_count < _SHORT_LIST_MEDIAN_SHARE * parliament_to_median[sitting_id_to_parliament[sitting_id]]
    ]


def _log_presence_counts(
    unexempted_status_to_row_count: Counter[_PresenceStatus],
    exemption_to_row_count: Counter[_Exemption],
    group_report_type_status_to_row_count: Counter[tuple[str, str, _PresenceStatus]],
) -> None:
    logger.info(f"B1 before exemptions, rows by status: { {status.value: row_count for status, row_count in unexempted_status_to_row_count.items()} }")
    logger.info(f"B1 exempted rows by reason: { {exemption.value: row_count for exemption, row_count in exemption_to_row_count.items()} }")
    groups = sorted({key[0] for key in group_report_type_status_to_row_count}, key=lambda group: (group != HEADLINE_GROUP, group))
    for group in groups:
        report_types = sorted({key[1] for key in group_report_type_status_to_row_count if key[0] == group})
        for report_type in report_types:
            status_to_row_count = {
                key[2].value: row_count for key, row_count in group_report_type_status_to_row_count.items()
                if key[0] == group and key[1] == report_type
            }
            logger.info(f"B1 {group} {report_type}: {status_to_row_count}")


def _check_presence(
    session: Session,
    speakers: list[Speaker],
    date_to_person_to_is_present: dict[date, dict[int, bool]],
    short_dates: set[date],
) -> list[_Pair]:
    speaker_id_to_speaker = {speaker.id: speaker for speaker in speakers}
    report_id_to_header: dict[int, ReportHeaderRow] = {header.id: header for header in CRUDReport(session).get_header_rows()}
    group_report_type_status_to_row_count: Counter[tuple[str, str, _PresenceStatus]] = Counter()
    unexempted_status_to_row_count: Counter[_PresenceStatus] = Counter()
    exemption_to_row_count: Counter[_Exemption] = Counter()
    pair_key_to_pair: dict[tuple[int, int], _Pair] = {}

    for link_row in CRUDSpeech(session).get_link_rows_by_speaker_id_not_null():
        header = report_id_to_header[link_row.report_id]
        speaker = speaker_id_to_speaker[link_row.speaker_id]
        sitting_date = header.sitting_date.date()
        status = _get_status(speaker.person_id, sitting_date, date_to_person_to_is_present)
        unexempted_status_to_row_count[status] += 1
        exemption = _get_exemption(header.report_type, link_row.speaker or "", link_row.transcript, speaker.is_member)
        if exemption is not None:
            exemption_to_row_count[exemption] += 1
            continue
        group_report_type_status_to_row_count[(get_group(header.parliament_number), header.report_type, status)] += 1
        if status != _PresenceStatus.ABSENT and status != _PresenceStatus.UNLISTED:
            continue
        pair = pair_key_to_pair.get((link_row.report_id, speaker.person_id))
        if pair is None:
            pair_key_to_pair[(link_row.report_id, speaker.person_id)] = _Pair(
                link_row.report_id, sitting_date, header.report_type, header.title, link_row.speaker or "",
                speaker.person_id, speaker.name, status, 1, link_row.ordinal, _get_first_line(link_row.transcript),
                sitting_date in short_dates,
            )
            continue
        pair.row_count += 1
        if link_row.ordinal < pair.first_ordinal:
            pair.first_ordinal = link_row.ordinal
            pair.first_transcript_line = _get_first_line(link_row.transcript)

    _log_presence_counts(unexempted_status_to_row_count, exemption_to_row_count, group_report_type_status_to_row_count)
    flagged_pairs = sorted(pair_key_to_pair.values(), key=lambda pair: (-pair.row_count, pair.report_id))
    logger.info(
        f"B1 flagged pairs: {len(flagged_pairs)} ({sum(pair.row_count for pair in flagged_pairs)} rows), "
        f"{sum(1 for pair in flagged_pairs if pair.is_short_list_sitting)} from B3-flagged sittings"
    )
    return flagged_pairs


def _check_unlinkable(session: Session) -> list[SpeakerStringCount]:
    unlinkable_strings = 0
    unlinkable_rows = 0
    faults = []
    for speaker_count in CRUDSpeech(session).get_speaker_counts_by_speaker_id_null_and_speaker_not_null():
        if _is_unlinkable(speaker_count.speaker):
            unlinkable_strings += 1
            unlinkable_rows += speaker_count.row_count
            continue
        faults.append(speaker_count)
    faults.sort(key=lambda fault: -fault.row_count)
    logger.info(f"B2 distinct unlinked strings: {unlinkable_strings + len(faults)}")
    logger.info(f"B2 unlinkable: {unlinkable_strings} strings, {unlinkable_rows} rows")
    logger.info(f"B2 faults: {len(faults)} strings, {sum(fault.row_count for fault in faults)} rows")
    for fault in faults[:_FAULT_LOG_LIMIT]:
        logger.info(f"B2 fault {fault.row_count:>5}  {fault.speaker}")
    return faults


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", metavar="FILE", help="Write the review list to FILE")
    arguments = parser.parse_args()

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        sitting_id_to_date: dict[int, date] = {}
        sitting_id_to_parliament: dict[int, int] = {}
        for sitting in CRUDSitting(session).get_date_rows():
            if sitting.sitting_date is None:
                continue
            sitting_id_to_date[sitting.id] = parse_sitting_date(sitting.sitting_date).date()
            parliament_number = infer_parliament(sitting.parlement_no, sitting.volume_no)
            if parliament_number is not None:
                sitting_id_to_parliament[sitting.id] = parliament_number

        short_sittings = _get_short_sittings(session, sitting_id_to_date, sitting_id_to_parliament)
        logger.info(f"B3 short attendance lists (under {_SHORT_LIST_MEDIAN_SHARE} of the parliament median): {len(short_sittings)} sittings")
        for sitting in short_sittings:
            logger.info(f"B3 {sitting.sitting_date} (Parliament {sitting.parliament_number}): {sitting.attendance_row_count} attendance rows, parliament median {sitting.parliament_median}")
        date_to_person_to_is_present = _get_date_to_person_to_is_present(
            session, sitting_id_to_date, {speaker.id: speaker.person_id for speaker in speakers}
        )
        short_dates = {sitting.sitting_date for sitting in short_sittings}
        flagged_pairs = _check_presence(session, speakers, date_to_person_to_is_present, short_dates)
        faults = _check_unlinkable(session)

    if arguments.json:
        review_list = {
            "b1_flagged_pairs": [asdict(pair) for pair in flagged_pairs],
            "b2_faults": [asdict(fault) for fault in faults],
            "b3_short_sittings": [asdict(sitting) for sitting in short_sittings],
        }
        with open(arguments.json, "w", encoding="utf-8") as file:
            json.dump(review_list, file, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Wrote the review list to {arguments.json}")


if __name__ == "__main__":
    main()

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from functools import partial
from typing import Optional, Union

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.report import CRUDReport, ReportParticipantReportRow
from crud.report_asker import CRUDReportAsker, ReportAskerRow
from crud.report_participant import CRUDReportParticipant, ReportParticipantRow
from crud.report_question_state import CRUDReportQuestionState, ReportQuestionStateRow
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechAskerRow
from database.report_participant import ReportParticipant
from database.report_question_state import ReportQuestionState
from enums import (
    OfficeSource,
    ParticipantRole,
    ParticipantRoleSource,
    QuestionState,
    ReportAskerSource,
    ReportType,
)
from exceptions import HansardWriteCheckError
from logs import logger
from services.attendance import build_speaker_lookups, get_sitting_entry_offices
from services.attribution import get_group
from services.report_asker import get_asker_candidates, get_question_row_ordinals
from services.report_participant import (
    build_report_participants,
    build_report_question_states,
    get_not_a_question_state,
    get_participants,
    get_question_states,
    read_inline_speakers,
)
from services.speaker_link import resolve_speech_speaker_id
from utils.asker_candidate import AskerCandidate
from utils.office import Office, get_header_entries, get_label_office
from utils.sitting_dates import get_sitting_date_key
from utils.speaker_resolution import SpeakerLookups

REPORT_PARTICIPANT_REPORT_TYPES = (
    ReportType.ORAL_ANSWER,
    ReportType.WRITTEN_ANSWER,
    ReportType.WRITTEN_ANSWER_NOT_AVAILABLE,
)
_REPORT_BATCH = 200
_SITTING_BATCH = 20


@dataclass
class ReportParticipantCounts:
    reports: int = 0
    role_to_row_count: Counter[ParticipantRole] = field(default_factory=Counter)
    role_source_to_row_count: Counter[ParticipantRoleSource] = field(
        default_factory=Counter
    )
    office_source_to_row_count: Counter[OfficeSource] = field(default_factory=Counter)
    state_to_row_count: Counter[QuestionState] = field(default_factory=Counter)
    rows_without_speaker_id: int = 0


@dataclass(frozen=True)
class ReportParticipantPlan:
    report_ids: list[int] = field(default_factory=list)
    report_participants: list[ReportParticipant] = field(default_factory=list)
    report_question_states: list[ReportQuestionState] = field(default_factory=list)
    report_id_to_group: dict[int, str] = field(default_factory=dict)
    group_to_counts: defaultdict[str, ReportParticipantCounts] = field(
        default_factory=lambda: defaultdict(ReportParticipantCounts)
    )


@dataclass(frozen=True)
class _PlannedRows:
    report_participants: list[ReportParticipant]
    report_question_states: list[ReportQuestionState]


@dataclass(frozen=True)
class _SittingAttendance:
    offices: dict[int, Office]
    listed_speaker_ids: frozenset[int]


@dataclass(frozen=True)
class _OfficeSources:
    sitting_date_to_attendance: dict[datetime, _SittingAttendance] = field(
        default_factory=dict
    )
    sitting_date_to_label_offices: dict[datetime, dict[int, Office]] = field(
        default_factory=dict
    )
    parliament_number_to_guess_offices: dict[int, dict[int, Office]] = field(
        default_factory=dict
    )


def _resolve_candidate(
    asker_candidate: AskerCandidate,
    report_row: ReportParticipantReportRow,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> AskerCandidate:
    if (
        asker_candidate.source != ReportAskerSource.STOOD_IN_NAME_LINE
        and asker_candidate.source != ReportAskerSource.NAME_IN_TEXT
    ):
        return asker_candidate
    return replace(
        asker_candidate,
        speaker_id=resolve_speech_speaker_id(
            asker_candidate.printed_name,
            report_row.parliament_number,
            report_row.sitting_date,
            lookups,
            name_parliament_number_to_speaker_id,
        ),
    )


def _get_header_offices(
    report_row: ReportParticipantReportRow,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> dict[int, Office]:
    if report_row.mps_speaking_header is None:
        return {}
    header_offices: dict[int, Office] = {}
    for header_entry in get_header_entries(report_row.mps_speaking_header):
        if header_entry.office_printed is None:
            continue
        speaker_id = resolve_speech_speaker_id(
            header_entry.printed_name,
            report_row.parliament_number,
            report_row.sitting_date,
            lookups,
            name_parliament_number_to_speaker_id,
        )
        if speaker_id is None:
            continue
        header_offices.setdefault(
            speaker_id,
            Office(header_entry.office_printed, OfficeSource.HEADER_IN_REPORT),
        )
    return header_offices


def _get_sitting_date_to_attendance(
    session: Session, sitting_dates: list[datetime], lookups: SpeakerLookups
) -> dict[datetime, _SittingAttendance]:
    sitting_date_to_attendance = {
        sitting_date: _SittingAttendance({}, frozenset())
        for sitting_date in sitting_dates
    }
    sitting_date_key_to_sitting_date = {
        get_sitting_date_key(sitting_date): sitting_date
        for sitting_date in sitting_dates
    }
    sitting_date_keys = list(sitting_date_key_to_sitting_date)
    for start in range(0, len(sitting_date_keys), _SITTING_BATCH):
        sitting_attendance_text_rows = CRUDSitting(
            session
        ).get_attendance_text_rows_by_sitting_dates(
            sitting_date_keys[start : start + _SITTING_BATCH]
        )
        sitting_id_and_speaker_name_to_speaker_id: dict[
            tuple[int, Optional[str]], int
        ] = {}
        sitting_id_to_listed_speaker_ids: defaultdict[int, set[int]] = defaultdict(set)
        for attendance_name_row in CRUDAttendance(
            session
        ).get_name_rows_by_sitting_ids_and_speaker_id_not_null(
            [
                sitting_attendance_text_row.id
                for sitting_attendance_text_row in sitting_attendance_text_rows
            ]
        ):
            sitting_id_and_speaker_name_to_speaker_id[
                (attendance_name_row.sitting_id, attendance_name_row.speaker_name)
            ] = attendance_name_row.speaker_id
            sitting_id_to_listed_speaker_ids[attendance_name_row.sitting_id].add(
                attendance_name_row.speaker_id
            )
        for sitting_attendance_text_row in sitting_attendance_text_rows:
            attendance_offices: dict[int, Office] = {}
            for entry_office in get_sitting_entry_offices(
                sitting_attendance_text_row, lookups
            ):
                speaker_id = sitting_id_and_speaker_name_to_speaker_id.get(
                    (sitting_attendance_text_row.id, entry_office.speaker_name)
                )
                if speaker_id is None:
                    continue
                attendance_offices.setdefault(
                    speaker_id,
                    Office(entry_office.office_printed, OfficeSource.ATTENDANCE_LIST),
                )
            sitting_date_to_attendance[
                sitting_date_key_to_sitting_date[
                    sitting_attendance_text_row.sitting_date
                ]
            ] = _SittingAttendance(
                attendance_offices,
                frozenset(
                    sitting_id_to_listed_speaker_ids.get(
                        sitting_attendance_text_row.id, set()
                    )
                ),
            )
    return sitting_date_to_attendance


def _get_sitting_date_to_label_offices(
    session: Session, sitting_dates: list[datetime]
) -> dict[datetime, dict[int, Office]]:
    sitting_date_to_label_offices: dict[datetime, dict[int, Office]] = {
        sitting_date: {} for sitting_date in sitting_dates
    }
    label_rows = sorted(
        CRUDSpeech(
            session
        ).get_label_rows_by_sitting_dates_and_speaker_id_not_null_and_speaker_not_null(
            sitting_dates
        ),
        key=lambda label_row: (label_row.report_id, label_row.ordinal),
    )
    for label_row in label_rows:
        label_offices = sitting_date_to_label_offices[label_row.sitting_date]
        if label_row.speaker_id in label_offices:
            continue
        label_office = get_label_office(label_row.speaker)
        if label_office is None:
            continue
        label_offices[label_row.speaker_id] = Office(
            label_office, OfficeSource.LABEL_SAME_DAY
        )
    return sitting_date_to_label_offices


def _get_parliament_number_to_guess_offices(
    session: Session, parliament_numbers: list[int]
) -> dict[int, dict[int, Office]]:
    parliament_number_and_speaker_id_to_office_counts: defaultdict[
        tuple[int, int], Counter[str]
    ] = defaultdict(Counter)
    for label_row in CRUDSpeech(
        session
    ).get_label_rows_by_parliament_numbers_and_report_types_and_speaker_id_not_null_and_speaker_not_null(
        parliament_numbers, REPORT_PARTICIPANT_REPORT_TYPES
    ):
        label_office = get_label_office(label_row.speaker)
        if label_office is None:
            continue
        parliament_number_and_speaker_id_to_office_counts[
            (label_row.parliament_number, label_row.speaker_id)
        ][label_office] += label_row.report_count
    parliament_number_to_guess_offices: dict[int, dict[int, Office]] = {
        parliament_number: {} for parliament_number in parliament_numbers
    }
    for (
        parliament_number,
        speaker_id,
    ), office_to_count in parliament_number_and_speaker_id_to_office_counts.items():
        most_common_count = max(office_to_count.values())
        most_common_offices = [
            label_office
            for label_office, count in office_to_count.items()
            if count == most_common_count
        ]
        if len(most_common_offices) > 1:
            continue
        parliament_number_to_guess_offices[parliament_number][speaker_id] = Office(
            most_common_offices[0], OfficeSource.PARLIAMENT_GUESS
        )
    return parliament_number_to_guess_offices


def _build_planned_rows(
    report_row: ReportParticipantReportRow,
    speech_asker_rows: list[SpeechAskerRow],
    asker_candidates: list[AskerCandidate],
    speaker_id_to_office: dict[int, Office],
    get_inline_speaker_id: Callable[[str], Optional[int]],
) -> _PlannedRows:
    question_row_ordinals = get_question_row_ordinals(speech_asker_rows)
    not_a_question_state = get_not_a_question_state(
        report_row.title, asker_candidates, question_row_ordinals
    )
    if not_a_question_state is not None:
        return _PlannedRows(
            [], build_report_question_states(report_row.id, [not_a_question_state])
        )
    participant_candidates = get_participants(
        read_inline_speakers(speech_asker_rows, get_inline_speaker_id),
        asker_candidates,
        question_row_ordinals,
        speaker_id_to_office,
    )
    return _PlannedRows(
        build_report_participants(report_row.id, participant_candidates),
        build_report_question_states(
            report_row.id,
            get_question_states(
                report_row.title, speech_asker_rows, participant_candidates
            ),
        ),
    )


def _add_report_participant(
    counts: ReportParticipantCounts,
    report_participant: Union[ReportParticipant, ReportParticipantRow],
) -> None:
    counts.role_to_row_count[report_participant.role] += 1
    counts.role_source_to_row_count[report_participant.role_source] += 1
    if report_participant.office_source is not None:
        counts.office_source_to_row_count[report_participant.office_source] += 1
    counts.rows_without_speaker_id += report_participant.speaker_id is None


def _add_report_question_state(
    counts: ReportParticipantCounts,
    report_question_state: Union[ReportQuestionState, ReportQuestionStateRow],
) -> None:
    counts.state_to_row_count[report_question_state.state] += 1


# NOTE: a member the sitting's attendance lists without an office held none that day, so no guess applies
def _get_speaker_id_to_office(
    report_row: ReportParticipantReportRow,
    office_sources: _OfficeSources,
    header_offices: dict[int, Office],
) -> dict[int, Office]:
    attendance = office_sources.sitting_date_to_attendance[report_row.sitting_date]
    return {
        **{
            speaker_id: guess_office
            for speaker_id, guess_office in office_sources.parliament_number_to_guess_offices[
                report_row.parliament_number
            ].items()
            if speaker_id not in attendance.listed_speaker_ids
        },
        **office_sources.sitting_date_to_label_offices[report_row.sitting_date],
        **attendance.offices,
        **header_offices,
    }


def _add_office_sources(
    session: Session,
    office_sources: _OfficeSources,
    report_rows: list[ReportParticipantReportRow],
    lookups: SpeakerLookups,
) -> None:
    sitting_dates = {report_row.sitting_date for report_row in report_rows}
    parliament_numbers = {report_row.parliament_number for report_row in report_rows}
    office_sources.sitting_date_to_attendance.update(
        _get_sitting_date_to_attendance(
            session,
            [
                sitting_date
                for sitting_date in sitting_dates
                if sitting_date not in office_sources.sitting_date_to_attendance
            ],
            lookups,
        )
    )
    office_sources.sitting_date_to_label_offices.update(
        _get_sitting_date_to_label_offices(
            session,
            [
                sitting_date
                for sitting_date in sitting_dates
                if sitting_date not in office_sources.sitting_date_to_label_offices
            ],
        )
    )
    office_sources.parliament_number_to_guess_offices.update(
        _get_parliament_number_to_guess_offices(
            session,
            [
                parliament_number
                for parliament_number in parliament_numbers
                if parliament_number
                not in office_sources.parliament_number_to_guess_offices
            ],
        )
    )


def get_report_participant_plan(
    session: Session, report_ids: list[int]
) -> ReportParticipantPlan:
    speakers = CRUDSpeaker(session).get_all()
    name_parliament_number_to_speaker_id = {
        (speaker.name, speaker.parliament_number): speaker.id
        for speaker in speakers
        if speaker.id is not None
    }
    lookups = build_speaker_lookups(speakers)
    office_sources = _OfficeSources()
    plan = ReportParticipantPlan()
    sorted_report_ids = sorted(report_ids)
    for start in range(0, len(sorted_report_ids), _REPORT_BATCH):
        report_rows = CRUDReport(
            session
        ).get_participant_report_rows_by_ids_and_report_types(
            sorted_report_ids[start : start + _REPORT_BATCH],
            REPORT_PARTICIPANT_REPORT_TYPES,
        )
        report_id_to_speech_asker_rows: defaultdict[int, list[SpeechAskerRow]] = (
            defaultdict(list)
        )
        for speech_asker_row in CRUDSpeech(session).get_asker_rows_by_report_ids(
            [report_row.id for report_row in report_rows]
        ):
            report_id_to_speech_asker_rows[speech_asker_row.report_id].append(
                speech_asker_row
            )
        _add_office_sources(session, office_sources, report_rows, lookups)
        for report_row in report_rows:
            speech_asker_rows = report_id_to_speech_asker_rows[report_row.id]
            planned_rows = _build_planned_rows(
                report_row,
                speech_asker_rows,
                [
                    _resolve_candidate(
                        asker_candidate,
                        report_row,
                        lookups,
                        name_parliament_number_to_speaker_id,
                    )
                    for asker_candidate in get_asker_candidates(
                        speech_asker_rows, report_row.title
                    )
                ],
                _get_speaker_id_to_office(
                    report_row,
                    office_sources,
                    _get_header_offices(
                        report_row, lookups, name_parliament_number_to_speaker_id
                    ),
                ),
                partial(
                    resolve_speech_speaker_id,
                    parliament_number=report_row.parliament_number,
                    sitting_date=report_row.sitting_date,
                    lookups=lookups,
                    name_parliament_number_to_speaker_id=name_parliament_number_to_speaker_id,
                ),
            )
            group = get_group(report_row.parliament_number)
            counts = plan.group_to_counts[group]
            counts.reports += 1
            for report_participant in planned_rows.report_participants:
                _add_report_participant(counts, report_participant)
            for report_question_state in planned_rows.report_question_states:
                _add_report_question_state(counts, report_question_state)
            plan.report_ids.append(report_row.id)
            plan.report_id_to_group[report_row.id] = group
            plan.report_participants.extend(planned_rows.report_participants)
            plan.report_question_states.extend(planned_rows.report_question_states)
    return plan


def _get_stored_counts(
    session: Session, plan: ReportParticipantPlan
) -> defaultdict[str, ReportParticipantCounts]:
    group_to_counts: defaultdict[str, ReportParticipantCounts] = defaultdict(
        ReportParticipantCounts
    )
    for start in range(0, len(plan.report_ids), _REPORT_BATCH):
        batch_report_ids = plan.report_ids[start : start + _REPORT_BATCH]
        for report_participant_row in CRUDReportParticipant(
            session
        ).get_rows_by_report_ids(batch_report_ids):
            _add_report_participant(
                group_to_counts[
                    plan.report_id_to_group[report_participant_row.report_id]
                ],
                report_participant_row,
            )
        for report_question_state_row in CRUDReportQuestionState(
            session
        ).get_rows_by_report_ids(batch_report_ids):
            _add_report_question_state(
                group_to_counts[
                    plan.report_id_to_group[report_question_state_row.report_id]
                ],
                report_question_state_row,
            )
    return group_to_counts


def _get_report_asker_role(report_asker_source: ReportAskerSource) -> ParticipantRole:
    if report_asker_source == ReportAskerSource.STOOD_IN_NAME_LINE:
        return ParticipantRole.ABSENT_FILER
    return ParticipantRole.ASKER


def _validate_can_commit_asker_agreement(
    session: Session, report_ids: list[int]
) -> None:
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch_report_ids = report_ids[start : start + _REPORT_BATCH]
        report_id_to_participant_rows: defaultdict[int, list[ReportParticipantRow]] = (
            defaultdict(list)
        )
        for report_participant_row in CRUDReportParticipant(
            session
        ).get_rows_by_report_ids(batch_report_ids):
            report_id_to_participant_rows[report_participant_row.report_id].append(
                report_participant_row
            )
        report_id_to_report_asker_rows: defaultdict[int, list[ReportAskerRow]] = (
            defaultdict(list)
        )
        for report_asker_row in CRUDReportAsker(session).get_rows_by_report_ids(
            batch_report_ids
        ):
            report_id_to_report_asker_rows[report_asker_row.report_id].append(
                report_asker_row
            )
        for report_id in batch_report_ids:
            participant_askers = [
                (
                    report_participant_row.printed_name,
                    report_participant_row.speaker_id,
                    report_participant_row.role,
                )
                for report_participant_row in report_id_to_participant_rows[report_id]
                if report_participant_row.role == ParticipantRole.ASKER
                or report_participant_row.role == ParticipantRole.ABSENT_FILER
            ]
            report_askers = [
                (
                    report_asker_row.printed_name,
                    report_asker_row.speaker_id,
                    _get_report_asker_role(report_asker_row.source),
                )
                for report_asker_row in report_id_to_report_asker_rows[report_id]
            ]
            if participant_askers != report_askers:
                raise HansardWriteCheckError(
                    f"Report {report_id}: report participants hold askers {participant_askers}, report_asker holds {report_askers}"
                )
            participant_readers = {
                (report_participant_row.printed_name, report_participant_row.speaker_id)
                for report_participant_row in report_id_to_participant_rows[report_id]
                if report_participant_row.role == ParticipantRole.READER
            }
            report_readers = {
                (
                    report_asker_row.reader_printed_name,
                    report_asker_row.reader_speaker_id,
                )
                for report_asker_row in report_id_to_report_asker_rows[report_id]
                if report_asker_row.reader_printed_name is not None
            }
            if participant_readers != report_readers:
                raise HansardWriteCheckError(
                    f"Report {report_id}: report participants hold readers {participant_readers}, report_asker holds {report_readers}"
                )


def _validate_can_commit_report_participants(
    session: Session, plan: ReportParticipantPlan
) -> None:
    stored_group_to_counts = _get_stored_counts(session, plan)
    for group, counts in plan.group_to_counts.items():
        stored_counts = stored_group_to_counts[group]
        if stored_counts.role_to_row_count != counts.role_to_row_count:
            raise HansardWriteCheckError(
                f"{group}: stored report participants by role {dict(stored_counts.role_to_row_count)}, the plan has {dict(counts.role_to_row_count)}"
            )
        if stored_counts.role_source_to_row_count != counts.role_source_to_row_count:
            raise HansardWriteCheckError(
                f"{group}: stored report participants by role source {dict(stored_counts.role_source_to_row_count)}, the plan has {dict(counts.role_source_to_row_count)}"
            )
        if (
            stored_counts.office_source_to_row_count
            != counts.office_source_to_row_count
        ):
            raise HansardWriteCheckError(
                f"{group}: stored report participants by office source {dict(stored_counts.office_source_to_row_count)}, the plan has {dict(counts.office_source_to_row_count)}"
            )
        if stored_counts.rows_without_speaker_id != counts.rows_without_speaker_id:
            raise HansardWriteCheckError(
                f"{group}: {stored_counts.rows_without_speaker_id} report participants hold no speaker_id, the plan has {counts.rows_without_speaker_id}"
            )
        if stored_counts.state_to_row_count != counts.state_to_row_count:
            raise HansardWriteCheckError(
                f"{group}: stored report question states {dict(stored_counts.state_to_row_count)}, the plan has {dict(counts.state_to_row_count)}"
            )
    _validate_can_commit_asker_agreement(session, plan.report_ids)


def _insert_report_participants(session: Session, plan: ReportParticipantPlan) -> None:
    CRUDReportParticipant(session).add_many(plan.report_participants)
    CRUDReportQuestionState(session).add_many(plan.report_question_states)
    _validate_can_commit_report_participants(session, plan)


def write_report_participant_plan(
    session: Session, plan: ReportParticipantPlan
) -> None:
    for start in range(0, len(plan.report_ids), _REPORT_BATCH):
        batch_report_ids = plan.report_ids[start : start + _REPORT_BATCH]
        stored_participant_count = len(
            CRUDReportParticipant(session).get_rows_by_report_ids(batch_report_ids)
        )
        deleted_participant_count = CRUDReportParticipant(session).delete_by_report_ids(
            batch_report_ids
        )
        if deleted_participant_count != stored_participant_count:
            raise HansardWriteCheckError(
                f"Deleted {deleted_participant_count} report participants, read {stored_participant_count}"
            )
        stored_state_count = len(
            CRUDReportQuestionState(session).get_rows_by_report_ids(batch_report_ids)
        )
        deleted_state_count = CRUDReportQuestionState(session).delete_by_report_ids(
            batch_report_ids
        )
        if deleted_state_count != stored_state_count:
            raise HansardWriteCheckError(
                f"Deleted {deleted_state_count} report question states, read {stored_state_count}"
            )
    _insert_report_participants(session, plan)


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_report_participants(session: Session, report_ids: list[int]) -> None:
    plan = get_report_participant_plan(session, report_ids)
    _insert_report_participants(session, plan)
    logger.info(
        f"Report participants: added {len(plan.report_participants)} rows and {len(plan.report_question_states)} states for {len(plan.report_ids)} reports"
    )

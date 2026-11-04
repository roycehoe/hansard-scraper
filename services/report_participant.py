import re
from dataclasses import dataclass, replace
from typing import Optional, Union

from crud.speech import SpeechAskerRow
from database.report_participant import ReportParticipant
from database.report_question_state import ReportQuestionState
from enums import (
    OfficeClass,
    OfficeSource,
    ParticipantRole,
    ParticipantRoleSource,
    QuestionState,
    ReportAskerSource,
    SpeechKind,
)
from utils.asker_candidate import AskerCandidate
from utils.names import CHAIR_FORM_PATTERN, TITLE_PREFIXES
from utils.office import (
    Office,
    get_answering_for_printed,
    get_label_office,
    get_office_class,
    is_government_office,
)

_MAX_CHAIR_NAME_CALL_WORDS = 8
_MINISTER_CALL_TITLE = "Minister "
_ROLE_ORDER = tuple(ParticipantRole)

_CHAIR_NAME_CALL_PATTERN = re.compile(
    r"^(?:"
    + "|".join(re.escape(title) for title in (*TITLE_PREFIXES, _MINISTER_CALL_TITLE))
    + r")[^.:;?!,]+\.?$",
    re.IGNORECASE,
)
_NOT_A_QUESTION_TITLE_PATTERN = re.compile(
    r"^\W*(?:annex(?:e?s)?|appendix|appendices|tables?|lists?|listing|statements?"
    r"|addend(?:um|a))\b",
    re.IGNORECASE,
)
_CORRECTION_TITLE_PATTERN = re.compile(r"^\W*addend(?:um|a)\b", re.IGNORECASE)
_COLLECTIVE_LABEL_PATTERN = re.compile(
    r"^\W*(?:(?:some|an?)\s+)?hon\.?\s+members?\W*$", re.IGNORECASE
)
_PRIVATE_NOTICE_PATTERN = re.compile(r"\(\s*by private notice", re.IGNORECASE)
_NOT_ASKED_ALOUD_PATTERN = re.compile(
    r"\b(?:stood\s+over|withdraw(?:n|al)?|postponed|deferred|not\s+reached|no\s+response"
    r"|is\s+not\s+here|stood\s+on\s+the\s+order\s+paper)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParticipantCandidate:
    role: ParticipantRole
    role_source: ParticipantRoleSource
    first_ordinal: int
    printed_name: str
    speaker_id: Optional[int]
    answering_for_printed: Optional[str] = None
    office_printed: Optional[str] = None
    office_class: Optional[OfficeClass] = None
    office_source: Optional[OfficeSource] = None


@dataclass(frozen=True)
class QuestionStateCandidate:
    state: QuestionState
    printed_text: str
    first_ordinal: Optional[int]


@dataclass(frozen=True)
class _ParticipantRow:
    ordinal: int
    label: str
    transcript: str
    speaker_id: Optional[int]
    person_key: Union[int, str]


@dataclass(frozen=True)
class _ReportRoles:
    question_ordinals: frozenset[int]
    chair_ordinals: frozenset[int]
    asker_person_keys: frozenset[Union[int, str]]
    reader_person_keys: frozenset[Union[int, str]]
    answerer_person_keys: frozenset[Union[int, str]]
    first_answer_ordinal: Optional[int]


def _get_person_key(speaker_id: Optional[int], printed_name: str) -> Union[int, str]:
    if speaker_id is None:
        return printed_name
    return speaker_id


def _get_participant_rows(
    speech_asker_rows: list[SpeechAskerRow],
) -> list[_ParticipantRow]:
    return [
        _ParticipantRow(
            speech_asker_row.ordinal,
            speech_asker_row.speaker,
            speech_asker_row.transcript,
            speech_asker_row.speaker_id,
            _get_person_key(speech_asker_row.speaker_id, speech_asker_row.speaker),
        )
        for speech_asker_row in speech_asker_rows
        if speech_asker_row.speaker is not None
        and speech_asker_row.kind == SpeechKind.SPEECH
    ]


def _get_kept_asker_candidates(
    asker_candidates: list[AskerCandidate],
) -> list[AskerCandidate]:
    kept_asker_candidates: list[AskerCandidate] = []
    kept_person_keys: set[Union[int, str]] = set()
    for asker_candidate in asker_candidates:
        person_key = _get_person_key(
            asker_candidate.speaker_id, asker_candidate.printed_name
        )
        if person_key in kept_person_keys:
            continue
        kept_person_keys.add(person_key)
        kept_asker_candidates.append(asker_candidate)
    return kept_asker_candidates


def _get_question_ordinals(
    question_row_ordinals: frozenset[int], asker_candidates: list[AskerCandidate]
) -> frozenset[int]:
    candidate_ordinals = {
        asker_candidate.row_ordinal for asker_candidate in asker_candidates
    }
    reader_ordinals = {
        asker_candidate.reader_row_ordinal
        for asker_candidate in asker_candidates
        if asker_candidate.reader_row_ordinal is not None
    }
    return question_row_ordinals | candidate_ordinals | reader_ordinals


def _get_asker_role(asker_candidate: AskerCandidate) -> ParticipantRole:
    if asker_candidate.source == ReportAskerSource.STOOD_IN_NAME_LINE:
        return ParticipantRole.ABSENT_FILER
    return ParticipantRole.ASKER


def _build_asker_participants(
    kept_asker_candidates: list[AskerCandidate],
) -> list[ParticipantCandidate]:
    return [
        ParticipantCandidate(
            role=_get_asker_role(asker_candidate),
            role_source=ParticipantRoleSource.ASKER_RULES,
            first_ordinal=asker_candidate.row_ordinal,
            printed_name=asker_candidate.printed_name,
            speaker_id=asker_candidate.speaker_id,
        )
        for asker_candidate in kept_asker_candidates
    ]


def _build_reader_participants(
    kept_asker_candidates: list[AskerCandidate],
) -> list[ParticipantCandidate]:
    reader_participants: list[ParticipantCandidate] = []
    reader_person_keys: set[Union[int, str]] = set()
    for asker_candidate in kept_asker_candidates:
        if asker_candidate.reader_row_ordinal is None:
            continue
        if asker_candidate.reader_printed_name is None:
            continue
        person_key = _get_person_key(
            asker_candidate.reader_speaker_id, asker_candidate.reader_printed_name
        )
        if person_key in reader_person_keys:
            continue
        reader_person_keys.add(person_key)
        reader_participants.append(
            ParticipantCandidate(
                role=ParticipantRole.READER,
                role_source=ParticipantRoleSource.ASKER_RULES,
                first_ordinal=asker_candidate.reader_row_ordinal,
                printed_name=asker_candidate.reader_printed_name,
                speaker_id=asker_candidate.reader_speaker_id,
            )
        )
    return reader_participants


def _is_chair_name_call(transcript: str) -> bool:
    if len(transcript.split()) > _MAX_CHAIR_NAME_CALL_WORDS:
        return False
    return _CHAIR_NAME_CALL_PATTERN.search(transcript.strip()) is not None


def _get_chair_ordinal_to_source(
    participant_rows: list[_ParticipantRow],
) -> dict[int, ParticipantRoleSource]:
    chair_speaker_ids = {
        participant_row.speaker_id
        for participant_row in participant_rows
        if participant_row.speaker_id is not None
        and CHAIR_FORM_PATTERN.search(participant_row.label)
    }
    chair_ordinal_to_source: dict[int, ParticipantRoleSource] = {}
    for participant_row in participant_rows:
        if CHAIR_FORM_PATTERN.search(participant_row.label):
            chair_ordinal_to_source[participant_row.ordinal] = (
                ParticipantRoleSource.CHAIR_LABEL
            )
            continue
        if participant_row.speaker_id not in chair_speaker_ids:
            continue
        if _is_chair_name_call(participant_row.transcript):
            chair_ordinal_to_source[participant_row.ordinal] = (
                ParticipantRoleSource.CHAIR_NAME_CALL
            )
    return chair_ordinal_to_source


def _build_chair_participants(
    participant_rows: list[_ParticipantRow],
    chair_ordinal_to_source: dict[int, ParticipantRoleSource],
) -> list[ParticipantCandidate]:
    chair_participants: list[ParticipantCandidate] = []
    chair_person_keys: set[Union[int, str]] = set()
    for participant_row in participant_rows:
        role_source = chair_ordinal_to_source.get(participant_row.ordinal)
        if role_source is None:
            continue
        if participant_row.person_key in chair_person_keys:
            continue
        chair_person_keys.add(participant_row.person_key)
        chair_participants.append(
            ParticipantCandidate(
                role=ParticipantRole.CHAIR,
                role_source=role_source,
                first_ordinal=participant_row.ordinal,
                printed_name=participant_row.label,
                speaker_id=participant_row.speaker_id,
            )
        )
    return chair_participants


def _get_person_key_to_labels(
    participant_rows: list[_ParticipantRow],
) -> dict[Union[int, str], list[str]]:
    person_key_to_labels: dict[Union[int, str], list[str]] = {}
    for participant_row in participant_rows:
        labels = person_key_to_labels.setdefault(participant_row.person_key, [])
        if participant_row.label not in labels:
            labels.append(participant_row.label)
    return person_key_to_labels


def _has_government_label_office(label: str) -> bool:
    label_office = get_label_office(label)
    if label_office is None:
        return False
    return is_government_office(label_office)


def _get_answerer_source(
    labels: list[str],
    speaker_id: Optional[int],
    speaker_id_to_office: dict[int, Office],
) -> Optional[ParticipantRoleSource]:
    if any(_has_government_label_office(label) for label in labels):
        return ParticipantRoleSource.OFFICE_LABEL
    if speaker_id is None:
        return None
    office = speaker_id_to_office.get(speaker_id)
    if office is None:
        return None
    if is_government_office(office.printed):
        return ParticipantRoleSource.OFFICE_ON_THE_DAY
    return None


def _get_answering_for_printed(labels: list[str]) -> Optional[str]:
    for label in labels:
        answering_for_printed = get_answering_for_printed(label)
        if answering_for_printed is not None:
            return answering_for_printed
    return None


def _build_answerer_participant(
    first_row: _ParticipantRow, role_source: ParticipantRoleSource, labels: list[str]
) -> ParticipantCandidate:
    return ParticipantCandidate(
        role=ParticipantRole.ANSWERER,
        role_source=role_source,
        first_ordinal=first_row.ordinal,
        printed_name=first_row.label,
        speaker_id=first_row.speaker_id,
        answering_for_printed=_get_answering_for_printed(labels),
    )


def _build_answerer_participants(
    eligible_rows: list[_ParticipantRow],
    person_key_to_labels: dict[Union[int, str], list[str]],
    reader_person_keys: frozenset[Union[int, str]],
    speaker_id_to_office: dict[int, Office],
    first_question_ordinal: int,
) -> list[ParticipantCandidate]:
    person_key_to_first_row: dict[Union[int, str], _ParticipantRow] = {}
    for eligible_row in eligible_rows:
        person_key_to_first_row.setdefault(eligible_row.person_key, eligible_row)
    answerer_participants: list[ParticipantCandidate] = []
    for person_key, first_row in person_key_to_first_row.items():
        labels = person_key_to_labels[person_key]
        role_source = _get_answerer_source(
            labels, first_row.speaker_id, speaker_id_to_office
        )
        if role_source is None:
            continue
        answerer_participants.append(
            _build_answerer_participant(first_row, role_source, labels)
        )
    if answerer_participants:
        return answerer_participants
    position_row = next(
        (
            eligible_row
            for eligible_row in eligible_rows
            if eligible_row.ordinal > first_question_ordinal
            and eligible_row.person_key not in reader_person_keys
        ),
        None,
    )
    if position_row is None:
        return []
    return [
        _build_answerer_participant(
            position_row,
            ParticipantRoleSource.POSITION,
            person_key_to_labels[position_row.person_key],
        )
    ]


def _build_other_role_participant(
    participant_row: _ParticipantRow,
    role: ParticipantRole,
    role_source: ParticipantRoleSource,
) -> ParticipantCandidate:
    return ParticipantCandidate(
        role=role,
        role_source=role_source,
        first_ordinal=participant_row.ordinal,
        printed_name=participant_row.label,
        speaker_id=participant_row.speaker_id,
    )


def _build_row_participant(
    participant_row: _ParticipantRow, report_roles: _ReportRoles
) -> Optional[ParticipantCandidate]:
    if participant_row.ordinal in report_roles.chair_ordinals:
        return None
    person_key = participant_row.person_key
    if participant_row.ordinal in report_roles.question_ordinals:
        if person_key in report_roles.asker_person_keys:
            return None
        if person_key in report_roles.reader_person_keys:
            return None
        return _build_other_role_participant(
            participant_row, ParticipantRole.UNLABELLED, ParticipantRoleSource.NO_RULE
        )
    if _COLLECTIVE_LABEL_PATTERN.search(participant_row.label):
        return _build_other_role_participant(
            participant_row, ParticipantRole.UNLABELLED, ParticipantRoleSource.NO_RULE
        )
    if person_key in report_roles.answerer_person_keys:
        return None
    is_after_answer = (
        report_roles.first_answer_ordinal is not None
        and participant_row.ordinal > report_roles.first_answer_ordinal
    )
    if person_key in report_roles.asker_person_keys:
        if not is_after_answer:
            return None
        return _build_other_role_participant(
            participant_row,
            ParticipantRole.ASKER_FOLLOW_UP,
            ParticipantRoleSource.AFTER_ANSWER,
        )
    if person_key in report_roles.reader_person_keys and not is_after_answer:
        return None
    if is_after_answer:
        return _build_other_role_participant(
            participant_row,
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
        )
    return _build_other_role_participant(
        participant_row, ParticipantRole.UNLABELLED, ParticipantRoleSource.NO_RULE
    )


def _build_other_participants(
    participant_rows: list[_ParticipantRow], report_roles: _ReportRoles
) -> list[ParticipantCandidate]:
    other_participants: list[ParticipantCandidate] = []
    held_roles: set[tuple[ParticipantRole, Union[int, str]]] = set()
    for participant_row in participant_rows:
        participant = _build_row_participant(participant_row, report_roles)
        if participant is None:
            continue
        held_role = (participant.role, participant_row.person_key)
        if held_role in held_roles:
            continue
        held_roles.add(held_role)
        other_participants.append(participant)
    return other_participants


def _get_speaker_id_to_label_office(
    participant_rows: list[_ParticipantRow],
) -> dict[int, str]:
    speaker_id_to_label_office: dict[int, str] = {}
    for participant_row in participant_rows:
        if participant_row.speaker_id is None:
            continue
        if participant_row.speaker_id in speaker_id_to_label_office:
            continue
        label_office = get_label_office(participant_row.label)
        if label_office is None:
            continue
        speaker_id_to_label_office[participant_row.speaker_id] = label_office
    return speaker_id_to_label_office


def _get_office(
    speaker_id: int,
    speaker_id_to_label_office: dict[int, str],
    speaker_id_to_office: dict[int, Office],
) -> Optional[Office]:
    label_office = speaker_id_to_label_office.get(speaker_id)
    if label_office is not None:
        return Office(label_office, OfficeSource.LABEL_IN_REPORT)
    return speaker_id_to_office.get(speaker_id)


def _add_office_mark(
    participant: ParticipantCandidate,
    speaker_id_to_label_office: dict[int, str],
    speaker_id_to_office: dict[int, Office],
) -> ParticipantCandidate:
    if participant.speaker_id is None:
        return participant
    office = _get_office(
        participant.speaker_id, speaker_id_to_label_office, speaker_id_to_office
    )
    if office is None:
        return participant
    return replace(
        participant,
        office_printed=office.printed,
        office_class=get_office_class(office.printed),
        office_source=office.source,
    )


def _get_first_answer_ordinal(
    eligible_rows: list[_ParticipantRow],
    answerer_participants: list[ParticipantCandidate],
    answerer_person_keys: frozenset[Union[int, str]],
    first_question_ordinal: int,
) -> Optional[int]:
    return next(
        (
            eligible_row.ordinal
            for eligible_row in eligible_rows
            if eligible_row.ordinal > first_question_ordinal
            and eligible_row.person_key in answerer_person_keys
        ),
        min(
            (participant.first_ordinal for participant in answerer_participants),
            default=None,
        ),
    )


def get_participants(
    speech_asker_rows: list[SpeechAskerRow],
    asker_candidates: list[AskerCandidate],
    question_row_ordinals: frozenset[int],
    speaker_id_to_office: dict[int, Office],
) -> list[ParticipantCandidate]:
    question_ordinals = _get_question_ordinals(question_row_ordinals, asker_candidates)
    if not question_ordinals:
        return []
    participant_rows = _get_participant_rows(speech_asker_rows)
    kept_asker_candidates = _get_kept_asker_candidates(asker_candidates)
    asker_participants = _build_asker_participants(kept_asker_candidates)
    reader_participants = _build_reader_participants(kept_asker_candidates)
    chair_ordinal_to_source = _get_chair_ordinal_to_source(participant_rows)
    chair_participants = _build_chair_participants(
        participant_rows, chair_ordinal_to_source
    )
    asker_person_keys = frozenset(
        _get_person_key(participant.speaker_id, participant.printed_name)
        for participant in asker_participants
    )
    reader_person_keys = frozenset(
        _get_person_key(participant.speaker_id, participant.printed_name)
        for participant in reader_participants
    )
    first_question_ordinal = min(question_ordinals)
    eligible_rows = [
        participant_row
        for participant_row in participant_rows
        if participant_row.ordinal not in question_ordinals
        and participant_row.ordinal not in chair_ordinal_to_source
        and participant_row.person_key not in asker_person_keys
        and not _COLLECTIVE_LABEL_PATTERN.search(participant_row.label)
    ]
    answerer_participants = _build_answerer_participants(
        eligible_rows,
        _get_person_key_to_labels(participant_rows),
        reader_person_keys,
        speaker_id_to_office,
        first_question_ordinal,
    )
    answerer_person_keys = frozenset(
        _get_person_key(participant.speaker_id, participant.printed_name)
        for participant in answerer_participants
    )
    report_roles = _ReportRoles(
        question_ordinals=question_ordinals,
        chair_ordinals=frozenset(chair_ordinal_to_source),
        asker_person_keys=asker_person_keys,
        reader_person_keys=reader_person_keys,
        answerer_person_keys=answerer_person_keys,
        first_answer_ordinal=_get_first_answer_ordinal(
            eligible_rows,
            answerer_participants,
            answerer_person_keys,
            first_question_ordinal,
        ),
    )
    speaker_id_to_label_office = _get_speaker_id_to_label_office(participant_rows)
    return [
        _add_office_mark(participant, speaker_id_to_label_office, speaker_id_to_office)
        for participant in [
            *asker_participants,
            *reader_participants,
            *chair_participants,
            *answerer_participants,
            *_build_other_participants(participant_rows, report_roles),
        ]
    ]


def build_report_participants(
    report_id: int, participant_candidates: list[ParticipantCandidate]
) -> list[ReportParticipant]:
    sorted_candidates = sorted(
        participant_candidates,
        key=lambda participant_candidate: (
            participant_candidate.first_ordinal,
            _ROLE_ORDER.index(participant_candidate.role),
        ),
    )
    return [
        ReportParticipant(
            ordinal=ordinal,
            role=participant_candidate.role,
            role_source=participant_candidate.role_source,
            first_ordinal=participant_candidate.first_ordinal,
            printed_name=participant_candidate.printed_name,
            answering_for_printed=participant_candidate.answering_for_printed,
            office_printed=participant_candidate.office_printed,
            office_class=participant_candidate.office_class,
            office_source=participant_candidate.office_source,
            report_id=report_id,
            speaker_id=participant_candidate.speaker_id,
        )
        for ordinal, participant_candidate in enumerate(sorted_candidates, start=1)
    ]


def get_not_a_question_state(
    title: str,
    asker_candidates: list[AskerCandidate],
    question_row_ordinals: frozenset[int],
) -> Optional[QuestionStateCandidate]:
    if asker_candidates:
        return None
    is_non_question_title = _NOT_A_QUESTION_TITLE_PATTERN.search(title) is not None
    if not is_non_question_title and question_row_ordinals:
        return None
    return QuestionStateCandidate(QuestionState.NOT_A_QUESTION, title, None)


def _get_first_matching_row(
    speech_asker_rows: list[SpeechAskerRow], pattern: re.Pattern[str]
) -> Optional[SpeechAskerRow]:
    return next(
        (
            speech_asker_row
            for speech_asker_row in speech_asker_rows
            if pattern.search(speech_asker_row.transcript)
        ),
        None,
    )


def _has_asker_and_no_answerer(
    participant_candidates: list[ParticipantCandidate],
) -> bool:
    roles = {
        participant_candidate.role for participant_candidate in participant_candidates
    }
    if ParticipantRole.ANSWERER in roles:
        return False
    return ParticipantRole.ASKER in roles or ParticipantRole.ABSENT_FILER in roles


def get_question_states(
    title: str,
    speech_asker_rows: list[SpeechAskerRow],
    participant_candidates: list[ParticipantCandidate],
) -> list[QuestionStateCandidate]:
    question_states: list[QuestionStateCandidate] = []
    if _CORRECTION_TITLE_PATTERN.search(title):
        question_states.append(
            QuestionStateCandidate(QuestionState.CORRECTION, title, None)
        )
    private_notice_row = _get_first_matching_row(
        speech_asker_rows, _PRIVATE_NOTICE_PATTERN
    )
    if private_notice_row is not None:
        question_states.append(
            QuestionStateCandidate(
                QuestionState.URGENT,
                private_notice_row.transcript,
                private_notice_row.ordinal,
            )
        )
    if not _has_asker_and_no_answerer(participant_candidates):
        return question_states
    not_asked_aloud_row = _get_first_matching_row(
        speech_asker_rows, _NOT_ASKED_ALOUD_PATTERN
    )
    if not_asked_aloud_row is not None:
        question_states.append(
            QuestionStateCandidate(
                QuestionState.NOT_ASKED_ALOUD,
                not_asked_aloud_row.transcript,
                not_asked_aloud_row.ordinal,
            )
        )
    return question_states


def build_report_question_states(
    report_id: int, question_state_candidates: list[QuestionStateCandidate]
) -> list[ReportQuestionState]:
    return [
        ReportQuestionState(
            state=question_state_candidate.state,
            printed_text=question_state_candidate.printed_text,
            first_ordinal=question_state_candidate.first_ordinal,
            report_id=report_id,
        )
        for question_state_candidate in question_state_candidates
    ]

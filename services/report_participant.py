import re
from collections.abc import Callable
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
    get_nested_answering_for_name,
    get_office_class,
    is_government_office,
)

_MAX_CALLED_QUESTION_WORDS = 30
_MAX_CHAIR_NAME_CALL_WORDS = 8
_MAX_EXCLAMATION_QUIP_WORDS = 6
_MAX_INLINE_SPEAKER_LABEL_WORDS = 8
_MAX_QUESTION_QUIP_WORDS = 8
_MAX_REPLY_TO_CHAIR_WORDS = 6
_MIN_ANSWER_ROW_WORDS = 12
_MINISTER_CALL_TITLE = "Minister "
_THE_PREFIX = "The "
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
_CORRECTION_ROW_PATTERN = re.compile(
    r"\bsupplied\s+the\s+following\s+(?:additional\s+)?(?:answers?|information)\b",
    re.IGNORECASE,
)
_STANDING_ORDER_PATTERN = re.compile(r"standing\s+orders?\b", re.IGNORECASE)
_PROCEDURAL_PATTERN = re.compile(
    r"point\s+of\s+(?:order|clarification|information|elucidation)"
    r"|out\s+of\s+order|standing\s+orders?|general\s+assent|may\s+i\s+reply"
    r"|what\s+is\s+your\s+question|should\s+not\s+make\s+any\s+comment",
    re.IGNORECASE,
)
_BARE_REPLY_PATTERN = re.compile(r"^(?:yes|no|correct)\.$", re.IGNORECASE)
_WORD_PATTERN = re.compile(r"\w+")
_NON_ANSWER_PHRASE_PATTERN = re.compile(
    r"not\s+supposed\s+to\s+answer|reply\s+on\s+my\s+behalf"
    r"|leave\s+that\s+(?:entirely\s+)?to\s+you|allowing\s+me\s+to\s+join",
    re.IGNORECASE,
)
_EARLIER_QUESTION_PATTERN = re.compile(
    r"clarif\w+\s+(?:on|of)\s+my\s+previous\s+repl(?:y|ies)\b"
    r"|respond\s+to\s+the\s+earlier\s+clarification\b",
    re.IGNORECASE,
)
_ASKING_PATTERN = re.compile(
    r"\b(?:ask|have)\s+(?:a\s+)?supplementary"
    r"|(?:^|[,.]\s*)(?:a\s+)?supplementary\s+question\b"
    r"|\bmay\s+i\s+ask\b|\bmay\s+i\s+have\s+the\s+opportunity\s+to\s+ask\b"
    r"|(?:is|are)\s+the\s+minister\s+(?:not\s+)?aware|would\s+the\s+minister"
    r"|seek\s+(?:a\s+)?clarification|i\s+would\s+like\s+to\s+ask"
    r"|i\s+am\s+just\s+wondering"
    r"|\bcould\s+the\s+(?:hon\.?\s+)?member\b"
    r"|\bask\s+(?:a\s+)?clarification\s+(?:of|from)\b"
    r"|\bthe\s+leader\s+of\s+the\s+opposition\b[^.?!]*\?"
    r"|point\s+of\s+clarification\b[\s\S]*\?\s*$"
    r"|\b(?:will|would|can|could|does|is|are|has|did)\s+the\s+(?:\w+\.?\s+){0,5}"
    r"(?:minister|secretary)\b[^?]*\?\s*$",
    re.IGNORECASE,
)
_INLINE_SPEAKER_PATTERN = re.compile(
    r"^\s*(?P<label>(?:"
    + "|".join(re.escape(title) for title in (*TITLE_PREFIXES, _THE_PREFIX))
    + r")[^:?!;]{0,150}?)\s*:"
)
_BRACKET_PATTERN = re.compile(r"\([^)]*\)?")
_CALLED_QUESTION_PATTERN = re.compile(
    r"(?:^|[.?!]\s+)\W*questions?\s+(?:nos?\.?\s*|number\s*)?(?P<number>\d+)"
    r"(?:,?\s*(?:sir|please|madam|mdm\s+speaker|mr\s+speaker))*\W*$",
    re.IGNORECASE,
)
_COLLECTIVE_LABEL_PATTERN = re.compile(
    r"^\W*(?:(?:some|an?)\s+)?hon\.?\s+members?\W*$", re.IGNORECASE
)
_PRIVATE_NOTICE_PATTERN = re.compile(r"\(\s*by private notice", re.IGNORECASE)
_NOT_ASKED_ALOUD_PATTERN = re.compile(
    r"\b(?:stood\s+over|withdraw(?:n|al)?|postponed|deferred|not\s+reached|no\s+response"
    r"|is\s+not\s+here|stood\s+on\s+the\s+order\s+paper"
    r"|not\s+asking\b|do\s+not\s+ask\s+it|there\s+is\s+none"
    r"|who\s+is\s+answering|if\s+you\s+could\s+give\s+way"
    r"|appears\s+to\s+be\s+absent|does\s+not\s+appear\s+to\s+be\s+here)\b",
    re.IGNORECASE,
)
_STOOD_OVER_LIST_TITLE_PATTERN = re.compile(
    r"^\s*questions for oral answer stood over\b", re.IGNORECASE
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
    dropped_person_keys: frozenset[Union[int, str]]
    supplementary_person_keys: frozenset[Union[int, str]]
    first_answer_ordinal: Optional[int]


def _get_person_key(speaker_id: Optional[int], printed_name: str) -> Union[int, str]:
    if speaker_id is None:
        return printed_name
    return speaker_id


def _get_inline_speaker_label(transcript: str) -> Optional[str]:
    match = _INLINE_SPEAKER_PATTERN.search(transcript)
    if match is None:
        return None
    label = match.group("label")
    unbracketed_label = _BRACKET_PATTERN.sub("", label)
    if "," in unbracketed_label:
        return None
    if len(unbracketed_label.split()) > _MAX_INLINE_SPEAKER_LABEL_WORDS:
        return None
    return label


def read_inline_speakers(
    speech_asker_rows: list[SpeechAskerRow],
    get_speaker_id: Callable[[str], Optional[int]],
) -> list[SpeechAskerRow]:
    inline_speaker_rows: list[SpeechAskerRow] = []
    printed_speaker: Optional[str] = None
    inline_speaker: Optional[tuple[str, int]] = None
    for speech_asker_row in speech_asker_rows:
        if speech_asker_row.speaker is None or speech_asker_row.kind not in (
            None,
            SpeechKind.SPEECH,
        ):
            inline_speaker_rows.append(speech_asker_row)
            continue
        label = (
            None
            if CHAIR_FORM_PATTERN.search(speech_asker_row.speaker)
            else _get_inline_speaker_label(speech_asker_row.transcript)
        )
        speaker_id = None if label is None else get_speaker_id(label)
        if (
            label is not None
            and speaker_id is not None
            and speaker_id != speech_asker_row.speaker_id
        ):
            printed_speaker = speech_asker_row.speaker
            inline_speaker = (label, speaker_id)
        elif speech_asker_row.speaker != printed_speaker:
            inline_speaker = None
        if inline_speaker is None:
            inline_speaker_rows.append(speech_asker_row)
            continue
        inline_speaker_rows.append(
            replace(
                speech_asker_row,
                speaker=inline_speaker[0],
                speaker_id=inline_speaker[1],
            )
        )
    return inline_speaker_rows


def read_nested_label_speakers(
    speech_asker_rows: list[SpeechAskerRow],
    get_speaker_id: Callable[[str], Optional[int]],
) -> list[SpeechAskerRow]:
    speaker_ids_in_report = {
        speech_asker_row.speaker_id
        for speech_asker_row in speech_asker_rows
        if speech_asker_row.speaker_id is not None
    }
    nested_speaker_rows: list[SpeechAskerRow] = []
    for speech_asker_row in speech_asker_rows:
        if (
            speech_asker_row.speaker is None
            or speech_asker_row.speaker_id is not None
            or speech_asker_row.kind not in (None, SpeechKind.SPEECH)
        ):
            nested_speaker_rows.append(speech_asker_row)
            continue
        nested_name = get_nested_answering_for_name(speech_asker_row.speaker)
        speaker_id = None if nested_name is None else get_speaker_id(nested_name)
        if speaker_id in speaker_ids_in_report:
            speech_asker_row = replace(speech_asker_row, speaker_id=speaker_id)
        nested_speaker_rows.append(speech_asker_row)
    return nested_speaker_rows


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
        and speech_asker_row.kind in (None, SpeechKind.SPEECH)
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


def _get_government_row_ordinals(
    participant_rows: list[_ParticipantRow], speaker_id_to_office: dict[int, Office]
) -> frozenset[int]:
    government_row_ordinals: set[int] = set()
    for participant_row in participant_rows:
        if _has_government_label_office(participant_row.label):
            government_row_ordinals.add(participant_row.ordinal)
            continue
        office = (
            None
            if participant_row.speaker_id is None
            else speaker_id_to_office.get(participant_row.speaker_id)
        )
        if office is not None and is_government_office(office.printed):
            government_row_ordinals.add(participant_row.ordinal)
    return frozenset(government_row_ordinals)


def _get_called_question_ordinals(
    participant_rows: list[_ParticipantRow],
    asker_person_keys: frozenset[Union[int, str]],
) -> frozenset[int]:
    return frozenset(
        participant_row.ordinal
        for participant_row in participant_rows
        if not CHAIR_FORM_PATTERN.search(participant_row.label)
        and participant_row.person_key not in asker_person_keys
        and len(participant_row.transcript.split()) <= _MAX_CALLED_QUESTION_WORDS
        and _CALLED_QUESTION_PATTERN.search(participant_row.transcript)
        and not _is_asking(participant_row.transcript)
    )


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
    if (
        asker_candidate.source == ReportAskerSource.STOOD_IN_NAME_LINE
        or asker_candidate.reader_printed_name is not None
    ):
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


def _get_called_question_number(transcript: str) -> Optional[str]:
    match = _CALLED_QUESTION_PATTERN.search(transcript.strip())
    if match is None:
        return None
    return match.group("number")


def _build_second_reader_participants(
    participant_rows: list[_ParticipantRow],
    reader_participants: list[ParticipantCandidate],
    question_ordinals: frozenset[int],
    first_answer_ordinal: Optional[int],
    held_person_keys: frozenset[Union[int, str]],
) -> list[ParticipantCandidate]:
    ordinal_to_transcript = {
        participant_row.ordinal: participant_row.transcript
        for participant_row in participant_rows
    }
    second_reader_participants: list[ParticipantCandidate] = []
    second_reader_person_keys = set(held_person_keys)
    for reader_participant in reader_participants:
        reader_transcript = ordinal_to_transcript.get(reader_participant.first_ordinal)
        called_number = (
            None
            if reader_transcript is None
            else _get_called_question_number(reader_transcript)
        )
        if called_number is None:
            continue
        for participant_row in participant_rows:
            if (
                participant_row.ordinal <= reader_participant.first_ordinal
                or participant_row.ordinal not in question_ordinals
                or participant_row.person_key in second_reader_person_keys
                or (
                    first_answer_ordinal is not None
                    and participant_row.ordinal >= first_answer_ordinal
                )
                or _get_called_question_number(participant_row.transcript)
                != called_number
            ):
                continue
            second_reader_person_keys.add(participant_row.person_key)
            second_reader_participants.append(
                _build_other_role_participant(
                    participant_row,
                    ParticipantRole.READER,
                    ParticipantRoleSource.QUESTION_NUMBER_CALL,
                )
            )
    return second_reader_participants


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
    if office is None or office.source == OfficeSource.PARLIAMENT_GUESS:
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


def _is_asking(transcript: str) -> bool:
    text = transcript.strip()
    if _ASKING_PATTERN.search(text):
        return True
    return text.endswith("?") and len(text.split()) <= _MAX_QUESTION_QUIP_WORDS


def _does_row_answer(
    participant_row: _ParticipantRow, previous_label: Optional[str]
) -> bool:
    text = participant_row.transcript.strip()
    word_count = len(text.split())
    if _PROCEDURAL_PATTERN.search(text) or _is_asking(text):
        return False
    if text.endswith("!") and word_count <= _MAX_EXCLAMATION_QUIP_WORDS:
        return False
    return not (
        word_count <= _MAX_REPLY_TO_CHAIR_WORDS
        and previous_label is not None
        and CHAIR_FORM_PATTERN.search(previous_label)
    )


def _is_substantive_row(
    participant_row: _ParticipantRow, previous_label: Optional[str]
) -> bool:
    text = participant_row.transcript.strip()
    if len(text.split()) >= _MIN_ANSWER_ROW_WORDS:
        return True
    return (
        _BARE_REPLY_PATTERN.search(text) is not None
        and previous_label is not None
        and not CHAIR_FORM_PATTERN.search(previous_label)
    )


def _is_taken_up(run: list[_ParticipantRow], first_answerer_transcript: str) -> bool:
    first_answerer_text = first_answerer_transcript.lower()
    return all(
        word in first_answerer_text
        for run_row in run
        for word in _WORD_PATTERN.findall(run_row.transcript.lower())
    )


def _is_answering_run(
    run: list[_ParticipantRow],
    ordinal_to_label: dict[int, str],
    ordinal_to_first_answerer_transcript: dict[int, str],
) -> bool:
    if any(_NON_ANSWER_PHRASE_PATTERN.search(run_row.transcript) for run_row in run):
        return False
    if _EARLIER_QUESTION_PATTERN.search(run[0].transcript):
        return False
    if not all(
        _does_row_answer(run_row, ordinal_to_label.get(run_row.ordinal - 1))
        for run_row in run
    ):
        return False
    if any(
        _is_substantive_row(run_row, ordinal_to_label.get(run_row.ordinal - 1))
        for run_row in run
    ):
        return True
    next_first_answerer_transcript = ordinal_to_first_answerer_transcript.get(
        run[-1].ordinal + 1
    )
    return next_first_answerer_transcript is not None and _is_taken_up(
        run, next_first_answerer_transcript
    )


def _has_answering_run(
    person_rows: list[_ParticipantRow],
    ordinal_to_label: dict[int, str],
    ordinal_to_first_answerer_transcript: dict[int, str],
) -> bool:
    runs: list[list[_ParticipantRow]] = []
    for person_row in person_rows:
        if runs and runs[-1][-1].ordinal + 1 == person_row.ordinal:
            runs[-1].append(person_row)
        else:
            runs.append([person_row])
    for run in runs:
        if any(_is_asking(run_row.transcript) for run_row in run):
            return False
        if _is_answering_run(
            run, ordinal_to_label, ordinal_to_first_answerer_transcript
        ):
            return True
    return False


def _get_ordinal_to_first_answerer_transcript(
    answerer_participants: list[ParticipantCandidate],
    eligible_rows: list[_ParticipantRow],
) -> dict[int, str]:
    if not answerer_participants:
        return {}
    first_person_key = _get_person_key(
        answerer_participants[0].speaker_id, answerer_participants[0].printed_name
    )
    return {
        eligible_row.ordinal: eligible_row.transcript
        for eligible_row in eligible_rows
        if eligible_row.person_key == first_person_key
    }


def _split_non_answering_holders(
    answerer_participants: list[ParticipantCandidate],
    eligible_rows: list[_ParticipantRow],
    ordinal_to_label: dict[int, str],
) -> tuple[list[ParticipantCandidate], frozenset[Union[int, str]]]:
    kept_participants = answerer_participants[:1]
    dropped_person_keys: set[Union[int, str]] = set()
    ordinal_to_first_answerer_transcript = _get_ordinal_to_first_answerer_transcript(
        answerer_participants, eligible_rows
    )
    for answerer_participant in answerer_participants[1:]:
        person_key = _get_person_key(
            answerer_participant.speaker_id, answerer_participant.printed_name
        )
        person_rows = [
            eligible_row
            for eligible_row in eligible_rows
            if eligible_row.person_key == person_key
        ]
        if _has_answering_run(
            person_rows, ordinal_to_label, ordinal_to_first_answerer_transcript
        ):
            kept_participants.append(answerer_participant)
        else:
            dropped_person_keys.add(person_key)
    return kept_participants, frozenset(dropped_person_keys)


def _get_supplementary_person_keys(
    eligible_rows: list[_ParticipantRow],
    dropped_person_keys: frozenset[Union[int, str]],
    first_answer_ordinal: Optional[int],
) -> frozenset[Union[int, str]]:
    if first_answer_ordinal is None:
        return frozenset()
    return frozenset(
        eligible_row.person_key
        for eligible_row in eligible_rows
        if eligible_row.person_key in dropped_person_keys
        and eligible_row.ordinal > first_answer_ordinal
        and _is_asking(eligible_row.transcript)
    )


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
        if person_key in report_roles.answerer_person_keys:
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
    if person_key in report_roles.dropped_person_keys:
        if person_key not in report_roles.supplementary_person_keys:
            return _build_other_role_participant(
                participant_row,
                ParticipantRole.UNLABELLED,
                ParticipantRoleSource.NO_RULE,
            )
        if not is_after_answer:
            return None
        return _build_other_role_participant(
            participant_row,
            ParticipantRole.SUPPLEMENTARY,
            ParticipantRoleSource.AFTER_ANSWER,
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


def _drop_unlabelled_of_role_holders(
    participants: list[ParticipantCandidate],
) -> list[ParticipantCandidate]:
    role_holder_person_keys = {
        _get_person_key(participant.speaker_id, participant.printed_name)
        for participant in participants
        if participant.role != ParticipantRole.UNLABELLED
    }
    return [
        participant
        for participant in participants
        if participant.role != ParticipantRole.UNLABELLED
        or _get_person_key(participant.speaker_id, participant.printed_name)
        not in role_holder_person_keys
    ]


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
    title: str,
    speech_asker_rows: list[SpeechAskerRow],
    asker_candidates: list[AskerCandidate],
    question_row_ordinals: frozenset[int],
    speaker_id_to_office: dict[int, Office],
) -> list[ParticipantCandidate]:
    if _STOOD_OVER_LIST_TITLE_PATTERN.search(title):
        return []
    participant_rows = _get_participant_rows(speech_asker_rows)
    kept_asker_candidates = _get_kept_asker_candidates(asker_candidates)
    asker_participants = _build_asker_participants(kept_asker_candidates)
    asker_person_keys = frozenset(
        _get_person_key(participant.speaker_id, participant.printed_name)
        for participant in asker_participants
    )
    question_ordinals = _get_question_ordinals(
        (
            question_row_ordinals
            | _get_called_question_ordinals(participant_rows, asker_person_keys)
        )
        - _get_government_row_ordinals(participant_rows, speaker_id_to_office),
        asker_candidates,
    )
    if not question_ordinals:
        return []
    reader_participants = _build_reader_participants(kept_asker_candidates)
    chair_ordinal_to_source = _get_chair_ordinal_to_source(participant_rows)
    chair_participants = _build_chair_participants(
        participant_rows, chair_ordinal_to_source
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
    answerer_participants, dropped_person_keys = _split_non_answering_holders(
        _build_answerer_participants(
            eligible_rows,
            _get_person_key_to_labels(participant_rows),
            reader_person_keys,
            speaker_id_to_office,
            first_question_ordinal,
        ),
        eligible_rows,
        {
            participant_row.ordinal: participant_row.label
            for participant_row in participant_rows
        },
    )
    answerer_person_keys = frozenset(
        _get_person_key(participant.speaker_id, participant.printed_name)
        for participant in answerer_participants
    )
    first_answer_ordinal = _get_first_answer_ordinal(
        eligible_rows,
        answerer_participants,
        answerer_person_keys,
        first_question_ordinal,
    )
    second_reader_participants = _build_second_reader_participants(
        participant_rows,
        reader_participants,
        question_ordinals,
        first_answer_ordinal,
        asker_person_keys | reader_person_keys | answerer_person_keys,
    )
    report_roles = _ReportRoles(
        question_ordinals=question_ordinals,
        chair_ordinals=frozenset(chair_ordinal_to_source),
        asker_person_keys=asker_person_keys,
        reader_person_keys=reader_person_keys
        | frozenset(
            _get_person_key(participant.speaker_id, participant.printed_name)
            for participant in second_reader_participants
        ),
        answerer_person_keys=answerer_person_keys,
        dropped_person_keys=dropped_person_keys,
        supplementary_person_keys=_get_supplementary_person_keys(
            eligible_rows, dropped_person_keys, first_answer_ordinal
        ),
        first_answer_ordinal=first_answer_ordinal,
    )
    speaker_id_to_label_office = _get_speaker_id_to_label_office(participant_rows)
    return [
        _add_office_mark(participant, speaker_id_to_label_office, speaker_id_to_office)
        for participant in _drop_unlabelled_of_role_holders(
            [
                *asker_participants,
                *reader_participants,
                *second_reader_participants,
                *chair_participants,
                *answerer_participants,
                *_build_other_participants(participant_rows, report_roles),
            ]
        )
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
    speech_asker_rows: list[SpeechAskerRow],
    asker_candidates: list[AskerCandidate],
    question_row_ordinals: frozenset[int],
) -> Optional[QuestionStateCandidate]:
    if asker_candidates:
        return None
    if _get_correction_state(title, speech_asker_rows) is not None:
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


def _get_correction_state(
    title: str, speech_asker_rows: list[SpeechAskerRow]
) -> Optional[QuestionStateCandidate]:
    if _CORRECTION_TITLE_PATTERN.search(title):
        return QuestionStateCandidate(QuestionState.CORRECTION, title, None)
    correction_row = _get_first_matching_row(
        [
            speech_asker_row
            for speech_asker_row in speech_asker_rows
            if not _STANDING_ORDER_PATTERN.search(speech_asker_row.transcript)
        ],
        _CORRECTION_ROW_PATTERN,
    )
    if correction_row is None:
        return None
    return QuestionStateCandidate(
        QuestionState.CORRECTION, correction_row.transcript, correction_row.ordinal
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
    correction_state = _get_correction_state(title, speech_asker_rows)
    if correction_state is not None:
        question_states.append(correction_state)
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
    if _STOOD_OVER_LIST_TITLE_PATTERN.search(title):
        question_states.append(
            QuestionStateCandidate(QuestionState.NOT_ASKED_ALOUD, title, None)
        )
        return question_states
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

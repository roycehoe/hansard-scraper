import re
from dataclasses import dataclass, replace
from typing import Optional, Union

from crud.speech import SpeechAskerRow
from database.report_asker import ReportAsker
from enums import ReportAskerSource, SpeechKind
from utils.asker_candidate import AskerCandidate
from utils.names import CHAIR_FORM_PATTERN, TITLE_PREFIXES

_ROLE_LABEL_PATTERN = re.compile(CHAIR_FORM_PATTERN.pattern + r"|^The\s", re.IGNORECASE)
_ASKED_LINE_PATTERN = re.compile(
    r"^\s*(?:\(\s*by private notice[^)]*\)\s*)?"
    r"(?:asked(?:\s*the)?\b|ask\s+the\s+(?:\w+\s+){0,3}minister\b)",
    re.IGNORECASE,
)
_TO_ASK_LINE_PATTERN = re.compile(r"^\W*(?:\d+\s*\.?\s*)?to ask\b", re.IGNORECASE)
_STOOD_IN_NAME_PATTERN = re.compile(
    r"^[\s*>+_]*The following Questions?"
    r"(?:\s+(?:Nos?\.?\s*[\d,\sand]+|for oral answer))?"
    r"\s+stood in the names? of\s+(?P<name>.+?)"
    r"(?:\s*:|\s+[-–—]|[-–—](?=\s|$)|\s*$)",
    re.IGNORECASE,
)
_STOOD_OVER_LIST_TITLE_PATTERN = re.compile(
    r"^\s*questions for oral answer stood over\b", re.IGNORECASE
)
_TO_ASK_WORDS_PATTERN = re.compile(r"\bto ask\b", re.IGNORECASE)
_STOOD_QUESTION_NUMBER_PATTERN = re.compile(
    r"^\W*(?P<number>\d+)\s*\.?\s*to ask\b", re.IGNORECASE
)
_READ_OUT_PATTERN = re.compile(
    r"^\W*(?:on behalf of [^,.]{1,60}[,.]\s*)?"
    r"(?:(?:mr|madam|mdm) speaker,?\s*)?"
    r"(?:(?:sir|madam)[,.]?\s*)?"
    r"question\s+(?:no\.?\s*|number\s*)?(?P<number>\d+)",
    re.IGNORECASE,
)
_MEMBER_REFERENCE_REGEX = (
    r"(?:the member for|mr|mrs|mdm|madam|miss|ms|dr|inche|encik|tuan haji|haji)\b"
)
_ABSENT_FILER_READ_OUT_PATTERN = re.compile(
    r"^\W*(?:mr speaker,?\s*)?(?:sir,?\s*)?(?:"
    r"(?:since|as)\s[^.]{1,80}?\s(?:is|was)\s(?:not here|absent)\b"
    r"|(?:in the absence of|i have been (?:asked|requested) by)\s+"
    + _MEMBER_REFERENCE_REGEX
    + r")",
    re.IGNORECASE,
)
_RESPECTIVELY_SUFFIX_PATTERN = re.compile(r"\s+respectively$", re.IGNORECASE)
_FILER_SEPARATOR_PATTERN = re.compile(r",\s+|\s+and\s+", re.IGNORECASE)
_LETTER_PATTERN = re.compile(r"[^\W\d_]")
_NAME_IN_TEXT_PATTERN = re.compile(
    r"^\W*(?:\d+\s*\.?\s*)?(?P<name>(?:"
    + "|".join(re.escape(prefix) for prefix in TITLE_PREFIXES)
    + r").{0,80}?)\s+asked\s*the\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _StoodLine:
    row_index: int
    printed_names: tuple[str, ...]


def _get_stood_printed_names(transcript: str) -> Optional[tuple[str, ...]]:
    match = _STOOD_IN_NAME_PATTERN.search(transcript)
    if match is None:
        return None
    filers_text = _RESPECTIVELY_SUFFIX_PATTERN.sub("", match.group("name"))
    return tuple(
        printed_name
        for printed_name in _FILER_SEPARATOR_PATTERN.split(filers_text)
        if _LETTER_PATTERN.search(printed_name)
    )


def _get_stood_lines(speech_asker_rows: list[SpeechAskerRow]) -> list[_StoodLine]:
    stood_lines: list[_StoodLine] = []
    for row_index, speech_asker_row in enumerate(speech_asker_rows):
        printed_names = _get_stood_printed_names(speech_asker_row.transcript)
        if printed_names is None:
            continue
        is_last_row = row_index == len(speech_asker_rows) - 1
        if (
            is_last_row
            and _TO_ASK_WORDS_PATTERN.search(speech_asker_row.transcript) is None
        ):
            continue
        stood_lines.append(_StoodLine(row_index, printed_names))
    return stood_lines


def _get_stood_question_number(
    speech_asker_rows: list[SpeechAskerRow], stood_line: _StoodLine
) -> Optional[int]:
    question_row_index = stood_line.row_index + 1
    if question_row_index >= len(speech_asker_rows):
        return None
    match = _STOOD_QUESTION_NUMBER_PATTERN.search(
        speech_asker_rows[question_row_index].transcript
    )
    if match is None:
        return None
    return int(match.group("number"))


def _is_non_filer_member_speech(
    speech_asker_row: SpeechAskerRow, filer_names: tuple[str, ...]
) -> bool:
    if speech_asker_row.kind != SpeechKind.SPEECH:
        return False
    if speech_asker_row.speaker is None:
        return False
    if speech_asker_row.speaker_id is None:
        return False
    if _ROLE_LABEL_PATTERN.search(speech_asker_row.speaker):
        return False
    return not speech_asker_row.speaker.lower().startswith(filer_names)


def _get_read_out_number(
    speech_asker_row: SpeechAskerRow, filer_names: tuple[str, ...]
) -> Optional[int]:
    if not _is_non_filer_member_speech(speech_asker_row, filer_names):
        return None
    match = _READ_OUT_PATTERN.search(speech_asker_row.transcript)
    if match is None:
        return None
    return int(match.group("number"))


def _is_absent_filer_read_out(
    speech_asker_row: SpeechAskerRow, filer_names: tuple[str, ...]
) -> bool:
    if not _is_non_filer_member_speech(speech_asker_row, filer_names):
        return False
    return (
        _ABSENT_FILER_READ_OUT_PATTERN.search(speech_asker_row.transcript) is not None
    )


def _get_reader_row(
    speech_asker_rows: list[SpeechAskerRow],
    stood_lines: list[_StoodLine],
    stood_line: _StoodLine,
    filer_names: tuple[str, ...],
) -> Optional[SpeechAskerRow]:
    question_number = _get_stood_question_number(speech_asker_rows, stood_line)
    first_row_index = stood_line.row_index + 1
    next_stood_row_index = min(
        (
            other_stood_line.row_index
            for other_stood_line in stood_lines
            if other_stood_line.row_index > stood_line.row_index
        ),
        default=len(speech_asker_rows),
    )
    stood_block_rows = speech_asker_rows[first_row_index:next_stood_row_index]
    if question_number is not None:
        for speech_asker_row in speech_asker_rows[first_row_index:]:
            if _get_read_out_number(speech_asker_row, filer_names) == question_number:
                return speech_asker_row
        for speech_asker_row in stood_block_rows:
            if _is_absent_filer_read_out(speech_asker_row, filer_names):
                return speech_asker_row
        return None
    for speech_asker_row in stood_block_rows:
        if _get_read_out_number(speech_asker_row, filer_names) is not None:
            return speech_asker_row
        if _is_absent_filer_read_out(speech_asker_row, filer_names):
            return speech_asker_row
    return None


def _is_asked_or_to_ask_line(speech_asker_row: SpeechAskerRow) -> bool:
    return (
        _ASKED_LINE_PATTERN.search(speech_asker_row.transcript) is not None
        or _TO_ASK_LINE_PATTERN.search(speech_asker_row.transcript) is not None
    )


def _is_unnumbered_to_ask_line(speech_asker_row: SpeechAskerRow) -> bool:
    return (
        _TO_ASK_LINE_PATTERN.search(speech_asker_row.transcript) is not None
        and _STOOD_QUESTION_NUMBER_PATTERN.search(speech_asker_row.transcript) is None
    )


def _with_reader(
    asker_candidate: AskerCandidate, reader_row: SpeechAskerRow
) -> AskerCandidate:
    return replace(
        asker_candidate,
        reader_printed_name=reader_row.speaker,
        reader_speaker_id=reader_row.speaker_id,
        reader_row_ordinal=reader_row.ordinal,
    )


def _with_to_ask_reader(
    speech_asker_rows: list[SpeechAskerRow],
    row_index: int,
    asker_candidate: AskerCandidate,
) -> AskerCandidate:
    match = _STOOD_QUESTION_NUMBER_PATTERN.search(
        speech_asker_rows[row_index].transcript
    )
    filer_names = (asker_candidate.printed_name.lower(),)
    if match is not None:
        question_number = int(match.group("number"))
        for speech_asker_row in speech_asker_rows[row_index + 1 :]:
            if _get_read_out_number(speech_asker_row, filer_names) == question_number:
                return _with_reader(asker_candidate, speech_asker_row)
        return asker_candidate
    if row_index > 0 and _is_unnumbered_to_ask_line(speech_asker_rows[row_index - 1]):
        return asker_candidate
    for speech_asker_row in speech_asker_rows[row_index + 1 :]:
        if _is_asked_or_to_ask_line(speech_asker_row):
            break
        if _get_read_out_number(speech_asker_row, filer_names) is not None:
            return _with_reader(asker_candidate, speech_asker_row)
    return asker_candidate


def _get_stood_candidates(
    speech_asker_rows: list[SpeechAskerRow],
    stood_lines: list[_StoodLine],
    stood_line: _StoodLine,
    filer_names: tuple[str, ...],
) -> list[AskerCandidate]:
    row_ordinal = speech_asker_rows[stood_line.row_index].ordinal
    reader_row = _get_reader_row(
        speech_asker_rows, stood_lines, stood_line, filer_names
    )
    if reader_row is None:
        return [
            AskerCandidate(
                row_ordinal,
                ReportAskerSource.STOOD_IN_NAME_LINE,
                printed_name,
                None,
                None,
                None,
                None,
            )
            for printed_name in stood_line.printed_names
        ]
    return [
        AskerCandidate(
            row_ordinal,
            ReportAskerSource.STOOD_IN_NAME_LINE,
            printed_name,
            None,
            reader_row.speaker,
            reader_row.speaker_id,
            reader_row.ordinal,
        )
        for printed_name in stood_line.printed_names
    ]


def _get_speaker_row_candidate(
    speech_asker_row: SpeechAskerRow, is_to_ask_line_counted: bool
) -> Optional[AskerCandidate]:
    if speech_asker_row.speaker is None:
        return None
    if speech_asker_row.speaker_id is None:
        return None
    if speech_asker_row.kind is not None and speech_asker_row.kind != SpeechKind.SPEECH:
        return None
    if _ROLE_LABEL_PATTERN.search(speech_asker_row.speaker):
        return None
    if _ASKED_LINE_PATTERN.search(speech_asker_row.transcript):
        return AskerCandidate(
            speech_asker_row.ordinal,
            ReportAskerSource.ASKED_LINE,
            speech_asker_row.speaker,
            speech_asker_row.speaker_id,
            None,
            None,
            None,
        )
    if not is_to_ask_line_counted:
        return None
    if _TO_ASK_LINE_PATTERN.search(speech_asker_row.transcript):
        return AskerCandidate(
            speech_asker_row.ordinal,
            ReportAskerSource.TO_ASK_LINE,
            speech_asker_row.speaker,
            speech_asker_row.speaker_id,
            None,
            None,
            None,
        )
    return None


def _get_name_in_text_candidate(
    speech_asker_row: SpeechAskerRow,
) -> Optional[AskerCandidate]:
    if speech_asker_row.speaker is not None:
        return None
    if (
        speech_asker_row.kind is not None
        and speech_asker_row.kind != SpeechKind.SPEECH
        and speech_asker_row.kind != SpeechKind.UNCLASSIFIED
    ):
        return None
    match = _NAME_IN_TEXT_PATTERN.search(speech_asker_row.transcript)
    if match is None:
        return None
    printed_name = match.group("name")
    if CHAIR_FORM_PATTERN.search(printed_name):
        return None
    return AskerCandidate(
        speech_asker_row.ordinal,
        ReportAskerSource.NAME_IN_TEXT,
        printed_name,
        None,
        None,
        None,
        None,
    )


def get_asker_candidates(
    speech_asker_rows: list[SpeechAskerRow], report_title: str = ""
) -> list[AskerCandidate]:
    if _STOOD_OVER_LIST_TITLE_PATTERN.search(report_title) is not None:
        return []
    stood_lines = _get_stood_lines(speech_asker_rows)
    filer_names = tuple(
        printed_name.lower()
        for stood_line in stood_lines
        for printed_name in stood_line.printed_names
    )
    row_index_to_stood_line = {
        stood_line.row_index: stood_line for stood_line in stood_lines
    }
    stood_block_row_indexes = {
        stood_line.row_index + 1
        for stood_line in stood_lines
        if stood_line.printed_names
    }
    asker_candidates: list[AskerCandidate] = []
    for row_index, speech_asker_row in enumerate(speech_asker_rows):
        stood_line = row_index_to_stood_line.get(row_index)
        if stood_line is not None:
            asker_candidates.extend(
                _get_stood_candidates(
                    speech_asker_rows, stood_lines, stood_line, filer_names
                )
            )
            continue
        is_to_ask_line_counted = row_index not in stood_block_row_indexes and all(
            asker_candidate.source != ReportAskerSource.ASKED_LINE
            for asker_candidate in asker_candidates
        )
        speaker_row_candidate = _get_speaker_row_candidate(
            speech_asker_row, is_to_ask_line_counted
        )
        if speaker_row_candidate is not None:
            if speaker_row_candidate.source == ReportAskerSource.TO_ASK_LINE:
                speaker_row_candidate = _with_to_ask_reader(
                    speech_asker_rows, row_index, speaker_row_candidate
                )
            asker_candidates.append(speaker_row_candidate)
            continue
        name_in_text_candidate = _get_name_in_text_candidate(speech_asker_row)
        if name_in_text_candidate is not None:
            asker_candidates.append(name_in_text_candidate)
    return asker_candidates


def _is_question_row(speech_asker_row: SpeechAskerRow) -> bool:
    if _ASKED_LINE_PATTERN.search(speech_asker_row.transcript):
        return True
    if _TO_ASK_LINE_PATTERN.search(speech_asker_row.transcript):
        return True
    if _get_name_in_text_candidate(speech_asker_row) is not None:
        return True
    if speech_asker_row.speaker is None:
        return False
    if CHAIR_FORM_PATTERN.search(speech_asker_row.speaker):
        return False
    if _READ_OUT_PATTERN.search(speech_asker_row.transcript):
        return True
    return (
        _ABSENT_FILER_READ_OUT_PATTERN.search(speech_asker_row.transcript) is not None
    )


def get_question_row_ordinals(
    speech_asker_rows: list[SpeechAskerRow],
) -> frozenset[int]:
    question_row_ordinals = {
        speech_asker_row.ordinal
        for speech_asker_row in speech_asker_rows
        if _is_question_row(speech_asker_row)
    }
    for stood_line in _get_stood_lines(speech_asker_rows):
        question_row_ordinals.add(speech_asker_rows[stood_line.row_index].ordinal)
        question_row_index = stood_line.row_index + 1
        if question_row_index < len(speech_asker_rows):
            question_row_ordinals.add(speech_asker_rows[question_row_index].ordinal)
    return frozenset(question_row_ordinals)


def build_report_askers(
    report_id: int, asker_candidates: list[AskerCandidate]
) -> list[ReportAsker]:
    report_askers: list[ReportAsker] = []
    kept_asker_keys: set[Union[int, str]] = set()
    for asker_candidate in asker_candidates:
        asker_key = (
            asker_candidate.printed_name
            if asker_candidate.speaker_id is None
            else asker_candidate.speaker_id
        )
        if asker_key in kept_asker_keys:
            continue
        kept_asker_keys.add(asker_key)
        report_askers.append(
            ReportAsker(
                ordinal=len(report_askers) + 1,
                printed_name=asker_candidate.printed_name,
                source=asker_candidate.source,
                reader_printed_name=asker_candidate.reader_printed_name,
                report_id=report_id,
                speaker_id=asker_candidate.speaker_id,
                reader_speaker_id=asker_candidate.reader_speaker_id,
            )
        )
    return report_askers

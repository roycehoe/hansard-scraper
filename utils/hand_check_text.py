import difflib
import html
import re
from dataclasses import dataclass
from typing import Optional

from enums import HandCheckDifferenceKind

_EQUAL_OPCODE = "equal"
_DELETE_OPCODE = "delete"
_LINE_BREAK_TAG_RE = re.compile(r"<br\b[^<>]*>", re.IGNORECASE)
# NOTE: a tag opens with a letter or a slash, so "<5%" in running text is not one.
_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
# NOTE: every underscore goes, as nothing tells an emphasis mark from a printed one. A lone "*" is not a marker and stays.
_MARKDOWN_MARKER_RE = re.compile(r"\*\*|_")
_WHITESPACE_RE = re.compile(r"\s+")
_LANGUAGE_NOTE_PATTERN = r"\((?:in|dalam) (?:Mandar\w+|Malay|English|Tamil|Hokkien|Cantonese|Teochew|Hakka)\)"
_BRACKETED_DIRECTION_RE = re.compile(r"\[[^\[\]]+\]\.?")


@dataclass(frozen=True)
class WordDifference:
    operation: str
    source_words: str
    row_words: str
    kind: Optional[HandCheckDifferenceKind] = None


@dataclass(frozen=True)
class RowContext:
    speaker: Optional[str]
    turn_first_paragraph: Optional[str]
    next_speaker: Optional[str]
    next_transcript: Optional[str]


def normalize_hand_check_text(text: str) -> str:
    # NOTE: tags go before references are decoded, so an escaped "&lt;b&gt;" stays text.
    text = _LINE_BREAK_TAG_RE.sub(" ", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _MARKDOWN_MARKER_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _is_printed_before_label(
    question_number: str, label: str, row_context: RowContext
) -> bool:
    if row_context.turn_first_paragraph is None:
        return False
    return (
        re.match(
            rf"{re.escape(question_number)} ?{re.escape(label)}",
            normalize_hand_check_text(row_context.turn_first_paragraph),
            re.IGNORECASE,
        )
        is not None
    )


def _get_turn_start_kind(
    source_words: str, row_context: RowContext
) -> Optional[HandCheckDifferenceKind]:
    if row_context.speaker is None:
        return None
    label = normalize_hand_check_text(row_context.speaker)
    # NOTE: what the archive leaves out at the start of a turn, in printed order and possibly unspaced: the question number (register line 87), the row's own label, a language note (line 84) and the colon.
    match = re.fullmatch(
        rf"(?P<question_number>\d+\.?)? ?(?P<label>{re.escape(label)})? ?(?P<language_note>{_LANGUAGE_NOTE_PATTERN})? ?(?P<colon>:)?",
        source_words,
        re.IGNORECASE,
    )
    if match is None or not any(match.groupdict().values()):
        return None
    question_number = match.group("question_number")
    # NOTE: a number is a question number only where the turn prints it before the label, as register line 87 says; a list number lost elsewhere still flags (triage ruling T3, 2 Nov 2026).
    if question_number and not _is_printed_before_label(
        question_number, label, row_context
    ):
        return None
    if match.group("language_note"):
        return HandCheckDifferenceKind.LANGUAGE_NOTE
    if question_number:
        return HandCheckDifferenceKind.QUESTION_NUMBER
    return HandCheckDifferenceKind.LABEL


def _is_chamber_event_cut(source_words: str, row_context: RowContext) -> bool:
    # NOTE: a bracketed direction cut out of the paragraph becomes the next row, a chamber event with no speaker (register line 82).
    return (
        row_context.next_speaker is None
        and row_context.next_transcript is not None
        and _BRACKETED_DIRECTION_RE.fullmatch(source_words) is not None
        and source_words == normalize_hand_check_text(row_context.next_transcript)
    )


def _get_difference_kind(
    operation: str,
    source_start: int,
    source_words: str,
    row_context: Optional[RowContext],
) -> Optional[HandCheckDifferenceKind]:
    if row_context is None or operation != _DELETE_OPCODE:
        return None
    if source_start == 0:
        turn_start_kind = _get_turn_start_kind(source_words, row_context)
        if turn_start_kind is not None:
            return turn_start_kind
    if _is_chamber_event_cut(source_words, row_context):
        return HandCheckDifferenceKind.CHAMBER_EVENT_CUT
    return None


def get_word_differences(
    source_text: str, row_text: str, row_context: Optional[RowContext] = None
) -> list[WordDifference]:
    source_words = normalize_hand_check_text(source_text).split()
    row_words = normalize_hand_check_text(row_text).split()
    word_differences = []
    for (
        operation,
        source_start,
        source_end,
        row_start,
        row_end,
    ) in difflib.SequenceMatcher(
        a=source_words, b=row_words, autojunk=False
    ).get_opcodes():
        if operation == _EQUAL_OPCODE:
            continue
        source_run = " ".join(source_words[source_start:source_end])
        word_differences.append(
            WordDifference(
                operation=operation,
                source_words=source_run,
                row_words=" ".join(row_words[row_start:row_end]),
                kind=_get_difference_kind(
                    operation, source_start, source_run, row_context
                ),
            )
        )
    return word_differences

import difflib
import html
import re
from dataclasses import dataclass

_EQUAL_OPCODE = "equal"
_LINE_BREAK_TAG_RE = re.compile(r"<br\b[^<>]*>", re.IGNORECASE)
# NOTE: a tag opens with a letter or a slash, so "<5%" in running text is not one.
_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
# NOTE: every underscore goes, as nothing tells an emphasis mark from a printed one. A lone "*" is not a marker and stays.
_MARKDOWN_MARKER_RE = re.compile(r"\*\*|_")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class WordDifference:
    operation: str
    source_words: str
    row_words: str


def normalize_hand_check_text(text: str) -> str:
    # NOTE: tags go before references are decoded, so an escaped "&lt;b&gt;" stays text.
    text = _LINE_BREAK_TAG_RE.sub(" ", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _MARKDOWN_MARKER_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def get_word_differences(source_text: str, row_text: str) -> list[WordDifference]:
    source_words = normalize_hand_check_text(source_text).split()
    row_words = normalize_hand_check_text(row_text).split()
    return [
        WordDifference(
            operation=operation,
            source_words=" ".join(source_words[source_start:source_end]),
            row_words=" ".join(row_words[row_start:row_end]),
        )
        for operation, source_start, source_end, row_start, row_end in difflib.SequenceMatcher(
            a=source_words, b=row_words, autojunk=False
        ).get_opcodes()
        if operation != _EQUAL_OPCODE
    ]

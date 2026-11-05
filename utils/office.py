import re
from dataclasses import dataclass
from typing import Optional

from enums import OfficeClass, OfficeSource
from utils.names import (
    CHAIR_FORM_PATTERN,
    CLOSING_PARENTHESIS,
    MP_NAME_SEPARATOR,
    OPENING_PARENTHESIS,
    strip_title,
)

_THE_PREFIX = "The "
_BARE_PRIME_MINISTER_LABEL = "Prime Minister"
_HEADER_NAME_SEPARATOR = ", "
_HEADER_NAME_TRAILING_CHARACTERS = " ,"
_APOSTROPHE_VARIANT = "’"

_TITLE_DOT_PREFIX_PATTERN = re.compile(r"^(Mr|Mrs|Dr|Ms)\.\s+")
_WHITESPACE_RUN_PATTERN = re.compile(r"\s+")
_LOST_SPACE_PATTERN = re.compile(
    r"(?<=[a-z])(?=(?:Minister|Ministry|Senior|Parliamentary|Secretary|State)\b)"
)
_ANSWERING_FOR_PATTERN = re.compile(
    r"^(?:for(?![a-z])|forthe\b|on\s+behalf\b)", re.IGNORECASE
)
_HEADER_OFFICE_WORD_PATTERN = re.compile(
    r"minister|secretary|speaker|leader of the house|attorney|whip|chairman|mayor",
    re.IGNORECASE,
)

_SERVED_MINISTER_PATTERN = re.compile(
    r"(parliamentary secretary|minister of state),? to the .*?"
    r"(?=(?:,| and )\s*(?:senior |acting |second |deputy |coordinating )?minister\b(?! for)|$)"
)
_NON_OFFICE_PHRASE_PATTERN = re.compile(r"prime minister's \w+|ministry of [a-z ]+")
_PRIME_MINISTER_PATTERN = re.compile(r"(?:^|\bthe |, |\band )prime minister\b")
_DEPUTY_PRIME_MINISTER_PATTERN = re.compile(r"deputy prime minister")
_MINISTER_PATTERN = re.compile(r"(?<!chief )(?<!assistant )\bminister\b(?! of state)")
_SENIOR_MINISTER_OF_STATE_PATTERN = re.compile(r"senior minister of state")
_MINISTER_OF_STATE_PATTERN = re.compile(r"minister of state")
_SENIOR_PARLIAMENTARY_SECRETARY_PATTERN = re.compile(r"senior parliamentary secretary")
_PARLIAMENTARY_SECRETARY_PATTERN = re.compile(r"parliamentary secretary")
_GOVERNMENT_OFFICE_PATTERN = re.compile(
    r"\bministers?\b|parliamentary secretary|leader of the house|attorney"
    r"|chief secretary|financial secretary"
)


@dataclass(frozen=True)
class Office:
    printed: str
    source: OfficeSource


@dataclass(frozen=True)
class HeaderEntry:
    printed_name: str
    office_printed: Optional[str]


@dataclass(frozen=True)
class _Bracket:
    start: int
    end: int
    inner: str


@dataclass(frozen=True)
class _LabelParts:
    name: Optional[str]
    office: Optional[str]
    answering_for: Optional[str]
    nested_answering_for_name: Optional[str] = None


def _get_brackets(text: str) -> list[_Bracket]:
    brackets = []
    depth = 0
    start = 0
    for index, character in enumerate(text):
        if character == OPENING_PARENTHESIS:
            if depth == 0:
                start = index
            depth += 1
        elif character == CLOSING_PARENTHESIS and depth > 0:
            depth -= 1
            if depth == 0:
                brackets.append(
                    _Bracket(start, index + 1, text[start + 1 : index].strip())
                )
    return brackets


def _remove_brackets(text: str, brackets: list[_Bracket]) -> str:
    for bracket in reversed(brackets):
        text = text[: bracket.start] + text[bracket.end :]
    return _WHITESPACE_RUN_PATTERN.sub(" ", text).strip()


def _is_name_bracket(bracket: _Bracket) -> bool:
    inner = _TITLE_DOT_PREFIX_PATTERN.sub(r"\1 ", bracket.inner)
    return strip_title(inner) != inner


def _is_answering_for_bracket(bracket: _Bracket) -> bool:
    return _ANSWERING_FOR_PATTERN.search(bracket.inner) is not None


def _is_office_text(text: str) -> bool:
    if CHAIR_FORM_PATTERN.search(text) or text == _BARE_PRIME_MINISTER_LABEL:
        return True
    return text.startswith(_THE_PREFIX) and strip_title(text) == text


def _split_label(label: str) -> _LabelParts:
    label = label.strip()
    brackets = _get_brackets(label)
    answering_for_brackets = [
        bracket for bracket in brackets if _is_answering_for_bracket(bracket)
    ]
    answering_for = answering_for_brackets[0].inner if answering_for_brackets else None
    name_bracket = next(
        (bracket for bracket in reversed(brackets) if _is_name_bracket(bracket)), None
    )
    if name_bracket is None:
        remainder = _remove_brackets(label, answering_for_brackets)
        if _is_office_text(remainder):
            return _LabelParts(None, remainder, answering_for)
        return _LabelParts(None, None, answering_for)
    before_name_bracket = _remove_brackets(
        label[: name_bracket.start],
        [
            bracket
            for bracket in answering_for_brackets
            if bracket.end <= name_bracket.start
        ],
    )
    if CHAIR_FORM_PATTERN.search(name_bracket.inner):
        return _LabelParts(before_name_bracket, name_bracket.inner, answering_for)
    nested_answering_for_bracket = next(
        (
            bracket
            for bracket in _get_brackets(name_bracket.inner)
            if _is_answering_for_bracket(bracket)
        ),
        None,
    )
    if nested_answering_for_bracket is None:
        return _LabelParts(
            name_bracket.inner, before_name_bracket or None, answering_for
        )
    nested_answering_for_name = _remove_brackets(
        name_bracket.inner, [nested_answering_for_bracket]
    )
    return _LabelParts(
        name_bracket.inner,
        before_name_bracket or None,
        answering_for or nested_answering_for_bracket.inner,
        nested_answering_for_name,
    )


def get_label_office(speaker_label: str) -> Optional[str]:
    return _split_label(speaker_label).office


def get_answering_for_printed(speaker_label: str) -> Optional[str]:
    return _split_label(speaker_label).answering_for


def get_nested_answering_for_name(speaker_label: str) -> Optional[str]:
    return _split_label(speaker_label).nested_answering_for_name


def _is_header_entry_start(text: str) -> bool:
    return text.startswith(_THE_PREFIX) or strip_title(text) != text


def _split_header_entries(text: str) -> list[str]:
    entries = []
    depth = 0
    start = 0
    for index, character in enumerate(text):
        if character == OPENING_PARENTHESIS:
            depth += 1
        elif character == CLOSING_PARENTHESIS and depth > 0:
            depth -= 1
        elif (
            depth == 0
            and text.startswith(_HEADER_NAME_SEPARATOR, index)
            and _is_header_entry_start(text[index + len(_HEADER_NAME_SEPARATOR) :])
        ):
            entries.append(text[start:index])
            start = index + len(_HEADER_NAME_SEPARATOR)
    entries.append(text[start:])
    return entries


def _build_header_entry(entry: str) -> HeaderEntry:
    if entry.startswith(_THE_PREFIX) and strip_title(entry) == entry:
        label_parts = _split_label(entry)
        if label_parts.name is not None:
            return HeaderEntry(label_parts.name, label_parts.office)
    title_length = len(entry) - len(strip_title(entry))
    brackets = [
        bracket for bracket in _get_brackets(entry) if bracket.start >= title_length
    ]
    if not brackets:
        return HeaderEntry(entry, None)
    printed_name = entry[: brackets[0].start].strip(_HEADER_NAME_TRAILING_CHARACTERS)
    office_bracket = next(
        (
            bracket
            for bracket in brackets
            if not _is_answering_for_bracket(bracket)
            and _HEADER_OFFICE_WORD_PATTERN.search(bracket.inner)
        ),
        None,
    )
    if office_bracket is None:
        return HeaderEntry(printed_name, None)
    return HeaderEntry(printed_name, office_bracket.inner)


def get_header_entries(header: str) -> list[HeaderEntry]:
    entries = []
    for piece in header.split(MP_NAME_SEPARATOR):
        for entry in _split_header_entries(piece):
            stripped = entry.strip()
            if stripped:
                entries.append(_build_header_entry(stripped))
    return entries


def _normalize_office_text(office_printed: str) -> str:
    text = _LOST_SPACE_PATTERN.sub(" ", office_printed).lower()
    text = text.replace(_APOSTROPHE_VARIANT, "'")
    text = _SERVED_MINISTER_PATTERN.sub(r"\1", text)
    return _NON_OFFICE_PHRASE_PATTERN.sub("", text)


def get_office_class(office_printed: str) -> OfficeClass:
    text = _normalize_office_text(office_printed)
    if _PRIME_MINISTER_PATTERN.search(text):
        return OfficeClass.PRIME_MINISTER
    if _DEPUTY_PRIME_MINISTER_PATTERN.search(text):
        return OfficeClass.DEPUTY_PRIME_MINISTER
    if _MINISTER_PATTERN.search(text):
        return OfficeClass.MINISTER
    if _SENIOR_MINISTER_OF_STATE_PATTERN.search(text):
        return OfficeClass.SENIOR_MINISTER_OF_STATE
    if _MINISTER_OF_STATE_PATTERN.search(text):
        return OfficeClass.MINISTER_OF_STATE
    if _SENIOR_PARLIAMENTARY_SECRETARY_PATTERN.search(text):
        return OfficeClass.SENIOR_PARLIAMENTARY_SECRETARY
    if _PARLIAMENTARY_SECRETARY_PATTERN.search(text):
        return OfficeClass.PARLIAMENTARY_SECRETARY
    return OfficeClass.OTHER


def is_government_office(office_printed: str) -> bool:
    return (
        _GOVERNMENT_OFFICE_PATTERN.search(_normalize_office_text(office_printed))
        is not None
    )

# NOTE: the Chairman is not looked up by date, because the chair changes within a sitting.

import bisect
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Iterable, Optional, Sequence

from crud.attendance import AttendanceSpeakerRow
from crud.speech import SpeechRow, SpeechSpeakerRow
from enums import ReportVersion
from schemas.hansard_report_response import HansardReportSection
from utils.markdown_parser import (
    ASTERISK,
    BYTE_ORDER_MARK,
    EMPHASIS_MARK,
    get_cleaned_report_markdown,
)
from utils.names import (
    CLOSING_PARENTHESIS,
    LABEL_COLON,
    MP_NAME_SEPARATOR,
    OPENING_PARENTHESIS,
    normalize_name,
    strip_title,
)
from utils.parliament_numbers import VOLUME_TO_PARLIAMENT
from utils.speaker_resolution import SpeakerLookups, resolve_canonical_name
from utils.speaker_resolution_constants import (
    COLONIAL_PARLIAMENT_FALLBACKS,
    DATED_ROLE_TERMS,
    DEPUTY_SPEAKER_TERMS,
    DEPUTY_SPEAKER_WOMEN,
    HEAD_OF_STATE_TERMS,
    NON_SPEAKERS,
    ROLE_ONLY_SPEAKERS,
    SPEAKER_WOMEN,
)
from utils.speaker_terms import SPEAKER_TERMS


class ChairRole(StrEnum):
    SPEAKER = "speaker"
    DEPUTY_SPEAKER = "deputy speaker"


CHAIRMAN_RE = re.compile(r"^(?:the ?|mr ?)?chairman:?$", re.IGNORECASE)
_ANNOTATION_RE = re.compile(r"\[([^\]\[]{0,90}?)\s*(?:temporarily\s+)?in the Chair\]", re.IGNORECASE)
_CHAIR_EVENT_RE = re.compile(
    r"Thereupon,? (?:Mr|Mdm) (Deputy Speaker|Speaker)\s*(?:\([^)]*\))? (?:left|took|resumed|vacated)[^.]{0,30}the Chair",
    re.IGNORECASE,
)
_HEADER_RE = re.compile(r"MPs Speaking:\|([^\n]*)")
_HEADER_TAG_RE = re.compile(r"^\s*(.*?)\s*\((?:Mr|Mdm) (Deputy Speaker|Speaker)\)\s*$", re.IGNORECASE)
_SPEAKER_ROLE_RE = re.compile(r"^(?:Mr|Mdm)\s*Speaker$", re.IGNORECASE)
_DEPUTY_ROLE_RE = re.compile(r"^(?:Mr|Mdm)\s*Deputy\s*Speaker$", re.IGNORECASE)
_DEPUTY_MENTION_RE = re.compile(r"Deputy\s*Speaker", re.IGNORECASE)
_NAMED_DEPUTY_RE = re.compile(r"Deputy\s*Speaker\s*\(([^)]+)\)", re.IGNORECASE)
_TITLE_RE = re.compile(r"^(?:Mr|Mdm|Dr|Sir|Mrs|Ms)\s+")
BARE_DEPUTY_RE = re.compile(r"^mr deputy speaker:?$", re.IGNORECASE)
_NAMED_DEPUTY_ROW_RE = re.compile(r"^(?:Mr|Mdm)\s*Deputy\s*Speaker\s*\(([^)]+)\)", re.IGNORECASE)
_NAMED_DEPUTY_LABEL_RE = re.compile(r"(?:Mr|Mdm)\s*Deputy\s*Speaker\s*\(([^)]+)\)\s*:", re.IGNORECASE)
_SPEAKER_LABEL_RE = re.compile(r"\b(?:Mr|Mdm|Madam)\s*Speaker\s*:", re.IGNORECASE)
_SUSPENSION_RE = re.compile(r"Sitting (?:was )?suspended|Sitting resumed|resumed at \d", re.IGNORECASE)
_MEMBER_LABEL_TAIL = r"\s*(?:\([^)]*\))?\s*:"
_LABEL_TRAILING_CHARACTERS = ";, "
_NON_LETTER_RE = re.compile(r"[^a-z ]")
_TRAILING_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\s*$")
_ALIGN_KEY_LENGTH = 35
_MIN_ALIGN_KEY_LENGTH = 12
_EVENT_SLACK = 3
_TITLE_WORDS = frozenset({"mr", "mdm", "ms", "mrs", "dr", "sir"})
_CARRIED_HOLDER_OPENER = " ("

CARRIED_ROLES = ("The Chief Secretary",)

_WOMAN_SPEAKER_LABEL = "Mdm Speaker"
_WOMAN_TITLE_PREFIX = "Mdm"
_SPEAKER_LABELS = ("Mr Speaker", _WOMAN_SPEAKER_LABEL)
_DEPUTY_SPEAKER_LABELS = ("Mr Deputy Speaker", "Mr DeputySpeaker", "Mdm Deputy Speaker", "Mdm DeputySpeaker", "The Deputy Speaker")

DATE_DEPENDENT_ROLES = (*DATED_ROLE_TERMS, *_SPEAKER_LABELS, *_DEPUTY_SPEAKER_LABELS)

_LEADING_LIST_NUMBER_RE = re.compile(r"^\d+\\?\.\s*")
_LEADING_DOT_RE = re.compile(r"^\.\s+")
_ASSOC_PROF_RE = re.compile(r"\bAssoc\.Prof\.")
_RANK_QUALIFIER_RE = re.compile(r"\s*[\[(](?:NS|Res)[\])]\s*")
_TRAILING_MR_SPEAKER_RE = re.compile(r"\s+Mr Speaker,?$")
_LEADING_QUOTE_RE = re.compile(r"^[\"“”'‘’]+")
_TRAILING_DASH_RE = re.compile(r"\s*[–—-]+$")
_TRAILING_NAME_DOT_RE = re.compile(r"(?<=[A-Za-z]{3})\.$")
_UPPERCASE_TITLE_RE = re.compile(r"^(?:MR|MRS|MS|DR|MDM|PROF)\b")
_PRESIDING_BRACKET_RE = re.compile(r"\s*\((?:Mr|Mdm) Speaker\)$")
_WHITESPACE_RE = re.compile(r"\s+")
_INVERTED_NAME_RE = re.compile(r"^([A-Z][a-z]+), ([A-Z][a-z]+)$")
_DOUBLED_LABEL_RE = re.compile(r"^(.{6,}?)\s+\1$")
_PARENTHESIS_RE = re.compile(r"\(([^)]+)\)")
_TITLE_DOT_PREFIX_RE = re.compile(r"^(Mr|Mrs|Dr|Ms)\.\s+")
_GLUED_TITLE_RE = re.compile(r"^(Mr|Mrs|Dr|Ms|Mdm)([A-Z])")
_TITLED_RE = re.compile(r"^(?:Mr|Mrs|Ms|Mdm|Dr|Miss|Inche|Encik|Assoc|Prof|Er)\b")

_ADDRESS_TITLES = ("GOVERNOR'S ADDRESS", "PRESIDENT'S ADDRESS", "YANG DI-PERTUAN NEGARA'S SPEECH")

# NOTE: SPRS prints these labels without the opening bracket.
_LABELS_MISSING_OPENING_BRACKET = {
    "Inche Mohd. Ali Bin Alwi Kampong Kembangan)": "Inche Mohd. Ali Bin Alwi (Kampong Kembangan)",
    "Ms Foo Mee Har West Coast)": "Ms Foo Mee Har (West Coast)",
}


@dataclass(frozen=True)
class DeputySpeakerNames:
    speech_id_to_deputy_name: dict[int, str]
    labelled: set[str]
    mentioned: set[str]


@dataclass(frozen=True)
class ChairMark:
    position: int
    end: int
    deputy_name: Optional[str]


@dataclass(frozen=True)
class SectionSpan:
    title: str
    start: int
    end: int


@dataclass(frozen=True)
class SittingText:
    text: str
    section_spans: list[SectionSpan]
    chair_marks: list[ChairMark]


@dataclass(frozen=True)
class ChairAnnotation:
    position: int
    text: str


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.replace(ASTERISK, "")).strip()


def _get_header_holders(markdown: str) -> dict[str, set[str]]:
    header = _HEADER_RE.search(markdown)
    if header is None:
        return {}
    role_to_holder_names: dict[str, set[str]] = {}
    for entry in header.group(1).split(MP_NAME_SEPARATOR):
        tag = _HEADER_TAG_RE.match(entry.replace(ASTERISK, ""))
        if tag is not None:
            role_to_holder_names.setdefault(tag.group(2).lower(), set()).add(_TITLE_RE.sub("", tag.group(1).strip()))
    return role_to_holder_names


def _get_positions(normalized_text: str, speech_rows: list[SpeechRow]) -> list[Optional[int]]:
    positions: list[Optional[int]] = []
    cursor = 0
    for speech_row in speech_rows:
        key = _normalize_text(speech_row.transcript)[:_ALIGN_KEY_LENGTH]
        found = normalized_text.find(key, cursor) if len(key) >= _MIN_ALIGN_KEY_LENGTH else -1
        positions.append(found if found >= 0 else None)
        if found >= 0:
            cursor = found + 1
    return positions


def _get_name_words(name: str) -> set[str]:
    return set(_NON_LETTER_RE.sub("", name.lower()).split()) - _TITLE_WORDS


def _is_other_name_in_annotations(annotations: list[ChairAnnotation], name: str) -> bool:
    for annotation in annotations:
        named = _PARENTHESIS_RE.search(_normalize_text(annotation.text))
        if named is not None and not (_get_name_words(named.group(1)) & _get_name_words(name)):
            return True
    return False


def _get_bound_position(positions: list[Optional[int]], index: int, annotations: list[ChairAnnotation]) -> Optional[int]:
    if positions[index] is not None:
        return positions[index]
    low = next((positions[row_index] for row_index in range(index - 1, -1, -1) if positions[row_index] is not None), 0)
    high = next((positions[row_index] for row_index in range(index + 1, len(positions)) if positions[row_index] is not None), None)
    if any(low <= annotation.position < (high if high is not None else math.inf) for annotation in annotations):
        return None
    return low + 1


def get_chairman_names(markdown: str, speech_rows: list[SpeechRow]) -> dict[int, str]:
    normalized_text = _normalize_text(markdown)
    annotations = [ChairAnnotation(match.start(), match.group(1)) for match in _ANNOTATION_RE.finditer(normalized_text)]
    events = [(match.start(), match.group(1).lower()) for match in _CHAIR_EVENT_RE.finditer(normalized_text)]
    role_to_holder_names = _get_header_holders(markdown)
    is_header_present = _HEADER_RE.search(markdown) is not None
    is_deputy_named = _DEPUTY_MENTION_RE.search(normalized_text) is not None
    suspension_positions = [match.start() for match in _SUSPENSION_RE.finditer(normalized_text)]
    positions = _get_positions(normalized_text, speech_rows)
    speech_id_to_name: dict[int, str] = {}
    for index, speech_row in enumerate(speech_rows):
        if not speech_row.speaker or not CHAIRMAN_RE.match(speech_row.speaker):
            continue
        position = _get_bound_position(positions, index, annotations)
        if position is None:
            continue
        preceding = [annotation for annotation in annotations if annotation.position < position]
        after_roles = {role for event_position, role in events if event_position >= position - _EVENT_SLACK}
        before_roles = {role for event_position, role in events if event_position < position - _EVENT_SLACK}
        if preceding:
            annotation_position = preceding[-1].position
            text = _normalize_text(preceding[-1].text)
            named_deputy = _NAMED_DEPUTY_RE.search(text)
            if named_deputy is not None or not (_SPEAKER_ROLE_RE.match(text) or _DEPUTY_ROLE_RE.match(text)):
                if any(annotation_position < event_position < position for event_position, _ in events):
                    continue
                speech_id_to_name[speech_row.id] = named_deputy.group(1).strip() if named_deputy is not None else text
            elif _SPEAKER_ROLE_RE.match(text):
                holders = role_to_holder_names.get(ChairRole.SPEAKER, set())
                if after_roles == {ChairRole.SPEAKER} and not before_roles and len(holders) == 1:
                    speech_id_to_name[speech_row.id] = next(iter(holders))
                # NOTE: a Deputy Speaker named anywhere in the report, or a suspension, may hand over the chair without a note, so the header's Speaker takes the chair only without either.
                elif (
                    len(holders) == 1
                    and not is_deputy_named
                    and not any(annotation_position < event_position < position for event_position, _ in events)
                    and not any(annotation_position < suspension_position < position for suspension_position in suspension_positions)
                ):
                    speech_id_to_name[speech_row.id] = next(iter(holders))
                # NOTE: with no MPs Speaking header, the annotation goes to stage 8, which finds the Speaker in SPEAKER_TERMS.
                elif not is_header_present and not any(annotation_position < event_position < position for event_position, _ in events):
                    speech_id_to_name[speech_row.id] = text
            continue
        if len(after_roles) != 1:
            continue
        holders = role_to_holder_names.get(next(iter(after_roles)), set())
        if len(holders) != 1:
            continue
        name = next(iter(holders))
        if not _is_other_name_in_annotations(annotations, name):
            speech_id_to_name[speech_row.id] = name
    return speech_id_to_name


def get_deputy_speaker_names(markdown: str, speech_rows: list[SpeechRow]) -> DeputySpeakerNames:
    normalized_text = _normalize_text(markdown)
    annotations = [ChairAnnotation(match.start(), match.group(1)) for match in _ANNOTATION_RE.finditer(normalized_text)]
    position_to_deputy_match = {annotation.position: _NAMED_DEPUTY_RE.search(_normalize_text(annotation.text)) for annotation in annotations}
    position_to_deputy_name = {position: _TITLE_RE.sub("", match.group(1).strip()) for position, match in position_to_deputy_match.items() if match is not None}
    events = [match.start() for match in _CHAIR_EVENT_RE.finditer(normalized_text)]
    positions = _get_positions(normalized_text, speech_rows)
    speech_id_to_deputy_name: dict[int, str] = {}
    labelled: set[str] = set()
    for index, speech_row in enumerate(speech_rows):
        if not speech_row.speaker:
            continue
        named_deputy_match = _NAMED_DEPUTY_ROW_RE.match(speech_row.speaker.strip())
        if named_deputy_match is not None:
            labelled.add(_TITLE_RE.sub("", named_deputy_match.group(1).strip()))
        if not BARE_DEPUTY_RE.match(speech_row.speaker.strip()):
            continue
        position = _get_bound_position(positions, index, annotations)
        if position is None:
            continue
        preceding = [annotation.position for annotation in annotations if annotation.position < position]
        deputy_name = position_to_deputy_name.get(preceding[-1]) if preceding else None
        if deputy_name is not None and not any(preceding[-1] < event_position < position for event_position in events):
            speech_id_to_deputy_name[speech_row.id] = deputy_name
    mentioned = set(position_to_deputy_name.values()) | labelled
    header = _HEADER_RE.search(markdown)
    for entry in (header.group(1).split(MP_NAME_SEPARATOR) if header is not None else []):
        name = _TITLE_RE.sub("", _TRAILING_PARENTHETICAL_RE.sub("", entry.replace(ASTERISK, "").strip()))
        if name:
            mentioned.add(name)
    return DeputySpeakerNames(speech_id_to_deputy_name, labelled, mentioned)


def _get_chair_marks(text: str) -> list[ChairMark]:
    chair_marks = []
    for match in _ANNOTATION_RE.finditer(text):
        named_deputy_match = _NAMED_DEPUTY_RE.search(match.group(1))
        chair_marks.append(ChairMark(match.start(), match.end(), None if named_deputy_match is None else named_deputy_match.group(1).strip()))
    for match in _NAMED_DEPUTY_LABEL_RE.finditer(text):
        chair_marks.append(ChairMark(match.start(), match.end(), match.group(1).strip()))
    for pattern in (_CHAIR_EVENT_RE, _SPEAKER_LABEL_RE, _SUSPENSION_RE):
        chair_marks.extend(ChairMark(match.start(), match.end(), None) for match in pattern.finditer(text))
    return sorted(chair_marks, key=lambda chair_mark: chair_mark.position)


def build_sitting_text_from_markdown(markdown: str) -> SittingText:
    text = _normalize_text(markdown)
    return SittingText(text, [], _get_chair_marks(text))


def build_sitting_text_from_sections(sections: str) -> SittingText:
    parts = []
    section_spans = []
    length = 0
    for raw_section in json.loads(sections):
        section = HansardReportSection.model_validate(raw_section)
        title = "" if section.title is None else _normalize_text(section.title)
        body = "" if section.content is None else _normalize_text(get_cleaned_report_markdown(section.content, ReportVersion.SPRS3))
        part = f"{title} {body} "
        section_spans.append(SectionSpan(title.lower(), length, length + len(part)))
        parts.append(part)
        length += len(part)
    text = "".join(parts)
    return SittingText(text, section_spans, _get_chair_marks(text))


def _get_chair_deputy_name(sitting_text: SittingText, chair_mark_positions: list[int], position: int) -> Optional[str]:
    index = bisect.bisect_left(chair_mark_positions, position)
    if index == 0:
        return None
    last_chair_mark = sitting_text.chair_marks[index - 1]
    if last_chair_mark.deputy_name is None:
        return None
    member_label_re = re.compile(re.escape(last_chair_mark.deputy_name) + _MEMBER_LABEL_TAIL)
    if member_label_re.search(sitting_text.text, last_chair_mark.end, position) is not None:
        return None
    if index < len(sitting_text.chair_marks):
        next_deputy_name = sitting_text.chair_marks[index].deputy_name
        if next_deputy_name is not None and _get_name_words(next_deputy_name) & _get_name_words(last_chair_mark.deputy_name):
            return None
    return last_chair_mark.deputy_name


def _get_section_positions(sitting_text: SittingText, section_span: SectionSpan, speech_rows: list[SpeechRow]) -> list[Optional[int]]:
    section_text = sitting_text.text[section_span.start : section_span.end]
    return [None if position is None else position + section_span.start for position in _get_positions(section_text, speech_rows)]


# NOTE: two sections of a sitting can share a title, one per reading, so the report is aligned in the one that places most of its rows, and in none on a tie.
def _get_sitting_positions(sitting_text: SittingText, report_title: str, speech_rows: list[SpeechRow]) -> Optional[list[Optional[int]]]:
    title = _normalize_text(report_title).lower()
    section_spans = [section_span for section_span in sitting_text.section_spans if section_span.title == title]
    if not section_spans:
        return _get_positions(sitting_text.text, speech_rows)
    section_positions = [_get_section_positions(sitting_text, section_span, speech_rows) for section_span in section_spans]
    aligned_counts = [sum(position is not None for position in positions) for positions in section_positions]
    most_aligned = max(aligned_counts)
    if aligned_counts.count(most_aligned) > 1:
        return None
    return section_positions[aligned_counts.index(most_aligned)]


def get_sitting_deputy_speaker_names(sitting_text: SittingText, report_title: str, speech_rows: list[SpeechRow]) -> dict[int, str]:
    positions = _get_sitting_positions(sitting_text, report_title, speech_rows)
    if positions is None:
        return {}
    chair_mark_positions = [chair_mark.position for chair_mark in sitting_text.chair_marks]
    chair_mark_annotations = [ChairAnnotation(chair_mark.position, "") for chair_mark in sitting_text.chair_marks]
    speech_id_to_deputy_name = {}
    for index, speech_row in enumerate(speech_rows):
        if not speech_row.speaker or not BARE_DEPUTY_RE.match(speech_row.speaker.strip()):
            continue
        position = _get_bound_position(positions, index, chair_mark_annotations)
        if position is None:
            continue
        deputy_name = _get_chair_deputy_name(sitting_text, chair_mark_positions, position)
        if deputy_name is not None:
            speech_id_to_deputy_name[speech_row.id] = deputy_name
    return speech_id_to_deputy_name


def get_deputy_speaker_names_in_text(text: str) -> set[str]:
    names = {_TITLE_RE.sub("", match.group(1).strip()) for match in _NAMED_DEPUTY_RE.finditer(_normalize_text(text))}
    names |= _get_header_holders(text).get(ChairRole.DEPUTY_SPEAKER, set())
    return names


def get_carried_role_names(speech_rows: list[SpeechRow]) -> dict[int, str]:
    role_to_holder: dict[str, str] = {}
    speech_id_to_name: dict[int, str] = {}
    for speech_row in speech_rows:
        if not speech_row.speaker:
            continue
        speaker = speech_row.speaker.rstrip(LABEL_COLON).strip()
        for role in CARRIED_ROLES:
            holder = role_to_holder.get(role)
            if speaker == role and holder is not None:
                speech_id_to_name[speech_row.id] = holder
            elif speaker.startswith(role + _CARRIED_HOLDER_OPENER):
                role_to_holder[role] = speaker[len(role + _CARRIED_HOLDER_OPENER) :].rstrip(CLOSING_PARENTHESIS).strip()
    return speech_id_to_name


def _clean_speaker_label(speaker_label: str) -> str:
    speaker_label = speaker_label.replace(BYTE_ORDER_MARK, "").strip()
    speaker_label = _LABELS_MISSING_OPENING_BRACKET.get(speaker_label, speaker_label)
    speaker_label = _LEADING_LIST_NUMBER_RE.sub("", speaker_label)
    speaker_label = _LEADING_DOT_RE.sub("", speaker_label)
    speaker_label = _ASSOC_PROF_RE.sub("Assoc. Prof.", speaker_label)
    speaker_label = _RANK_QUALIFIER_RE.sub(" ", speaker_label)
    speaker_label = _TRAILING_MR_SPEAKER_RE.sub("", speaker_label)
    speaker_label = _LEADING_QUOTE_RE.sub("", speaker_label)
    speaker_label = _PRESIDING_BRACKET_RE.sub("", speaker_label)
    speaker_label = _TRAILING_DASH_RE.sub("", speaker_label)
    speaker_label = _TRAILING_NAME_DOT_RE.sub("", speaker_label)
    if _UPPERCASE_TITLE_RE.match(speaker_label) is not None and speaker_label.isupper():
        speaker_label = speaker_label.title()
    speaker_label = _WHITESPACE_RE.sub(" ", speaker_label).rstrip(_LABEL_TRAILING_CHARACTERS).strip()
    if speaker_label.count(OPENING_PARENTHESIS) > speaker_label.count(CLOSING_PARENTHESIS):
        cut = speaker_label.rfind(OPENING_PARENTHESIS)
        inner = speaker_label[cut + 1 :].strip()
        speaker_label = f"{speaker_label[:cut]}({inner})" if _TITLED_RE.match(inner) else speaker_label[:cut].strip()
    inverted = _INVERTED_NAME_RE.match(speaker_label)
    if inverted is not None:
        speaker_label = f"{inverted.group(2)} {inverted.group(1)}"
    doubled = _DOUBLED_LABEL_RE.match(speaker_label)
    return doubled.group(1) if doubled is not None else speaker_label


def _is_title_in_parentheses(match: re.Match) -> bool:
    inner = _TITLE_DOT_PREFIX_RE.sub(r"\1 ", match.group(1).strip())
    return strip_title(inner) != inner


def get_holders_on(terms: Sequence[tuple[date, date, str]], day: date) -> list[str]:
    return [name for first, last, name in terms if first <= day <= last]


def _get_holder_on(
    terms: Sequence[tuple[date, date, str]], sitting_date: Optional[datetime]
) -> Optional[str]:
    if sitting_date is None:
        return None
    holders = get_holders_on(terms, sitting_date.date())
    return holders[0] if len(holders) == 1 else None


@dataclass(frozen=True)
class ResolvedName:
    canonical_name: Optional[str]
    parliament_number: int


def _resolve_with_parliament_fallback(
    name: str,
    parliament_number: int,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> ResolvedName:
    canonical_name = resolve_canonical_name(name, parliament_number, lookups)
    if canonical_name is not None or parliament_number != 0:
        return ResolvedName(canonical_name, parliament_number)
    for fallback_parliament_number in COLONIAL_PARLIAMENT_FALLBACKS:
        candidate = resolve_canonical_name(name, fallback_parliament_number, lookups)
        if candidate and (candidate, fallback_parliament_number) in name_parliament_number_to_speaker_id:
            return ResolvedName(candidate, fallback_parliament_number)
    return ResolvedName(None, parliament_number)


def _get_presiding_officer_id(
    name: Optional[str],
    parliament_number: int,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> Optional[int]:
    if not name:
        return None
    resolved_name = _resolve_with_parliament_fallback(name, parliament_number, lookups, name_parliament_number_to_speaker_id)
    return name_parliament_number_to_speaker_id.get((resolved_name.canonical_name, resolved_name.parliament_number)) if resolved_name.canonical_name else None


def _resolve_presiding_officer(
    speaker_label: str,
    parliament_number: int,
    sitting_date: Optional[datetime],
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> Optional[int]:
    if speaker_label in _SPEAKER_LABELS:
        holder = _get_holder_on(SPEAKER_TERMS, sitting_date)
        is_woman_label = speaker_label == _WOMAN_SPEAKER_LABEL
        if is_woman_label != (holder in SPEAKER_WOMEN):
            return None
        return _get_presiding_officer_id(holder, parliament_number, lookups, name_parliament_number_to_speaker_id)
    if speaker_label.startswith(_DEPUTY_SPEAKER_LABELS):
        named_match = _PARENTHESIS_RE.search(speaker_label)
        terms = (
            [term for term in DEPUTY_SPEAKER_TERMS if term[2] in DEPUTY_SPEAKER_WOMEN]
            if speaker_label.startswith(_WOMAN_TITLE_PREFIX)
            else DEPUTY_SPEAKER_TERMS
        )
        name = (
            normalize_name(strip_title(named_match.group(1).strip()))
            if named_match is not None
            else _get_holder_on(terms, sitting_date)
        )
        return _get_presiding_officer_id(name, parliament_number, lookups, name_parliament_number_to_speaker_id)
    return None


def _resolve_attendance_speaker_id(
    speaker_name: str,
    parliament_number: int,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> Optional[int]:
    speaker_id = name_parliament_number_to_speaker_id.get((speaker_name, parliament_number))
    if speaker_id is not None:
        return speaker_id
    name = normalize_name(strip_title(speaker_name))
    resolved_name = _resolve_with_parliament_fallback(name, parliament_number, lookups, name_parliament_number_to_speaker_id)
    return name_parliament_number_to_speaker_id.get((resolved_name.canonical_name, resolved_name.parliament_number)) if resolved_name.canonical_name else None


def _get_role_key(speaker_label: str, parliament_number: int) -> Optional[tuple[str, int]]:
    if parliament_number != 0:
        return (speaker_label, parliament_number)
    for fallback_parliament_number in COLONIAL_PARLIAMENT_FALLBACKS:
        if (speaker_label, fallback_parliament_number) in ROLE_ONLY_SPEAKERS:
            return (speaker_label, fallback_parliament_number)
    return None


def resolve_speech_speaker_id(
    speaker: str,
    parliament_number: int,
    sitting_date: Optional[datetime],
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> Optional[int]:
    if speaker in NON_SPEAKERS or speaker.startswith(OPENING_PARENTHESIS) or speaker.startswith(EMPHASIS_MARK):
        return None

    speaker_label = _clean_speaker_label(speaker.rstrip(LABEL_COLON).strip())

    if speaker_label in _SPEAKER_LABELS or speaker_label.startswith(_DEPUTY_SPEAKER_LABELS):
        return _resolve_presiding_officer(
            speaker_label, parliament_number, sitting_date, lookups, name_parliament_number_to_speaker_id
        )

    dated_role_terms = DATED_ROLE_TERMS.get(speaker_label)
    if dated_role_terms is not None:
        holder = _get_holder_on(dated_role_terms, sitting_date)
        if holder is None:
            return None
        resolved_name = _resolve_with_parliament_fallback(holder, parliament_number, lookups, name_parliament_number_to_speaker_id)
        return name_parliament_number_to_speaker_id.get((resolved_name.canonical_name, resolved_name.parliament_number)) if resolved_name.canonical_name else None

    role_key = _get_role_key(speaker_label, parliament_number)
    if role_key is not None:
        role_name = ROLE_ONLY_SPEAKERS.get(role_key)
        if role_name is not None:
            _, role_key_parliament_number = role_key
            resolved_role_name = _resolve_with_parliament_fallback(role_name, role_key_parliament_number, lookups, name_parliament_number_to_speaker_id)
            return name_parliament_number_to_speaker_id.get((resolved_role_name.canonical_name, resolved_role_name.parliament_number)) if resolved_role_name.canonical_name else None

    parenthesised_matches = list(_PARENTHESIS_RE.finditer(speaker_label))
    if parenthesised_matches:
        title_match = next(
            (match for match in reversed(parenthesised_matches) if _is_title_in_parentheses(match)),
            None,
        )
        if title_match is not None:
            speaker_label = title_match.group(1).strip()
        else:
            speaker_label = speaker_label[: parenthesised_matches[0].start()].strip()
    speaker_label = _GLUED_TITLE_RE.sub(r"\1 \2", speaker_label)
    speaker_label = _TITLE_DOT_PREFIX_RE.sub(r"\1 ", speaker_label)
    name = normalize_name(strip_title(speaker_label))
    if not name:
        return None

    resolved_name = _resolve_with_parliament_fallback(name, parliament_number, lookups, name_parliament_number_to_speaker_id)
    return name_parliament_number_to_speaker_id.get((resolved_name.canonical_name, resolved_name.parliament_number)) if resolved_name.canonical_name else None


@dataclass(frozen=True)
class ResolvedSpeakerIds:
    id_to_speaker_id: dict[int, int]
    row_count: int


def resolve_attendance_rows(
    attendance_rows: Iterable[AttendanceSpeakerRow],
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> ResolvedSpeakerIds:
    key_to_speaker_id: dict[tuple[str, int], Optional[int]] = {}
    attendance_id_to_speaker_id: dict[int, int] = {}
    total = 0
    for attendance_row in attendance_rows:
        total += 1
        if not attendance_row.speaker_name:
            continue
        parliament_number = (
            attendance_row.parlement_no if attendance_row.parlement_no is not None else VOLUME_TO_PARLIAMENT.get(attendance_row.volume_no)
        )
        if parliament_number is None:
            continue
        key = (attendance_row.speaker_name, parliament_number)
        if key not in key_to_speaker_id:
            key_to_speaker_id[key] = _resolve_attendance_speaker_id(
                attendance_row.speaker_name, parliament_number, lookups, name_parliament_number_to_speaker_id
            )
        if key_to_speaker_id[key] is not None:
            attendance_id_to_speaker_id[attendance_row.id] = key_to_speaker_id[key]
    return ResolvedSpeakerIds(attendance_id_to_speaker_id, total)


def resolve_speech_rows(
    speech_rows: Iterable[SpeechSpeakerRow],
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> ResolvedSpeakerIds:
    key_to_speaker_id: dict[tuple[str, int, Optional[datetime]], Optional[int]] = {}
    speech_id_to_speaker_id: dict[int, int] = {}
    total = 0
    for speech_row in speech_rows:
        total += 1
        if not speech_row.speaker:
            continue
        date_key = speech_row.sitting_date if speech_row.speaker.startswith(DATE_DEPENDENT_ROLES) else None
        key = (speech_row.speaker, speech_row.parliament_number, date_key)
        if key not in key_to_speaker_id:
            key_to_speaker_id[key] = resolve_speech_speaker_id(
                speech_row.speaker, speech_row.parliament_number, speech_row.sitting_date, lookups, name_parliament_number_to_speaker_id
            )
        if key_to_speaker_id[key] is not None:
            speech_id_to_speaker_id[speech_row.id] = key_to_speaker_id[key]
    return ResolvedSpeakerIds(speech_id_to_speaker_id, total)


# NOTE: a bare head-of-state string is the holder only in the Address itself; the same strings in addenda and adjournment reports are parser errors and stay unlinked.
def get_head_of_state_names(title: str, sitting_date: datetime, speech_rows: list[SpeechRow]) -> dict[int, str]:
    if not title.upper().startswith(_ADDRESS_TITLES):
        return {}
    speech_id_to_name = {}
    for speech_row in speech_rows:
        if speech_row.speaker is None:
            continue
        head_of_state_terms = HEAD_OF_STATE_TERMS.get(speech_row.speaker)
        if head_of_state_terms is not None:
            holder = _get_holder_on(head_of_state_terms, sitting_date)
            if holder is not None:
                speech_id_to_name[speech_row.id] = holder
    return speech_id_to_name


def get_speaker_id_for_name(
    name: str,
    parliament_number: int,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> Optional[int]:
    resolved_name = _resolve_with_parliament_fallback(
        normalize_name(strip_title(name)), parliament_number, lookups, name_parliament_number_to_speaker_id
    )
    return name_parliament_number_to_speaker_id.get((resolved_name.canonical_name, resolved_name.parliament_number)) if resolved_name.canonical_name else None


def get_speaker_ids_for_names(
    names: Iterable[str],
    parliament_number: int,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> set[int]:
    found = (get_speaker_id_for_name(name, parliament_number, lookups, name_parliament_number_to_speaker_id) for name in names)
    return {speaker_id for speaker_id in found if speaker_id is not None}

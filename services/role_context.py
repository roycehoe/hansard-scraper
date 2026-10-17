# NOTE: the Chairman is not looked up by date, because the chair changes within a sitting.

import bisect
import json
import re
from dataclasses import dataclass
from typing import Optional

from crud.speech import SpeechRow
from enums import ReportVersion
from schemas.hansard_report_response import HansardReportSection
from utils.markdown_parser import get_cleaned_report_markdown

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
_NAMED_DEPUTY_RE = re.compile(r"Deputy\s*Speaker\s*\(([^)]+)\)", re.IGNORECASE)
_TITLE_RE = re.compile(r"^(?:Mr|Mdm|Dr|Sir|Mrs|Ms)\s+")
BARE_DEPUTY_RE = re.compile(r"^mr deputy speaker:?$", re.IGNORECASE)
_NAMED_DEPUTY_ROW_RE = re.compile(r"^(?:Mr|Mdm)\s*Deputy\s*Speaker\s*\(([^)]+)\)", re.IGNORECASE)
_NAMED_DEPUTY_LABEL_RE = re.compile(r"(?:Mr|Mdm)\s*Deputy\s*Speaker\s*\(([^)]+)\)\s*:", re.IGNORECASE)
_SPEAKER_LABEL_RE = re.compile(r"\b(?:Mr|Mdm|Madam)\s*Speaker\s*:", re.IGNORECASE)
_SUSPENSION_RE = re.compile(r"Sitting (?:was )?suspended|Sitting resumed|resumed at \d", re.IGNORECASE)
_MEMBER_LABEL_TAIL = r"\s*(?:\([^)]*\))?\s*:"
_ALIGN_KEY_LENGTH = 35
_MIN_ALIGN_KEY_LENGTH = 12
_EVENT_SLACK = 3
_TITLE_WORDS = frozenset({"mr", "mdm", "ms", "mrs", "dr", "sir"})
_CARRIED_HOLDER_OPENER = " ("

CARRIED_ROLES = ("The Chief Secretary",)


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
class SittingText:
    text: str
    title_to_offset: dict[str, int]
    chair_marks: list[ChairMark]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def _get_header_holders(markdown: str) -> dict[str, set[str]]:
    header = _HEADER_RE.search(markdown)
    if header is None:
        return {}
    role_to_holder_names: dict[str, set[str]] = {}
    for entry in header.group(1).split(";"):
        tag = _HEADER_TAG_RE.match(entry.replace("*", ""))
        if tag is not None:
            role_to_holder_names.setdefault(tag.group(2).lower(), set()).add(_TITLE_RE.sub("", tag.group(1).strip()))
    return role_to_holder_names


def _get_positions(normalised: str, speech_rows: list[SpeechRow]) -> list[Optional[int]]:
    positions: list[Optional[int]] = []
    cursor = 0
    for speech_row in speech_rows:
        key = _normalise(speech_row.transcript)[:_ALIGN_KEY_LENGTH]
        found = normalised.find(key, cursor) if len(key) >= _MIN_ALIGN_KEY_LENGTH else -1
        positions.append(found if found >= 0 else None)
        if found >= 0:
            cursor = found + 1
    return positions


def _get_name_words(name: str) -> set[str]:
    return set(re.sub(r"[^a-z ]", "", name.lower()).split()) - _TITLE_WORDS


def _is_other_name_in_annotations(annotations: list[tuple[int, str]], name: str) -> bool:
    for _, text in annotations:
        named = re.search(r"\(([^)]+)\)", _normalise(text))
        if named is not None and not (_get_name_words(named.group(1)) & _get_name_words(name)):
            return True
    return False


def _get_bound_position(positions: list[Optional[int]], index: int, annotations: list[tuple[int, str]]) -> Optional[int]:
    if positions[index] is not None:
        return positions[index]
    low = next((positions[row_index] for row_index in range(index - 1, -1, -1) if positions[row_index] is not None), 0)
    high = next((positions[row_index] for row_index in range(index + 1, len(positions)) if positions[row_index] is not None), None)
    if any(low <= annotation_position < (high if high is not None else float("inf")) for annotation_position, _ in annotations):
        return None
    return low + 1


def chairman_names(markdown: str, speech_rows: list[SpeechRow]) -> dict[int, str]:
    normalised = _normalise(markdown)
    annotations = [(match.start(), match.group(1)) for match in _ANNOTATION_RE.finditer(normalised)]
    events = [(match.start(), match.group(1).lower()) for match in _CHAIR_EVENT_RE.finditer(normalised)]
    role_to_holder_names = _get_header_holders(markdown)
    positions = _get_positions(normalised, speech_rows)
    speech_id_to_name: dict[int, str] = {}
    for index, speech_row in enumerate(speech_rows):
        if not speech_row.speaker or not CHAIRMAN_RE.match(speech_row.speaker):
            continue
        position = _get_bound_position(positions, index, annotations)
        if position is None:
            continue
        preceding = [annotation for annotation in annotations if annotation[0] < position]
        after_roles = {role for event_position, role in events if event_position >= position - _EVENT_SLACK}
        before_roles = {role for event_position, role in events if event_position < position - _EVENT_SLACK}
        if preceding:
            annotation_position, text = preceding[-1]
            text = _normalise(text)
            named_deputy = _NAMED_DEPUTY_RE.search(text)
            if named_deputy is not None or not (_SPEAKER_ROLE_RE.match(text) or _DEPUTY_ROLE_RE.match(text)):
                # NOTE: a chair-change line between the annotation and the row voids it.
                if any(annotation_position < event_position < position for event_position, _ in events):
                    continue
                speech_id_to_name[speech_row.id] = named_deputy.group(1).strip() if named_deputy is not None else text
            elif _SPEAKER_ROLE_RE.match(text):
                holders = role_to_holder_names.get("speaker", set())
                if after_roles == {"speaker"} and not before_roles and len(holders) == 1:
                    speech_id_to_name[speech_row.id] = next(iter(holders))
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


def deputy_speaker_names(markdown: str, speech_rows: list[SpeechRow]) -> DeputySpeakerNames:
    normalised = _normalise(markdown)
    annotations = [(match.start(), match.group(1)) for match in _ANNOTATION_RE.finditer(normalised)]
    position_to_deputy_match = {position: _NAMED_DEPUTY_RE.search(_normalise(text)) for position, text in annotations}
    position_to_deputy_name = {position: _TITLE_RE.sub("", match.group(1).strip()) for position, match in position_to_deputy_match.items() if match is not None}
    events = [match.start() for match in _CHAIR_EVENT_RE.finditer(normalised)]
    positions = _get_positions(normalised, speech_rows)
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
        preceding = [annotation_position for annotation_position, _ in annotations if annotation_position < position]
        if preceding and preceding[-1] in position_to_deputy_name and not any(preceding[-1] < event_position < position for event_position in events):
            speech_id_to_deputy_name[speech_row.id] = position_to_deputy_name[preceding[-1]]
    mentioned = set(position_to_deputy_name.values()) | labelled
    header = _HEADER_RE.search(markdown)
    for entry in (header.group(1).split(";") if header is not None else []):
        name = _TITLE_RE.sub("", re.sub(r"\s*\([^)]*\)\s*$", "", entry.replace("*", "").strip()))
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
    text = _normalise(markdown)
    return SittingText(text, {}, _get_chair_marks(text))


def build_sitting_text_from_sections(sections: str) -> SittingText:
    parts = []
    title_to_offset: dict[str, int] = {}
    length = 0
    for raw_section in json.loads(sections):
        section = HansardReportSection.model_validate(raw_section)
        title = "" if section.title is None else _normalise(section.title)
        body = "" if section.content is None else _normalise(get_cleaned_report_markdown(section.content, ReportVersion.SPRS3))
        title_to_offset.setdefault(title.lower(), length)
        part = f"{title} {body} "
        parts.append(part)
        length += len(part)
    text = "".join(parts)
    return SittingText(text, title_to_offset, _get_chair_marks(text))


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


def sitting_deputy_speaker_names(sitting_text: SittingText, report_title: str, speech_rows: list[SpeechRow]) -> dict[int, str]:
    offset = sitting_text.title_to_offset.get(_normalise(report_title).lower(), 0)
    positions = [None if position is None else position + offset for position in _get_positions(sitting_text.text[offset:], speech_rows)]
    chair_mark_positions = [chair_mark.position for chair_mark in sitting_text.chair_marks]
    chair_mark_annotations = [(chair_mark.position, "") for chair_mark in sitting_text.chair_marks]
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


def deputy_speaker_names_in_text(text: str) -> set[str]:
    names = {_TITLE_RE.sub("", match.group(1).strip()) for match in _NAMED_DEPUTY_RE.finditer(_normalise(text))}
    names |= _get_header_holders(text).get("deputy speaker", set())
    return names


def carried_role_names(speech_rows: list[SpeechRow]) -> dict[int, str]:
    role_to_holder: dict[str, str] = {}
    speech_id_to_name: dict[int, str] = {}
    for speech_row in speech_rows:
        if not speech_row.speaker:
            continue
        speaker = speech_row.speaker.rstrip(":").strip()
        for role in CARRIED_ROLES:
            if speaker == role and role in role_to_holder:
                speech_id_to_name[speech_row.id] = role_to_holder[role]
            elif speaker.startswith(role + _CARRIED_HOLDER_OPENER):
                role_to_holder[role] = speaker[len(role + _CARRIED_HOLDER_OPENER) :].rstrip(")").strip()
    return speech_id_to_name

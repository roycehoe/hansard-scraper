"""Attribute role-only speaker strings from the report itself.

"The Chairman" has no holder per date: whoever presides over a Committee of the whole
House is the Chairman, and the chair changes within a sitting (Standing Order 8(4)).
Hansard records the holder in three places that this module reads:

- the "[X in the Chair]" annotation printed at the start of a report and after each
  change of chair;
- the closing line "Thereupon Mr Speaker left the Chair of the Committee", which
  names the role that held the chair up to that point;
- the report header "MPs Speaking:| Name (Mr Speaker); ..." which names the holder
  of each presiding role that day.

A role named earlier in the same report with its holder ("The Chief Secretary (Mr
E. B. David)") also attributes later bare mentions of that role.
"""
import re
from typing import Optional

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
_ALIGN_KEY_LENGTH = 35
_MIN_ALIGN_KEY_LENGTH = 12
_EVENT_SLACK = 3

CARRIED_ROLES = ("The Chief Secretary",)

SpeechRow = tuple[int, int, Optional[str], str]  # (id, ordinal, speaker, transcript)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def _get_header_holders(markdown: str) -> dict[str, set[str]]:
    """Role ("speaker" or "deputy speaker") to the set of names tagged with it in the header."""
    header = _HEADER_RE.search(markdown)
    role_to_holder_names: dict[str, set[str]] = {}
    if not header:
        return role_to_holder_names
    for entry in header.group(1).split(";"):
        tag = _HEADER_TAG_RE.match(entry.replace("*", ""))
        if tag:
            role_to_holder_names.setdefault(tag.group(2).lower(), set()).add(_TITLE_RE.sub("", tag.group(1).strip()))
    return role_to_holder_names


def _get_positions(normalised: str, rows: list[SpeechRow]) -> list[Optional[int]]:
    """Position of each row in the normalised markdown, found by the opening of its transcript
    in document order; None when the opening is too short or not found."""
    positions: list[Optional[int]] = []
    cursor = 0
    for _, _, _, transcript in rows:
        key = _normalise(transcript)[:_ALIGN_KEY_LENGTH]
        found = normalised.find(key, cursor) if len(key) >= _MIN_ALIGN_KEY_LENGTH else -1
        positions.append(found if found >= 0 else None)
        if found >= 0:
            cursor = found + 1
    return positions


def _get_name_words(name: str) -> set[str]:
    return set(re.sub(r"[^a-z ]", "", name.lower()).split()) - {"mr", "mdm", "ms", "mrs", "dr", "sir"}


def _is_other_name_in_annotations(annotations: list[tuple[int, str]], name: str) -> bool:
    for _, text in annotations:
        named = re.search(r"\(([^)]+)\)", _normalise(text))
        if named and not (_get_name_words(named.group(1)) & _get_name_words(name)):
            return True
    return False


def _get_bound_position(positions: list[Optional[int]], index: int, annotations: list[tuple[int, str]]) -> Optional[int]:
    """Position of row `index`; an unaligned row is bounded by its aligned neighbours and is None
    when an annotation lies inside the bounds."""
    if positions[index] is not None:
        return positions[index]
    low = next((positions[row_index] for row_index in range(index - 1, -1, -1) if positions[row_index] is not None), 0)
    high = next((positions[row_index] for row_index in range(index + 1, len(positions)) if positions[row_index] is not None), None)
    if any(low <= annotation_position < (high if high is not None else float("inf")) for annotation_position, _ in annotations):
        return None
    return low + 1


def chairman_names(markdown: str, rows: list[SpeechRow]) -> dict[int, str]:
    """Speech id to the name of the person in the chair, for rows whose speaker is the Chairman
    and whose chair the report itself establishes. Rows the report leaves open are omitted."""
    normalised = _normalise(markdown)
    annotations = [(match.start(), match.group(1)) for match in _ANNOTATION_RE.finditer(normalised)]
    events = [(match.start(), match.group(1).lower()) for match in _CHAIR_EVENT_RE.finditer(normalised)]
    role_to_holder_names = _get_header_holders(markdown)
    positions = _get_positions(normalised, rows)
    speech_id_to_name: dict[int, str] = {}
    for index, (speech_id, _, speaker, _) in enumerate(rows):
        if not speaker or not CHAIRMAN_RE.match(speaker):
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
            if named_deputy or not (_SPEAKER_ROLE_RE.match(text) or _DEPUTY_ROLE_RE.match(text)):
                # The annotation names the person; a chair-change line between it and the row voids it.
                if any(annotation_position < event_position < position for event_position, _ in events):
                    continue
                speech_id_to_name[speech_id] = named_deputy.group(1).strip() if named_deputy else text
            elif _SPEAKER_ROLE_RE.match(text):
                # "[Mr Speaker in the Chair]": corroborated by a closing line naming the Speaker and a
                # header that names exactly one Speaker.
                holders = role_to_holder_names.get("speaker", set())
                if after_roles == {"speaker"} and not before_roles and len(holders) == 1:
                    speech_id_to_name[speech_id] = next(iter(holders))
            continue
        # No preceding annotation: the closing line gives the role, the header gives its one holder.
        if len(after_roles) != 1:
            continue
        holders = role_to_holder_names.get(next(iter(after_roles)), set())
        if len(holders) != 1:
            continue
        name = next(iter(holders))
        if not _is_other_name_in_annotations(annotations, name):
            speech_id_to_name[speech_id] = name
    return speech_id_to_name


def deputy_speaker_names(markdown: str, rows: list[SpeechRow]) -> tuple[dict[int, str], set[str], set[str]]:
    """Evidence for bare "Mr Deputy Speaker" rows, names as printed minus the title:
    (speech id to the name in the annotation last before the row, when that annotation is
    "[Mr Deputy Speaker (Name) in the Chair]" and no chair change follows it before the row;
    every name in a "Mr Deputy Speaker (Name)" speaker row; every name the report shows
    taking part, in the chair annotations, speaker rows or header)."""
    normalised = _normalise(markdown)
    annotations = [(match.start(), match.group(1)) for match in _ANNOTATION_RE.finditer(normalised)]
    position_to_deputy_match = {position: _NAMED_DEPUTY_RE.search(_normalise(text)) for position, text in annotations}
    position_to_deputy_name = {position: _TITLE_RE.sub("", match.group(1).strip()) for position, match in position_to_deputy_match.items() if match}
    events = [match.start() for match in _CHAIR_EVENT_RE.finditer(normalised)]
    positions = _get_positions(normalised, rows)
    speech_id_to_deputy_name: dict[int, str] = {}
    labelled: set[str] = set()
    for index, (speech_id, _, speaker, _) in enumerate(rows):
        if not speaker:
            continue
        row_name = _NAMED_DEPUTY_ROW_RE.match(speaker.strip())
        if row_name:
            labelled.add(_TITLE_RE.sub("", row_name.group(1).strip()))
        if not BARE_DEPUTY_RE.match(speaker.strip()):
            continue
        position = _get_bound_position(positions, index, annotations)
        if position is None:
            continue
        preceding = [annotation_position for annotation_position, _ in annotations if annotation_position < position]
        if preceding and preceding[-1] in position_to_deputy_name and not any(preceding[-1] < event_position < position for event_position in events):
            speech_id_to_deputy_name[speech_id] = position_to_deputy_name[preceding[-1]]
    mentioned = set(position_to_deputy_name.values()) | labelled
    header = _HEADER_RE.search(markdown)
    for entry in (header.group(1).split(";") if header else []):
        name = _TITLE_RE.sub("", re.sub(r"\s*\([^)]*\)\s*$", "", entry.replace("*", "").strip()))
        if name:
            mentioned.add(name)
    return speech_id_to_deputy_name, labelled, mentioned


def deputy_speaker_names_in_text(text: str) -> set[str]:
    """Names a day-level text associates with the deputy role: "Deputy Speaker (Name)" in brackets,
    headings and speaker labels, and the header's deputy speaker tag."""
    names = {_TITLE_RE.sub("", match.group(1).strip()) for match in _NAMED_DEPUTY_RE.finditer(_normalise(text))}
    names |= _get_header_holders(text).get("deputy speaker", set())
    return names


def carried_role_names(rows: list[SpeechRow]) -> dict[int, str]:
    """Speech id to name for bare role strings whose holder an earlier row in the same report
    names, as in "The Chief Secretary (Mr W. A. C. Goode)" followed by "The Chief Secretary"."""
    role_to_holder: dict[str, str] = {}
    speech_id_to_name: dict[int, str] = {}
    for speech_id, _, speaker, _ in rows:
        if not speaker:
            continue
        speaker = speaker.rstrip(":").strip()
        for role in CARRIED_ROLES:
            if speaker == role and role in role_to_holder:
                speech_id_to_name[speech_id] = role_to_holder[role]
            elif speaker.startswith(role + " ("):
                role_to_holder[role] = speaker[len(role) + 2 :].rstrip(")").strip()
    return speech_id_to_name

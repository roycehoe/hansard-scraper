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
_ALIGN_KEY_LENGTH = 35
_MIN_ALIGN_KEY_LENGTH = 12
_EVENT_SLACK = 3

CARRIED_ROLES = ("The Chief Secretary",)

SpeechRow = tuple[int, int, Optional[str], str]  # (id, ordinal, speaker, transcript)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def _header_holders(markdown: str) -> dict[str, set[str]]:
    """Role ("speaker" or "deputy speaker") to the set of names tagged with it in the header."""
    header = _HEADER_RE.search(markdown)
    holders: dict[str, set[str]] = {}
    if not header:
        return holders
    for entry in header.group(1).split(";"):
        tag = _HEADER_TAG_RE.match(entry.replace("*", ""))
        if tag:
            holders.setdefault(tag.group(2).lower(), set()).add(_TITLE_RE.sub("", tag.group(1).strip()))
    return holders


def _positions(normalised: str, rows: list[SpeechRow]) -> list[Optional[int]]:
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


def _name_words(name: str) -> set[str]:
    return set(re.sub(r"[^a-z ]", "", name.lower()).split()) - {"mr", "mdm", "ms", "mrs", "dr", "sir"}


def _annotation_names_other(annotations: list[tuple[int, str]], name: str) -> bool:
    for _, text in annotations:
        named = re.search(r"\(([^)]+)\)", _normalise(text))
        if named and not (_name_words(named.group(1)) & _name_words(name)):
            return True
    return False


def chairman_names(markdown: str, rows: list[SpeechRow]) -> dict[int, str]:
    """Speech id to the name of the person in the chair, for rows whose speaker is the Chairman
    and whose chair the report itself establishes. Rows the report leaves open are omitted."""
    normalised = _normalise(markdown)
    annotations = [(m.start(), m.group(1)) for m in _ANNOTATION_RE.finditer(normalised)]
    events = [(m.start(), m.group(1).lower()) for m in _CHAIR_EVENT_RE.finditer(normalised)]
    header = _header_holders(markdown)
    positions = _positions(normalised, rows)
    names: dict[int, str] = {}
    for index, (speech_id, _, speaker, _) in enumerate(rows):
        if not speaker or not CHAIRMAN_RE.match(speaker):
            continue
        position = positions[index]
        if position is None:
            # Bound the row by its aligned neighbours; an annotation inside the bounds is ambiguous.
            low = next((positions[k] for k in range(index - 1, -1, -1) if positions[k] is not None), 0)
            high = next((positions[k] for k in range(index + 1, len(rows)) if positions[k] is not None), None)
            if any(low <= a_pos < (high if high is not None else float("inf")) for a_pos, _ in annotations):
                continue
            position = low + 1
        preceding = [a for a in annotations if a[0] < position]
        after_roles = {role for e_pos, role in events if e_pos >= position - _EVENT_SLACK}
        before_roles = {role for e_pos, role in events if e_pos < position - _EVENT_SLACK}
        if preceding:
            a_pos, text = preceding[-1]
            text = _normalise(text)
            named_deputy = _NAMED_DEPUTY_RE.search(text)
            if named_deputy or not (_SPEAKER_ROLE_RE.match(text) or _DEPUTY_ROLE_RE.match(text)):
                # The annotation names the person; a chair-change line between it and the row voids it.
                if any(a_pos < e_pos < position for e_pos, _ in events):
                    continue
                names[speech_id] = named_deputy.group(1).strip() if named_deputy else text
            elif _SPEAKER_ROLE_RE.match(text):
                # "[Mr Speaker in the Chair]": corroborated by a closing line naming the Speaker and a
                # header that names exactly one Speaker.
                holders = header.get("speaker", set())
                if after_roles == {"speaker"} and not before_roles and len(holders) == 1:
                    names[speech_id] = next(iter(holders))
            continue
        # No preceding annotation: the closing line gives the role, the header gives its one holder.
        if len(after_roles) != 1:
            continue
        holders = header.get(next(iter(after_roles)), set())
        if len(holders) != 1:
            continue
        name = next(iter(holders))
        if not _annotation_names_other(annotations, name):
            names[speech_id] = name
    return names


def carried_role_names(rows: list[SpeechRow]) -> dict[int, str]:
    """Speech id to name for bare role strings whose holder an earlier row in the same report
    names, as in "The Chief Secretary (Mr W. A. C. Goode)" followed by "The Chief Secretary"."""
    holder_by_role: dict[str, str] = {}
    names: dict[int, str] = {}
    for speech_id, _, speaker, _ in rows:
        if not speaker:
            continue
        speaker = speaker.rstrip(":").strip()
        for role in CARRIED_ROLES:
            if speaker == role and role in holder_by_role:
                names[speech_id] = holder_by_role[role]
            elif speaker.startswith(role + " ("):
                holder_by_role[role] = speaker[len(role) + 2 :].rstrip(")").strip()
    return names

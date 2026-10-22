import json
import re
from dataclasses import dataclass
from typing import Optional

from crud.attendance import AttendanceLocationRow
from database.attendance import Attendance
from database.sitting import Sitting
from database.speaker import Speaker
from exceptions import HansardWriteCheckError
from schemas.constituency_names import ConstituencyNames
from schemas.hansard_report_response import HansardReportAttendanceEntry
from utils.names import (
    TITLE_PREFIXES,
    invert_to_natural,
    normalize_name,
    period_normalize,
    strip_bin,
    strip_title,
)
from utils.parliament_numbers import infer_parliament
from utils.sitting_dates import parse_sitting_date
from utils.speaker_resolution import (
    SpeakerLookups,
    normalize_for_lookup,
    resolve_canonical_name,
)
from utils.speaker_terms import SPEAKER_TERMS

_HONORIFIC_SUFFIX_RE = re.compile(r"(?:,\s*[A-Z][A-Z.]*(?:\s+[A-Z][A-Z.]*)*)+$")

_ISLAMIC_SUFFIX_RE = re.compile(r"\s+[Aa]l-[Hh]aj[jh]?\s*$")

_OFFICIAL_ROLE_SUFFIX_RE = re.compile(
    r",\s*(?:Acting\s+)?(?:Financial|Chief|Colonial)\s+Secretary"
    r"|,\s*Attorney[-\s]General"
    r"|,\s*(?:Acting\s+)?Governor\b",
    re.I,
)

_MIN_SURNAME_LOOKUP_LENGTH = 2
_MIN_PREFIX_WORD_COUNT = 2
_MIN_MULTIWORD_SURNAME_LENGTH = 2
_MIN_REARRANGEABLE_WORD_COUNT = 3
_MIN_WORDSET_SUBSET_WORDS = 3

_LEAVE_NOTE_PREFIX = "For information on permission given to Members for leave of absence"

_SECTION_END_RE = re.compile(r"#|\||\*\*|\*[^\s*]|\d{1,2}(?:st|nd|rd|th) [A-Za-z]+,? \d{4}$|(?:Mr|Mdm) Speaker, preceded by")
_MARKUP_RE = re.compile(r"[*|#_\[\]]")
_SPEAKER_OFFICE_NAME = "speaker"

_TITLE_ALTERNATION = "|".join(re.escape(prefix.strip()) for prefix in TITLE_PREFIXES if prefix[0].isalpha())
_ENTRY_LINE_RE = re.compile(rf"^(?:{_TITLE_ALTERNATION})\s+[A-Z][^()]{{0,80}}\(")
_NEXT_ENTRY_START_RE = re.compile(rf"(?<=[\s.,;)\d])(?:{_TITLE_ALTERNATION})\s+[A-Z][^()]{{0,80}}\(")
_SECTION_HEADER_RE = re.compile(r"^(?:\*{2}|#+)?\s*(?:PRESENT|ABSENT)\s*:(?:\*{2})?\s*$", re.IGNORECASE)
_MASTHEAD_LINE = "## PARLIAMENTARY DEBATES"
_SPEAKER_ENTRY_MARKER = "SPEAKER"
_MAX_MASTHEAD_LINES = 20

# NOTE: the source lost the start of this entry; the line is the sitting of 10 June 1963.
_TRUNCATED_LINE_TO_ENTRY_LINE: dict[str, str] = {
    "Tunah), Parliamentary Secretary to the Prime Minister.": "Inche Yaacob Bin Mohamed (Bukit Timah), Parliamentary Secretary to the Prime Minister.",
}








def _build_direct_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    key_to_count: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        key = (period_normalize(speaker.name), speaker.parliament_number)
        key_to_count[key] = key_to_count.get(key, 0) + 1
        entries.append((key, speaker.name))
    return {key: canonical_name for key, canonical_name in entries if key_to_count[key] == 1}


def _build_bin_free_lookup(
    speakers: list[Speaker],
    direct: dict[tuple[str, int], str],
) -> dict[tuple[str, int], str]:
    key_to_count: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        key = (period_normalize(strip_bin(speaker.name)), speaker.parliament_number)
        key_to_count[key] = key_to_count.get(key, 0) + 1
        entries.append((key, speaker.name))
    return {key: canonical_name for key, canonical_name in entries if key_to_count[key] == 1 and key not in direct}


def _build_inverted_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    inverted: dict[tuple[str, int], str] = {}
    surname_key_to_count: dict[tuple[str, int], int] = {}
    surname_only_entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        parliament_number = speaker.parliament_number
        if ", " in speaker.name:
            natural_stripped = invert_to_natural(speaker.name)
            key = (normalize_for_lookup(natural_stripped), parliament_number)
            inverted[key] = speaker.name
            surname = speaker.name.split(", ")[0]
            surname_words = surname.split()
            if len(surname_words) >= _MIN_MULTIWORD_SURNAME_LENGTH:
                surname_key = (normalize_for_lookup(surname), parliament_number)
                surname_key_to_count[surname_key] = surname_key_to_count.get(surname_key, 0) + 1
                surname_only_entries.append((surname_key, speaker.name))
        else:
            words = speaker.name.split()
            if len(words) >= _MIN_REARRANGEABLE_WORD_COUNT:
                rearranged = f"{words[-1]} {' '.join(words[1:-1])} {words[0]}"
                if rearranged != speaker.name:
                    rearranged_stripped = strip_title(rearranged).strip()
                    rearranged_key = (normalize_for_lookup(rearranged_stripped), parliament_number)
                    if rearranged_key not in inverted:
                        inverted[rearranged_key] = speaker.name
    for surname_key, canonical_name in surname_only_entries:
        if surname_key_to_count.get(surname_key, 0) == 1 and surname_key not in inverted:
            inverted[surname_key] = canonical_name
    return inverted


def _build_wordset_lookup(speakers: list[Speaker]) -> dict[tuple[frozenset, int, int], str]:
    triples: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = invert_to_natural(speaker.name)
        if natural:
            triples.append((natural, speaker.name, speaker.parliament_number))
        triples.append((speaker.name, speaker.name, speaker.parliament_number))
    key_to_count: dict[tuple[frozenset, int, int], int] = {}
    entries: list[tuple[tuple[frozenset, int, int], str]] = []
    for display, canonical_name, parliament_number in triples:
        words = period_normalize(display).split()
        key = (frozenset(words), len(words), parliament_number)
        key_to_count[key] = key_to_count.get(key, 0) + 1
        entries.append((key, canonical_name))
    wordset: dict[tuple[frozenset, int, int], str] = {}
    for key, canonical_name in entries:
        if key_to_count[key] == 1 and key not in wordset:
            wordset[key] = canonical_name
    return wordset


def _build_wordset_subset_lookup(speakers: list[Speaker]) -> dict[tuple[frozenset, int], str]:
    triples: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = invert_to_natural(speaker.name)
        if natural:
            triples.append((natural, speaker.name, speaker.parliament_number))
        triples.append((speaker.name, speaker.name, speaker.parliament_number))
    key_to_count: dict[tuple[frozenset, int], int] = {}
    entries: list[tuple[tuple[frozenset, int], str]] = []
    for display, canonical_name, parliament_number in triples:
        words = period_normalize(strip_title(display)).split()
        if len(words) < _MIN_WORDSET_SUBSET_WORDS:
            continue
        words = [word for word in words if len(word) > 1]
        key = (frozenset(words), parliament_number)
        key_to_count[key] = key_to_count.get(key, 0) + 1
        entries.append((key, canonical_name))
    wordset_subset: dict[tuple[frozenset, int], str] = {}
    for key, canonical_name in entries:
        if key_to_count[key] == 1 and key not in wordset_subset:
            wordset_subset[key] = canonical_name
    return wordset_subset


def _build_prefix_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    forms: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = invert_to_natural(speaker.name)
        if natural:
            forms.append((natural, speaker.name, speaker.parliament_number))
        forms.append((speaker.name, speaker.name, speaker.parliament_number))
    prefix_key_to_count: dict[tuple[str, int], int] = {}
    prefix_entries: list[tuple[tuple[str, int], str]] = []
    for display, canonical_name, parliament_number in forms:
        words = period_normalize(display).split()
        for prefix_length in range(_MIN_PREFIX_WORD_COUNT, len(words)):
            joined_prefix = " ".join(words[:prefix_length])
            prefix_key = (joined_prefix, parliament_number)
            prefix_key_to_count[prefix_key] = prefix_key_to_count.get(prefix_key, 0) + 1
            prefix_entries.append((prefix_key, canonical_name))
    prefix: dict[tuple[str, int], str] = {}
    for prefix_key, canonical_name in prefix_entries:
        if prefix_key_to_count[prefix_key] == 1 and prefix_key not in prefix:
            prefix[prefix_key] = canonical_name
    return prefix


def _build_surname_fallback_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    surname_key_to_count: dict[tuple[str, int], int] = {}
    surname_entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        natural = invert_to_natural(speaker.name) or speaker.name
        words = period_normalize(natural).split()
        if not words:
            continue
        last_word = words[-1]
        if len(last_word) < _MIN_SURNAME_LOOKUP_LENGTH:
            continue
        surname_key = (last_word, speaker.parliament_number)
        surname_key_to_count[surname_key] = surname_key_to_count.get(surname_key, 0) + 1
        surname_entries.append((surname_key, speaker.name))
    return {key: canonical_name for key, canonical_name in surname_entries if surname_key_to_count[key] == 1}


def build_speaker_lookups(speakers: list[Speaker]) -> SpeakerLookups:
    direct = _build_direct_lookup(speakers)
    return SpeakerLookups(
        direct=direct,
        bin_free=_build_bin_free_lookup(speakers, direct),
        inverted=_build_inverted_lookup(speakers),
        wordset=_build_wordset_lookup(speakers),
        wordset_subset=_build_wordset_subset_lookup(speakers),
        prefix=_build_prefix_lookup(speakers),
        surname_fallback=_build_surname_fallback_lookup(speakers),
    )


@dataclass(frozen=True)
class ParsedAttendee:
    name: str
    constituency: Optional[str]


def _get_closing_parenthesis_index(text: str, open_index: int) -> Optional[int]:
    depth = 0
    for char_index in range(open_index, len(text)):
        if text[char_index] == "(":
            depth += 1
        elif text[char_index] == ")":
            depth -= 1
            if depth == 0:
                return char_index
    return None


def _strip_name_decorations(name_part: str) -> str:
    # NOTE: the role suffix goes first, so a mixed-case role title never blocks the all-caps honorific strip.
    name = strip_title(name_part.strip())
    name = _OFFICIAL_ROLE_SUFFIX_RE.sub("", name).rstrip(", ").strip()
    name = _HONORIFIC_SUFFIX_RE.sub("", name).rstrip(", ").strip()
    return _ISLAMIC_SUFFIX_RE.sub("", name).strip()


def _parse_name_and_location(text: str) -> ParsedAttendee:
    text = text.strip().rstrip(". ")

    # NOTE: the first parenthetical is the constituency, so a later portfolio parenthetical never replaces it.
    first_open = text.find("(")
    if first_open == -1:
        return ParsedAttendee(_strip_name_decorations(text), None)
    close_index = _get_closing_parenthesis_index(text, first_open)
    if close_index is None:
        return ParsedAttendee(_strip_name_decorations(text[:first_open].rstrip(", )")), None)
    constituency = text[first_open + 1 : close_index].strip()
    return ParsedAttendee(_strip_name_decorations(text[:first_open].rstrip(", ")), constituency)


def parse_speaker_line(line: str) -> ParsedAttendee:
    line = line.rstrip(". ")
    match = re.search(r"\((.+)\)\s*$", line)
    if match is None:
        return ParsedAttendee("SPEAKER", None)
    inner = match.group(1).strip()
    name_before_constituency = line[: match.start()].partition("SPEAKER")[2].strip()
    if name_before_constituency:
        return ParsedAttendee(_strip_name_decorations(name_before_constituency), inner)
    inner_stripped = strip_title(inner)
    return _parse_name_and_location(inner_stripped)


def _get_presiding_officer_name(sitting_date: str) -> Optional[str]:
    day = parse_sitting_date(sitting_date).date()
    names = [name for first, last, name in SPEAKER_TERMS if first <= day <= last]
    return names[0] if len(names) == 1 else None


def _parse_entry_line(line: str, sitting_date: str) -> Optional[ParsedAttendee]:
    line = line.strip()
    line = _TRUNCATED_LINE_TO_ENTRY_LINE.get(line, line)
    if not line:
        return None
    if line.startswith("* "):
        line = line[2:].strip()
    if not line:
        return None
    if line.startswith("**"):
        line = line[2:].strip()
    line = re.sub(r"^(?:Absent|Present):\s*", "", line, flags=re.IGNORECASE)
    if not line:
        return None
    line = re.sub(r"^\d+(?=[A-Z])", "", line)

    # NOTE: a name entry carries a title or a bracketed constituency; office fragments and prose have neither.
    if strip_title(line) == line and "(" not in line:
        return None

    parsed = parse_speaker_line(line) if "SPEAKER" in line else _parse_name_and_location(strip_title(line))
    if _MARKUP_RE.search(parsed.name):
        return None
    if parsed.name.lower() != _SPEAKER_OFFICE_NAME:
        return parsed

    # NOTE: a bare "Speaker" entry names the office; the dated table of Speakers names the person.
    presiding_officer_name = _get_presiding_officer_name(sitting_date)
    if presiding_officer_name is None:
        return parsed
    return ParsedAttendee(presiding_officer_name, None)


def _get_masthead_end_index(lines: list[str], masthead_index: int) -> Optional[int]:
    for line_index in range(masthead_index + 1, min(masthead_index + _MAX_MASTHEAD_LINES, len(lines))):
        stripped = lines[line_index].strip()
        if _SECTION_HEADER_RE.match(stripped):
            return None
        if _ENTRY_LINE_RE.match(stripped):
            return line_index
    return None


def _drop_masthead_blocks(lines: list[str]) -> list[str]:
    kept_lines = []
    resume_index = 0
    for line_index, line in enumerate(lines):
        if line_index < resume_index:
            continue
        if line.strip() == _MASTHEAD_LINE:
            masthead_end_index = _get_masthead_end_index(lines, line_index)
            if masthead_end_index is not None:
                resume_index = masthead_end_index
                continue
        kept_lines.append(line)
    return kept_lines


def _split_entry_line(line: str) -> list[str]:
    if _SPEAKER_ENTRY_MARKER in line:
        return [line]
    first_close_index = line.find(")")
    if first_close_index == -1:
        return [line]
    bounds = [0, *(match.start() for match in _NEXT_ENTRY_START_RE.finditer(line, first_close_index)), len(line)]
    return [line[start:end] for start, end in zip(bounds, bounds[1:])]


def extract_section_lines(content: str, section: str) -> list[str]:
    # NOTE: a page masthead reprinted inside a list is not its end when a member entry follows it.
    lines = _drop_masthead_blocks(content.split("\n"))
    is_in_section = False
    other_section = "ABSENT" if section == "PRESENT" else "PRESENT"
    entry_lines = []

    for line in lines:
        stripped = line.strip()

        if not is_in_section:
            if re.match(rf"^(?:\*{{2}}|#+)?\s*{section}\s*:(?:\*{{2}})?\s*$", stripped, re.IGNORECASE):
                is_in_section = True
            continue

        if re.match(rf"^(?:\*{{2}}|#+)?\s*{other_section}\s*:(?:\*{{2}})?\s*$", stripped, re.IGNORECASE):
            break
        if _SECTION_END_RE.match(stripped) or stripped == "* * *":
            break
        if re.match(r"^\d+\\\.?\s", stripped):
            break

        if stripped:
            entry_lines.append(line)
            # NOTE: a heading glued to the end of an entry line starts the text that follows the list.
            if "**" in stripped:
                break

    return entry_lines






@dataclass(frozen=True)
class ConstituencyLookups:
    printed_parliament_to_constituency: dict[tuple[str, Optional[int]], str]
    printed_to_constituency: dict[str, str]
    sitting_speaker_printed_to_constituency: dict[tuple[Optional[str], Optional[str], str], str]


@dataclass(frozen=True)
class AttendanceNameChange:
    id: int
    sitting_id: int
    speaker_name_before: Optional[str]
    speaker_name_after: Optional[str]
    is_present: Optional[bool]
    location_name: Optional[str]
    speaker_id: Optional[int]


@dataclass(frozen=True)
class LocationChange:
    id: int
    speaker_name: Optional[str]
    sitting_date: Optional[str]
    location_name_before: str
    location_name_after: str


def build_constituency_lookups(constituency_names: ConstituencyNames) -> ConstituencyLookups:
    return ConstituencyLookups(
        printed_parliament_to_constituency={
            (name.printed, name.parliament_number): name.constituency
            for name in constituency_names.names
            if name.parliament_number is not None
        },
        printed_to_constituency={name.printed: name.constituency for name in constituency_names.names if name.parliament_number is None},
        sitting_speaker_printed_to_constituency={
            (row.sitting_date, row.speaker_name, row.printed): row.constituency for row in constituency_names.rows
        },
    )


def get_constituency_name(
    printed: Optional[str],
    parliament_number: Optional[int],
    sitting_date: Optional[str],
    speaker_name: Optional[str],
    lookups: ConstituencyLookups,
) -> Optional[str]:
    if printed is None:
        return None
    row_constituency = lookups.sitting_speaker_printed_to_constituency.get((sitting_date, speaker_name, printed))
    if row_constituency is not None:
        return row_constituency
    parliament_constituency = lookups.printed_parliament_to_constituency.get((printed, parliament_number))
    if parliament_constituency is not None:
        return parliament_constituency
    return lookups.printed_to_constituency.get(printed, printed)


def get_location_changes(rows: list[AttendanceLocationRow], lookups: ConstituencyLookups) -> list[LocationChange]:
    location_changes = []
    for row in rows:
        location_name_after = get_constituency_name(
            row.location_name, infer_parliament(row.parlement_no, row.volume_no), row.sitting_date, row.speaker_name, lookups
        )
        if location_name_after == row.location_name:
            continue
        location_changes.append(LocationChange(row.id, row.speaker_name, row.sitting_date, row.location_name, location_name_after))
    return location_changes


def _drop_repeated_attendees(records: list[Attendance]) -> list[Attendance]:
    speaker_name_to_record: dict[Optional[str], Attendance] = {}
    for record in records:
        kept_record = speaker_name_to_record.get(record.speaker_name)
        if kept_record is None or (record.is_present and not kept_record.is_present):
            speaker_name_to_record[record.speaker_name] = record
    return list(speaker_name_to_record.values())


def build_sitting_attendances_from_markdown(sitting: Sitting, lookups: SpeakerLookups, constituency_lookups: ConstituencyLookups) -> list[Attendance]:
    if not sitting.markdown_content:
        return []

    parliament_number = infer_parliament(sitting.parlement_no, sitting.volume_no)
    content = sitting.markdown_content
    records = []

    for section, is_present in [("PRESENT", True), ("ABSENT", False)]:
        for line in extract_section_lines(content, section):
            for entry_line in _split_entry_line(line):
                parsed = _parse_entry_line(entry_line, sitting.sitting_date)
                if parsed is None:
                    continue
                if not parsed.name:
                    continue
                name = normalize_name(parsed.name)
                canonical_name = None if parliament_number is None else resolve_canonical_name(name, parliament_number, lookups)
                speaker_name = canonical_name or name
                records.append(Attendance(
                    sitting_id=sitting.id,
                    speaker_name=speaker_name,
                    is_present=is_present,
                    location_name=get_constituency_name(parsed.constituency, parliament_number, sitting.sitting_date, speaker_name, constituency_lookups),
                ))

    return _drop_repeated_attendees(records)


def build_sitting_attendances_from_list(sitting: Sitting, lookups: SpeakerLookups, constituency_lookups: ConstituencyLookups) -> list[Attendance]:
    if sitting.attendance_list is None:
        return []

    parliament_number = infer_parliament(sitting.parlement_no, sitting.volume_no)
    records = []

    for raw_entry in json.loads(sitting.attendance_list):
        entry = HansardReportAttendanceEntry.model_validate(raw_entry)
        if entry.mp_name is None:
            continue
        if entry.mp_name.startswith(_LEAVE_NOTE_PREFIX):
            continue
        parsed = _parse_entry_line(entry.mp_name, sitting.sitting_date)
        if parsed is None:
            continue
        if not parsed.name:
            continue
        name = normalize_name(parsed.name)
        canonical_name = None if parliament_number is None else resolve_canonical_name(name, parliament_number, lookups)
        speaker_name = canonical_name or name
        records.append(Attendance(
            sitting_id=sitting.id,
            speaker_name=speaker_name,
            is_present=entry.attendance,
            location_name=get_constituency_name(parsed.constituency, parliament_number, sitting.sitting_date, speaker_name, constituency_lookups),
        ))

    return _drop_repeated_attendees(records)


def build_sitting_attendances(sitting: Sitting, lookups: SpeakerLookups, constituency_lookups: ConstituencyLookups) -> list[Attendance]:
    if sitting.markdown_content is not None:
        return build_sitting_attendances_from_markdown(sitting, lookups, constituency_lookups)
    return build_sitting_attendances_from_list(sitting, lookups, constituency_lookups)


def get_attendance_name_changes(sitting_id: int, stored_rows: list[Attendance], built_rows: list[Attendance]) -> list[AttendanceNameChange]:
    if len(stored_rows) != len(built_rows):
        raise HansardWriteCheckError(f"Sitting {sitting_id}: {len(stored_rows)} stored attendance rows, stage 7 builds {len(built_rows)}")
    name_changes = []
    for stored_row, built_row in zip(stored_rows, built_rows):
        if stored_row.is_present != built_row.is_present:
            raise HansardWriteCheckError(f"Attendance row {stored_row.id}: presence {stored_row.is_present}, stage 7 builds {built_row.is_present}")
        if stored_row.location_name != built_row.location_name:
            raise HansardWriteCheckError(f"Attendance row {stored_row.id}: location {stored_row.location_name!r}, stage 7 builds {built_row.location_name!r}")
        if stored_row.speaker_name == built_row.speaker_name:
            continue
        name_changes.append(AttendanceNameChange(
            stored_row.id, sitting_id, stored_row.speaker_name, built_row.speaker_name,
            stored_row.is_present, stored_row.location_name, stored_row.speaker_id,
        ))
    return name_changes

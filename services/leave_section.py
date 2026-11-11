import re
from typing import Optional

from schemas.leave_date_misprint import LeaveDateMisprint
from utils.names import strip_title

_SECTION_HEADING_RE = re.compile(
    r"^#*\s*(?:\*\*)?\s*permission\s+to\s+members?\s+(?:to\s+)?be\s+absent\s*(?:\*\*)?\s*:?\s*(?:\*\*)?\s*$",
    re.IGNORECASE,
)
_SIGNATURE_LINE_RE = re.compile(r"^\|?\s*_?(?:Deputy )?Speaker")
_CAPITAL_SIGNATURE_LINE_RE = re.compile(r"^\|\s*\|?\s*\(?[A-Z .]{6,}\)?,?\s*$")
_GLUED_BOLD_HEADING_RE = re.compile(r"\s*\*\*[A-Z].*$")
_NUMBERED_ITEM_LINE_RE = re.compile(r"^\([ivxlc]+\)\s")
_PREAMBLE_LINE_RE = re.compile(
    r"^(?:Under the provisions?\b|The following Member|\*\*Mr Speaker|Mr Speaker|I have|---)"
)
_CONSTITUENCY_BRACKET_RE = re.compile(r"\([^)]*\)")
_BOLD_MARKER = "**"
_TABLE_CELL_SEPARATOR = "|"
_SECTION_END_PREFIXES = ("#", "[")


def apply_leave_date_misprints(
    date_text: str, leave_date_misprints: list[LeaveDateMisprint]
) -> str:
    for leave_date_misprint in leave_date_misprints:
        date_text = re.sub(
            rf"(?<!\w){re.escape(leave_date_misprint.printed)}(?!\w)",
            leave_date_misprint.reading,
            date_text,
        )
    return date_text


def _is_section_end(line: str, is_entry_seen: bool) -> bool:
    if line.startswith(_SECTION_END_PREFIXES):
        return True
    if _SIGNATURE_LINE_RE.match(line):
        return True
    if _CAPITAL_SIGNATURE_LINE_RE.match(line):
        return True
    if _NUMBERED_ITEM_LINE_RE.match(line):
        return True
    return is_entry_seen and line.startswith(_BOLD_MARKER)


def _join_wrapped_lines(lines: list[str]) -> list[str]:
    joined_lines: list[str] = []
    is_prose_entry_open = False
    for line in lines:
        if _TABLE_CELL_SEPARATOR in line:
            joined_lines.append(line)
            is_prose_entry_open = False
            continue
        if strip_title(line) != line or _CONSTITUENCY_BRACKET_RE.search(line):
            joined_lines.append(line)
            is_prose_entry_open = True
            continue
        if is_prose_entry_open:
            joined_lines[-1] += " " + line
            continue
        joined_lines.append(line)
    return joined_lines


def get_leave_sections(markdown_content: str) -> list[list[str]]:
    sections: list[list[str]] = []
    section_lines: Optional[list[str]] = None
    is_entry_seen = False
    for markdown_line in markdown_content.split("\n"):
        line = markdown_line.strip()
        if _SECTION_HEADING_RE.match(line):
            if section_lines is not None:
                sections.append(section_lines)
            section_lines = []
            is_entry_seen = False
            continue
        if section_lines is None:
            continue
        if not line or _PREAMBLE_LINE_RE.match(line):
            continue
        if _is_section_end(line, is_entry_seen):
            sections.append(section_lines)
            section_lines = None
            continue
        glued_heading = (
            None
            if _TABLE_CELL_SEPARATOR in line or line.startswith(_BOLD_MARKER)
            else _GLUED_BOLD_HEADING_RE.search(line)
        )
        if glued_heading is not None:
            entry_text = line[: glued_heading.start()].strip()
            if entry_text:
                section_lines.append(entry_text)
            sections.append(section_lines)
            section_lines = None
            continue
        section_lines.append(line)
        is_entry_seen = True
    if section_lines is not None:
        sections.append(section_lines)
    return [_join_wrapped_lines(lines) for lines in sections if lines]

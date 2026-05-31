import re

from sqlmodel import Session, select

from database.init import engine
from database.mp import Mp
from database.sitting import Sitting
from database.sitting_attendance import SittingAttendance

# Derived from markdown content: "Parliament No:| N" header in every sitting.
VOLUME_TO_PARLIAMENT: dict[int, int] = {
    1: 1, 2: 1, 3: 1, 4: 1, 6: 1, 7: 1, 8: 1, 9: 1, 11: 1,
    12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
    20: 0, 21: 0, 22: 0, 23: 0,
    24: 1, 25: 1, 26: 1,
    27: 2, 28: 2, 29: 2, 30: 2, 31: 2,
    32: 3, 33: 3, 34: 3, 35: 3,
    36: 4, 37: 4, 38: 4, 39: 4,
    40: 5, 41: 5, 42: 5, 43: 5, 44: 5,
    45: 6, 46: 6, 47: 6, 48: 6, 49: 6, 50: 6, 51: 6,
    52: 7, 53: 7, 54: 7, 55: 7, 56: 7, 57: 7, 58: 7,
    59: 8, 60: 8, 61: 8, 62: 8, 63: 8, 64: 8, 65: 8, 66: 8,
    67: 9, 68: 9, 69: 9, 70: 9, 71: 9, 72: 9, 73: 9,
    74: 10, 75: 10, 76: 10, 77: 10, 78: 10, 79: 10, 80: 10, 81: 10,
    82: 11, 83: 11, 84: 11, 85: 11, 86: 11, 87: 11,
    88: 12, 89: 12,
}

# Title prefixes, longest first to avoid partial matches.
_TITLE_PREFIXES = [
    "The Honourable Mr ", "The Honourable Mrs ", "The Honourable Dr ",
    "The Honourable Miss ", "The Honourable Ms ", "The Honourable Inche ",
    "The Honourable Encik ", "The Honourable ",
    "Assoc. Prof. ", "Assoc Prof ",
    "Er Dr ", "Er ",
    "BG (NS) ", "BG [NS] ", "MG [NS] ", "MG (NS) ",
    "RAdm (NS) ", "RAdm ",
    "BG ", "MG ",
    "Prof. ", "Prof ",
    "Maj. ", "Maj ",
    "Dr ", "Mr ", "Mrs ", "Miss ", "Ms ", "Mdm ", "Madam ",
    "Inche ", "Encik ", "Sir ", "Dato ",
    "Asst Prof ", "Asst. Prof. ",
    "Tuan Haji ", "Haji ", "Hj. ", "Hj ",
]

# Trailing comma-separated ALL-CAPS honorific abbreviations.
# Each token may have spaces within it (e.g. "J. P." counts as one token).
_HONORIFIC_SUFFIX_RE = re.compile(r"(?:,\s*[A-Z][A-Z.]*(?:\s+[A-Z][A-Z.]*)*)+$")

# Islamic suffix like "Al-Haj", "Al-Hajj" that can follow the name after a space.
_ISLAMIC_SUFFIX_RE = re.compile(r"\s+[Aa]l-[Hh]aj[jh]?\s*$")

# Title suffixes that can appear at the end of inverted names: "Surname, Firstname, Dr".
_INVERTED_TITLE_SUFFIXES = {"Dr", "Mdm", "Mr", "Mrs", "Ms", "Prof", "Assoc Prof", "RAdm", "BG"}


def _normalize_name(name: str) -> str:
    """
    Normalise a name string for storage and lookup:
    1. Collapse spaces between consecutive initials: "E. W. Barker" -> "E.W. Barker"
    2. Normalise Malay abbreviation: "Mohd." -> "Mohd"
    Note: lone-initial period ("S. Iswaran") is NOT stripped because some Mp.name
    values keep the period (e.g. "A. Rahim Ishak") while others omit it ("S Iswaran").
    """
    name = re.sub(r"(?<=[A-Z]\.) (?=[A-Z]\.)", "", name)
    name = re.sub(r"\bMohd\.", "Mohd", name)
    return name


def _normalize_for_lookup(name: str) -> str:
    n = _normalize_name(name)
    # Additional normalization for inverted-lookup key only:
    # strip period from a lone leading initial ("S. Name" -> "S Name") so that
    # "S. Rajaratnam" matches the lookup key for "Rajaratnam, S" (stored without period).
    # This does NOT affect the stored mp_name — only the lookup search key.
    n = re.sub(r"^([A-Z])\. (?=[A-Z])", r"\1 ", n)
    return n.lower()


# Lazy-loaded lookup: (normalised_natural_name, parliament_number) -> canonical Mp.name
# Built from Mp rows whose names use "Surname, X" inverted format.
_INVERTED_LOOKUP: dict[tuple[str, int], str] = {}


def _get_inverted_lookup() -> dict[tuple[str, int], str]:
    global _INVERTED_LOOKUP
    if _INVERTED_LOOKUP:
        return _INVERTED_LOOKUP
    with Session(engine) as s:
        mps = s.exec(select(Mp)).all()

    # Track which parliament+surname keys are already used to avoid ambiguous surname-only matches.
    surname_only_counts: dict[tuple[str, int], int] = {}

    inverted_entries = []

    for mp in mps:
        parl = mp.parliament_number

        if ", " in mp.name:
            # Standard inverted format: "Surname, Firstname[, TitleSuffix]"
            parts = mp.name.split(", ")
            if len(parts) >= 3 and parts[-1] in _INVERTED_TITLE_SUFFIXES:
                surname = parts[0]
                rest = " ".join(parts[1:-1])
            else:
                surname = parts[0]
                rest = ", ".join(parts[1:])
            natural = f"{rest} {surname}"
            natural_stripped = _strip_title(natural).strip()
            key = (_normalize_for_lookup(natural_stripped), parl)
            _INVERTED_LOOKUP[key] = mp.name

            # Track surname-only key for potential later addition (only for multi-word surnames)
            surname_words = surname.split()
            if len(surname_words) >= 2:
                sk = (_normalize_for_lookup(surname), parl)
                surname_only_counts[sk] = surname_only_counts.get(sk, 0) + 1
                inverted_entries.append((sk, mp.name))
        else:
            # Non-standard "Surname Initials Firstname" format (no comma, but surname-first):
            # e.g. "Tan H.H. Augustine" -> natural order is "Augustine H.H. Tan"
            # = put last token first, keep middle tokens, put first token last.
            words = mp.name.split()
            if len(words) >= 3:
                rearranged = f"{words[-1]} {' '.join(words[1:-1])} {words[0]}"
                if rearranged != mp.name:
                    rearranged_stripped = _strip_title(rearranged).strip()
                    rk = (_normalize_for_lookup(rearranged_stripped), parl)
                    if rk not in _INVERTED_LOOKUP:
                        _INVERTED_LOOKUP[rk] = mp.name

    # Add surname-only keys only where that surname is UNIQUE within the parliament
    for sk, canonical in inverted_entries:
        if surname_only_counts.get(sk, 0) == 1 and sk not in _INVERTED_LOOKUP:
            _INVERTED_LOOKUP[sk] = canonical

    return _INVERTED_LOOKUP


def infer_parliament(sitting: Sitting) -> int | None:
    if sitting.parlement_no is not None:
        return sitting.parlement_no
    return VOLUME_TO_PARLIAMENT.get(sitting.volume_no)  # type: ignore[arg-type]


def _strip_title(text: str) -> str:
    for prefix in _TITLE_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _parse_name_and_location(text: str) -> tuple[str, str | None]:
    """
    Extract (mp_name, location_name) from text like:
      "Name, Honorifics (Constituency), Portfolio [possibly (more)]"
      "Name (Constituency)"
      "Name, Honorifics"   (no constituency)

    Uses the FIRST parenthetical as constituency, not the last, so that
    portfolio suffixes like ", Second Deputy Prime Minister (Foreign Affairs)"
    do not clobber the constituency.
    """
    text = text.strip().rstrip(". ")

    first_open = text.find("(")
    if first_open != -1:
        # Walk forward to find matching close paren (handles nesting)
        depth = 0
        close_idx = -1
        for i in range(first_open, len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    close_idx = i
                    break
        if close_idx != -1:
            constituency = text[first_open + 1 : close_idx].strip()
            name_part = text[:first_open].rstrip(", ")
        else:
            constituency = None
            name_part = text
    else:
        constituency = None
        name_part = text

    name = _strip_title(name_part.strip())
    name = _HONORIFIC_SUFFIX_RE.sub("", name).rstrip(", ").strip()
    # Strip trailing Islamic honorific suffix: "Rahmat Bin Kenap Al-Haj" -> "Rahmat Bin Kenap"
    name = _ISLAMIC_SUFFIX_RE.sub("", name).strip()
    return name, constituency


def _parse_speaker_line(line: str) -> tuple[str, str | None]:
    """
    Parse SPEAKER lines: "[Title] SPEAKER ([Title] Name [(Constituency)]).".
    Extracts the name and constituency from within the outer parentheses.
    """
    line = line.rstrip(". ")
    # Find the outermost parenthetical (greedy: first '(' to last ')')
    m = re.search(r"\((.+)\)\s*$", line)
    if not m:
        return "SPEAKER", None
    inner = m.group(1).strip()
    inner_stripped = _strip_title(inner)
    return _parse_name_and_location(inner_stripped)


def _parse_entry_line(line: str) -> tuple[str, str | None] | None:
    line = line.strip()
    if not line:
        return None
    # Strip bullet prefix for modern vol 88-89 (## Present: / ## Absent: format)
    if line.startswith("* "):
        line = line[2:].strip()
    if not line:
        return None

    if "SPEAKER" in line:
        return _parse_speaker_line(line)

    return _parse_name_and_location(_strip_title(line))


def _extract_section_lines(content: str, section: str) -> list[str]:
    """
    Extract non-empty entry lines from a PRESENT or ABSENT section.
    Handles both standard ("PRESENT:") and modern ("## Present:") headers.
    """
    lines = content.split("\n")
    in_section = False
    other = "ABSENT" if section == "PRESENT" else "PRESENT"
    result = []

    for line in lines:
        stripped = line.strip()

        if not in_section:
            # Detect section header: "PRESENT:", "**PRESENT:**", or "## Present:"
            if re.match(rf"^(?:\*{{2}}|#+)?\s*{section}\s*:(?:\*{{2}})?\s*$", stripped, re.IGNORECASE):
                in_section = True
            continue

        # End-of-section markers
        if re.match(rf"^(?:\*{{2}}|#+)?\s*{other}\s*:(?:\*{{2}})?\s*$", stripped, re.IGNORECASE):
            break
        if stripped.startswith("####") or stripped.startswith("# ") or stripped == "* * *":
            break

        if stripped:
            result.append(line)

    return result


def get_sitting_attendance(sitting: Sitting) -> list[SittingAttendance]:
    if not sitting.markdown_content:
        return []

    parliament = infer_parliament(sitting)
    inverted = _get_inverted_lookup() if parliament is not None else {}
    content = sitting.markdown_content
    records = []

    for section, is_present in [("PRESENT", True), ("ABSENT", False)]:
        for line in _extract_section_lines(content, section):
            parsed = _parse_entry_line(line)
            if not parsed:
                continue
            name, location = parsed
            if not name:
                continue
            # Normalise initials and Malay abbreviation before lookup and storage.
            name = _normalize_name(name)
            # Map to canonical Mp.name form for inverted-format MPs.
            if parliament is not None:
                canonical = inverted.get((_normalize_for_lookup(name), parliament))
                if canonical:
                    name = canonical
            records.append(SittingAttendance(
                sitting_id=sitting.id,
                mp_name=name,
                attendance=is_present,
                location_name=location,
            ))

    return records

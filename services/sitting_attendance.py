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

# Manual overrides for names that cannot be resolved by general normalisation rules.
# Key: (period_normalized_extracted_name, parliament_number)
# Value: canonical Mp.name
_MANUAL_OVERRIDES: dict[tuple[str, int], str] = {
    # Mp table has typo "Gahni" instead of "Ghani"
    ("ahmad khalis bin abdul ghani", 10): "Ahmad Khalis bin Abdul Gahni",
    # "B M M" is an abbreviation of "Bin Masagos Mohamad"
    ("masagos zulkifli b m m", 11): "Masagos Zulkifli Bin Masagos Mohamad",
    ("masagos zulkifli b m m", 12): "Masagos Zulkifli Bin Masagos Mohamad",
    # Extracted name lacks the ", Dr" title suffix present in Mp.name
    ("lim chun leng, michael", 8): "Lim Chun Leng, Michael, Dr",
    ("lim chun leng, michael", 9): "Lim Chun Leng, Michael, Dr",
    ("lim chun leng, michael", 10): "Lim Chun Leng, Michael, Dr",
    # One-letter spelling difference in Mp.name
    ("abdul nasser bin kamaruddin", 7): "Abdul Nasser Bin Kamarudin",
    ("seet ai mee", 7): "Seet Ai Mei, Dr",
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
    "Cdre ", "[NS] ", "(NS) ",
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

# Lazy-loaded fallback: (period_stripped_name, parliament_number) -> canonical Mp.name
# Covers names like "S Jayakumar", "K Shanmugam" where the Mp table omits the period
# that appears in the markdown ("S. Jayakumar", "K. Shanmugam").
_DIRECT_LOOKUP: dict[tuple[str, int], str] = {}


def _period_normalize(name: str) -> str:
    """
    Normalize for period-stripped key comparison:
    'M.K.A. Jabbar' -> 'm k a jabbar'
    'J.B. Jeyaretnam' -> 'j b jeyaretnam'
    'S. Jayakumar' -> 's jayakumar'
    'Harun bin A. Ghani' -> 'harun bin a ghani'
    """
    # Insert space between consecutive uppercase initials using lookbehind/lookahead
    # so all pairs are split in one pass: "M.K.A." -> "M K A." (positions don't consume).
    n = re.sub(r"(?<=[A-Z])\.(?=[A-Z])", " ", name)
    n = re.sub(r"([A-Z])\.", r"\1", n)   # strip remaining trailing period: "K." -> "K"
    n = re.sub(r"\s+", " ", n)
    return n.strip().lower()


def _get_direct_lookup() -> dict[tuple[str, int], str]:
    global _DIRECT_LOOKUP
    if _DIRECT_LOOKUP:
        return _DIRECT_LOOKUP
    with Session(engine) as s:
        mps = s.exec(select(Mp)).all()
    # Only add unambiguous keys (unique within each parliament).
    counts: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for mp in mps:
        key = (_period_normalize(mp.name), mp.parliament_number)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, mp.name))
    for key, canonical in entries:
        if counts[key] == 1:
            _DIRECT_LOOKUP[key] = canonical
    return _DIRECT_LOOKUP


def _strip_bin(name: str) -> str:
    """Remove the Malay 'bin'/'binte' patronymic connector (case-insensitive)."""
    return re.sub(r"\s+bin(?:te)?\s+", " ", name, flags=re.IGNORECASE).strip()


def _strip_middle_haji(name: str) -> str:
    """Remove 'Haji'/'Tuan Haji' from the middle of a name (not as a prefix).
    Used as a lookup fallback: 'Saidi Haji Shariff' -> 'Saidi Shariff'."""
    return re.sub(r"\s+(?:[Tt]uan\s+)?[Hh]aji\s+", " ", name).strip()


def _spelling_normalize(name: str) -> str:
    """
    Normalise common spelling variants for lookup purposes only:
    - Mohamad/Mohammed/Mohammad -> Mohamed
    - Consecutive spaced single uppercase letters -> joined: "B P M" -> "BPM"
    - Hyphens -> spaces (to match "Lee Siew-Choh" against "Lee Siew Choh")
    """
    n = re.sub(r"\bMohamad\b|\bMohammed\b|\bMohammad\b", "Mohamed", name)
    n = n.replace("-", " ")
    # Collapse sequences of spaced single uppercase letters: "B P M" -> "BPM"
    n = re.sub(r"\b([A-Z])((?:\s+[A-Z])+)\b", lambda m: m.group(1) + m.group(2).replace(" ", ""), n)
    return re.sub(r"\s+", " ", n).strip()


# Lazy-loaded bin-free fallback: (period_stripped + bin_stripped key, parliament) -> canonical
# Handles mismatches where markdown omits 'Bin' present in Mp.name ("Abdullah Tarmugi" ->
# "Abdullah Bin Tarmugi") and vice-versa ("Ibrahim bin Othman" -> "Ibrahim Othman").
_BIN_FREE_LOOKUP: dict[tuple[str, int], str] = {}


def _get_bin_free_lookup() -> dict[tuple[str, int], str]:
    global _BIN_FREE_LOOKUP
    if _BIN_FREE_LOOKUP:
        return _BIN_FREE_LOOKUP
    with Session(engine) as s:
        mps = s.exec(select(Mp)).all()
    counts: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for mp in mps:
        key = (_period_normalize(_strip_bin(mp.name)), mp.parliament_number)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, mp.name))
    direct = _get_direct_lookup()
    for key, canonical in entries:
        if counts[key] == 1 and key not in direct:
            _BIN_FREE_LOOKUP[key] = canonical
    return _BIN_FREE_LOOKUP


# Lazy-loaded word-set lookup: (frozenset_of_words, word_count, parliament) -> canonical
# Handles name permutation mismatches where markdown writes words in a different order
# than what the Mp table or inverted lookup expects:
#   "George Yong-Boon Yeo"  <-> "Yeo Yong-Boon, George"
#   "David T.E. Lim"        <-> "Lim T E, David"
#   "Aline K. Wong"         <-> "Wong Aline K"
#   "Dixie Tan"             <-> "Tan Dixie"
# Only unambiguous keys (unique frozenset+count within each parliament) are stored.
_WORDSET_LOOKUP: dict[tuple[frozenset, int, int], str] = {}


def _get_wordset_lookup() -> dict[tuple[frozenset, int, int], str]:
    global _WORDSET_LOOKUP
    if _WORDSET_LOOKUP:
        return _WORDSET_LOOKUP
    with Session(engine) as s:
        mps = s.exec(select(Mp)).all()
    # Build (natural_display_form, canonical_mp_name, parliament) triples.
    # For inverted names ("Surname, Firstname") add the natural form alongside.
    triples: list[tuple[str, str, int]] = []
    for mp in mps:
        if ", " in mp.name:
            parts = mp.name.split(", ")
            if len(parts) >= 3 and parts[-1] in _INVERTED_TITLE_SUFFIXES:
                rest = " ".join(parts[1:-1])
            else:
                rest = ", ".join(parts[1:])
            natural = _strip_title(f"{rest} {parts[0]}").strip()
            triples.append((natural, mp.name, mp.parliament_number))
        triples.append((mp.name, mp.name, mp.parliament_number))
    counts: dict[tuple[frozenset, int, int], int] = {}
    entries: list[tuple[tuple[frozenset, int, int], str]] = []
    for display, canonical_mp_name, parl in triples:
        words = _period_normalize(display).split()
        key: tuple[frozenset, int, int] = (frozenset(words), len(words), parl)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, canonical_mp_name))
    for key, canonical_mp_name in entries:
        if counts[key] == 1 and key not in _WORDSET_LOOKUP:
            _WORDSET_LOOKUP[key] = canonical_mp_name
    return _WORDSET_LOOKUP


def _wordset_key(name: str) -> tuple[frozenset, int]:
    words = _period_normalize(name).split()
    return frozenset(words), len(words)


# Lazy-loaded prefix lookup: (period_normalized_prefix, parliament) -> canonical Mp.name
# Handles names like "Bernard Chen" that are a strict prefix of the canonical full name
# "Bernard Chen Tien Lap" (natural form of "Chen Tien Lap, Bernard").
# Only unambiguous prefixes (unique within each parliament) are stored.
_PREFIX_LOOKUP: dict[tuple[str, int], str] = {}


def _get_prefix_lookup() -> dict[tuple[str, int], str]:
    global _PREFIX_LOOKUP
    if _PREFIX_LOOKUP:
        return _PREFIX_LOOKUP
    with Session(engine) as s:
        mps = s.exec(select(Mp)).all()
    # Collect (display_form, canonical_mp_name, parliament) triples.
    forms: list[tuple[str, str, int]] = []
    for mp in mps:
        if ", " in mp.name:
            parts = mp.name.split(", ")
            if len(parts) >= 3 and parts[-1] in _INVERTED_TITLE_SUFFIXES:
                rest = " ".join(parts[1:-1])
            else:
                rest = ", ".join(parts[1:])
            natural = _strip_title(f"{rest} {parts[0]}").strip()
            forms.append((natural, mp.name, mp.parliament_number))
        forms.append((mp.name, mp.name, mp.parliament_number))
    counts: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for display, canonical, parl in forms:
        words = _period_normalize(display).split()
        for n in range(2, len(words)):
            prefix = " ".join(words[:n])
            key = (prefix, parl)
            counts[key] = counts.get(key, 0) + 1
            entries.append((key, canonical))
    for key, canonical in entries:
        if counts[key] == 1 and key not in _PREFIX_LOOKUP:
            _PREFIX_LOOKUP[key] = canonical
    return _PREFIX_LOOKUP


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
    # Strip leading OCR digit artifacts: "2Mr" -> "Mr"
    line = re.sub(r"^\d+(?=[A-Z])", "", line)

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
        # Numbered oral-question marker ("1\. **Mr X asked...") signals section end.
        if re.match(r"^\d+\\\.?\s", stripped):
            break

        if stripped:
            result.append(line)

    return result


def resolve_canonical_name(name: str, parliament: int) -> str | None:
    """
    Try to match a name string to canonical Mp.name using the full lookup cascade.
    Returns canonical Mp.name if found, None if no match.
    Reusable by any module that needs MP name resolution.
    """
    inverted = _get_inverted_lookup()
    direct = _get_direct_lookup()
    bin_free = _get_bin_free_lookup()
    wordset = _get_wordset_lookup()
    prefix = _get_prefix_lookup()

    canonical = _MANUAL_OVERRIDES.get((_period_normalize(name), parliament))
    if canonical:
        return canonical
    canonical = inverted.get((_normalize_for_lookup(name), parliament))
    if canonical:
        return canonical
    canonical = direct.get((_period_normalize(name), parliament))
    if canonical:
        return canonical
    bin_key = (_period_normalize(_strip_bin(name)), parliament)
    canonical = bin_free.get(bin_key) or direct.get(bin_key)
    if canonical:
        return canonical
    ws, wc = _wordset_key(name)
    canonical = wordset.get((ws, wc, parliament))
    if canonical:
        return canonical
    canonical = prefix.get((_period_normalize(name), parliament))
    if canonical:
        return canonical

    spell = _spelling_normalize(name)
    if spell != name:
        sp = _period_normalize(spell)
        sp_bin = _period_normalize(_strip_bin(spell))
        canonical = (
            direct.get((sp, parliament))
            or bin_free.get((sp_bin, parliament))
            or direct.get((sp_bin, parliament))
            or wordset.get((*_wordset_key(spell), parliament))
            or prefix.get((sp, parliament))
        )
    if canonical:
        return canonical

    no_haji = _strip_middle_haji(name)
    if no_haji != name:
        nh = _period_normalize(no_haji)
        nh_bin = _period_normalize(_strip_bin(no_haji))
        canonical = (
            direct.get((nh, parliament))
            or bin_free.get((nh_bin, parliament))
            or direct.get((nh_bin, parliament))
            or prefix.get((nh, parliament))
        )
    if canonical:
        return canonical

    # CamelCase split fallback for source markdown that concatenated names without
    # spaces ("AbdullahTarmugi"). Re-strip title after splitting in case the missing
    # space prevented _strip_title from matching at extraction time.
    split = re.sub(r"([a-z\.])([A-Z])", r"\1 \2", name)
    if split != name:
        split_stripped = _strip_title(split).strip()
        sp2 = _period_normalize(split_stripped)
        sp2_bin = _period_normalize(_strip_bin(split_stripped))
        canonical = (
            _MANUAL_OVERRIDES.get((sp2, parliament))
            or direct.get((sp2, parliament))
            or bin_free.get((sp2_bin, parliament))
            or direct.get((sp2_bin, parliament))
            or wordset.get((*_wordset_key(split_stripped), parliament))
            or prefix.get((sp2, parliament))
        )
    return canonical


def get_sitting_attendance(sitting: Sitting) -> list[SittingAttendance]:
    if not sitting.markdown_content:
        return []

    parliament = infer_parliament(sitting)
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
            name = _normalize_name(name)
            if parliament is not None:
                canonical = resolve_canonical_name(name, parliament)
                if canonical:
                    name = canonical
            records.append(SittingAttendance(
                sitting_id=sitting.id,
                mp_name=name,
                attendance=is_present,
                location_name=location,
            ))

    return records

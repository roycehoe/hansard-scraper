import re
from dataclasses import dataclass
from typing import Optional

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
    # Colonial-era variant spellings
    # "D.S. Marshall" is David Marshall (Labour Front Chief Minister)
    ("d s marshall", 1): "David Marshall",
    # "G.E.N. Oehlers" is George E.N. Oehlers (Labour Front)
    ("g e n oehlers", 1): "George Oehlers",
    # "Rahamat" is a spelling variant of "Rahmat" (already in Mp table)
    ("rahamat bin kenap", 1): "Rahmat Bin Kenap",
    # OCR spelling variants of existing parliament-1 MPs
    # "Koo Young" is "Koo Yong" (Barisan Sosialis)
    ("koo young", 1): "Koo Yong",
    # "Chew Chin Han" is "Chew Chin Harn" (People's Action Party)
    ("chew chin han", 1): "Chew Chin Harn",
    # Surname-only speech forms for colonial officials -- all unique in parliament 1
    ("hart", 1): "Hart, T.M.",
    ("goode", 1): "Goode, W.A.C.",
    ("butterfield", 1): "Butterfield, C.H.",
    ("shanks", 1): "Shanks, E.P.",
    ("david", 1): "David, E.B.",
    ("sutherland", 1): "Sutherland, G.A.P.",
    ("stewart", 1): "Stewart, S.T.",
    ("davies", 1): "Davies, E.J.",
    ("higham", 1): "Higham, J.D.",
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
    # Surname-only references: "Mr Jeyaretnam", "Prof. Jayakumar", etc.
    ("jeyaretnam", 5): "J B Jeyaretnam",
    ("jeyaretnam", 6): "J B Jeyaretnam",
    ("jeyaretnam", 9): "J B Jeyaretnam",
    ("jayakumar", 5): "S Jayakumar",
    ("jayakumar", 6): "S Jayakumar",
    ("jayakumar", 7): "S Jayakumar",
    ("jayakumar", 8): "S Jayakumar",
    ("jayakumar", 9): "S Jayakumar",
    ("jayakumar", 10): "S Jayakumar",
    ("jayakumar", 11): "S Jayakumar",
    ("dhanabalan", 4): "S. Dhanabalan",
    ("dhanabalan", 5): "S. Dhanabalan",
    ("dhanabalan", 6): "S. Dhanabalan",
    ("dhanabalan", 7): "S. Dhanabalan",
    ("dhanabalan", 8): "S. Dhanabalan",
    # Barker, E.W. stored in inverted format; last word of canonical is "E.W." not "Barker"
    ("barker", 1): "Barker, E.W.",
    ("barker", 2): "Barker, E.W.",
    ("barker", 3): "Barker, E.W.",
    ("barker", 4): "Barker, E.W.",
    ("barker", 5): "Barker, E.W.",
    ("barker", 6): "Barker, E.W.",
    # Bani, S.T. stored in inverted format; resolved after parl=0 fallback to parl=1
    ("bani", 1): "Bani, S.T.",
    # Full-name variant: "Joshua Benjamin Jeyaretnam" for J B Jeyaretnam
    ("joshua benjamin jeyaretnam", 5): "J B Jeyaretnam",
    ("joshua benjamin jeyaretnam", 6): "J B Jeyaretnam",
    # Apostrophe variant: "Ya'acob" vs "Yaacob" in Mp table
    ("ya'acob bin mohamed", 1): "Yaacob Bin Mohamed",
    ("ya'acob bin mohamed", 2): "Yaacob Bin Mohamed",
    ("ya'acob bin mohamed", 3): "Yaacob Bin Mohamed",
    ("ya'acob bin mohamed", 4): "Yaacob Bin Mohamed",
    # S. Rajaratnam stored inverted as "Rajaratnam, S"; "Mr. S. Rajaratnam" leaves "Mr."
    # after strip_title which doesn't handle the period-after-title form
    ("s rajaratnam", 1): "Rajaratnam, S",
    ("s rajaratnam", 2): "Rajaratnam, S",
    ("s rajaratnam", 3): "Rajaratnam, S",
    ("s rajaratnam", 4): "Rajaratnam, S",
    ("s rajaratnam", 5): "Rajaratnam, S",
    ("s rajaratnam", 6): "Rajaratnam, S",
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
    "Inche ", "Encik ", "Sir ", "Dato ", "Tun Dato ", "Tun ",
    "Asst Prof ", "Asst. Prof. ",
    "Tuan Haji ", "Haji ", "Hj. ", "Hj ",
    "Cdre ", "[NS] ", "(NS) ",
]

# Trailing comma-separated ALL-CAPS honorific abbreviations.
# Each token may have spaces within it (e.g. "J. P." counts as one token).
_HONORIFIC_SUFFIX_RE = re.compile(r"(?:,\s*[A-Z][A-Z.]*(?:\s+[A-Z][A-Z.]*)*)+$")

# Islamic suffix like "Al-Haj", "Al-Hajj" that can follow the name after a space.
_ISLAMIC_SUFFIX_RE = re.compile(r"\s+[Aa]l-[Hh]aj[jh]?\s*$")

# Trailing official role suffix: ", Financial Secretary", ", Attorney-General", etc.
# Applied before _HONORIFIC_SUFFIX_RE so that mixed-case role titles don't block
# the all-caps honorific stripping (e.g. "Hart, C.M.G., Financial Secretary" ->
# strip role -> "Hart, C.M.G." -> strip honorific -> "Hart").
_OFFICIAL_ROLE_SUFFIX_RE = re.compile(
    r",\s*(?:Acting\s+)?(?:Financial|Chief|Colonial)\s+Secretary"
    r"|,\s*Attorney[-\s]General"
    r"|,\s*(?:Acting\s+)?Governor\b",
    re.I,
)

# Title suffixes that can appear at the end of inverted names: "Surname, Firstname, Dr".
_INVERTED_TITLE_SUFFIXES = {"Dr", "Mdm", "Mr", "Mrs", "Ms", "Prof", "Assoc Prof", "RAdm", "BG"}

_MIN_SURNAME_LOOKUP_LENGTH = 2
_MIN_PREFIX_WORD_COUNT = 2
_MIN_MULTIWORD_SURNAME_LENGTH = 2
_MIN_REARRANGEABLE_WORD_COUNT = 3


def normalize_name(name: str) -> str:
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
    normalized = normalize_name(name)
    # Additional normalization for inverted-lookup key only:
    # strip period from a lone leading initial ("S. Name" -> "S Name") so that
    # "S. Rajaratnam" matches the lookup key for "Rajaratnam, S" (stored without period).
    # This does NOT affect the stored mp_name -- only the lookup search key.
    normalized = re.sub(r"^([A-Z])\. (?=[A-Z])", r"\1 ", normalized)
    return normalized.lower()


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
    normalized = re.sub(r"(?<=[A-Z])\.(?=[A-Z])", " ", name)
    normalized = re.sub(r"([A-Z])\.", r"\1", normalized)   # strip remaining trailing period: "K." -> "K"
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


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
    normalized = re.sub(r"\bMohamad\b|\bMohammed\b|\bMohammad\b", "Mohamed", name)
    normalized = normalized.replace("-", " ")
    # Collapse sequences of spaced single uppercase letters: "B P M" -> "BPM"
    normalized = re.sub(
        r"\b([A-Z])((?:\s+[A-Z])+)\b",
        lambda abbrev_match: abbrev_match.group(1) + abbrev_match.group(2).replace(" ", ""),
        normalized,
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _invert_to_natural(mp_name: str) -> Optional[str]:
    """Convert 'Surname, Firstname[, TitleSuffix]' to natural 'Firstname Surname' form.
    Returns None if the name is not in inverted format."""
    if ", " not in mp_name:
        return None
    parts = mp_name.split(", ")
    if len(parts) >= 3 and parts[-1] in _INVERTED_TITLE_SUFFIXES:
        rest = " ".join(parts[1:-1])
    else:
        rest = ", ".join(parts[1:])
    return strip_title(f"{rest} {parts[0]}").strip()


def _wordset_key(name: str) -> tuple[frozenset, int]:
    words = _period_normalize(name).split()
    return frozenset(words), len(words)


def strip_title(text: str) -> str:
    while True:
        for prefix in _TITLE_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        else:
            return text


def infer_parliament(sitting: Sitting) -> Optional[int]:
    if sitting.parlement_no is not None:
        return sitting.parlement_no
    return VOLUME_TO_PARLIAMENT.get(sitting.volume_no)  # type: ignore[arg-type]


@dataclass
class MpLookups:
    inverted: dict[tuple[str, int], str]
    direct: dict[tuple[str, int], str]
    bin_free: dict[tuple[str, int], str]
    wordset: dict[tuple[frozenset, int, int], str]
    prefix: dict[tuple[str, int], str]
    surname_fallback: dict[tuple[str, int], str]


def _build_direct_lookup(mps: list[Mp]) -> dict[tuple[str, int], str]:
    counts: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for mp in mps:
        key = (_period_normalize(mp.name), mp.parliament_number)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, mp.name))
    return {key: canonical for key, canonical in entries if counts[key] == 1}


def _build_bin_free_lookup(
    mps: list[Mp],
    direct: dict[tuple[str, int], str],
) -> dict[tuple[str, int], str]:
    counts: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for mp in mps:
        key = (_period_normalize(_strip_bin(mp.name)), mp.parliament_number)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, mp.name))
    return {key: canonical for key, canonical in entries if counts[key] == 1 and key not in direct}


def _build_inverted_lookup(mps: list[Mp]) -> dict[tuple[str, int], str]:
    inverted: dict[tuple[str, int], str] = {}
    surname_only_counts: dict[tuple[str, int], int] = {}
    surname_only_entries: list[tuple[tuple[str, int], str]] = []
    for mp in mps:
        parliament = mp.parliament_number
        if ", " in mp.name:
            natural_stripped = _invert_to_natural(mp.name)
            key = (_normalize_for_lookup(natural_stripped), parliament)
            inverted[key] = mp.name
            surname = mp.name.split(", ")[0]
            surname_words = surname.split()
            if len(surname_words) >= _MIN_MULTIWORD_SURNAME_LENGTH:
                surname_key = (_normalize_for_lookup(surname), parliament)
                surname_only_counts[surname_key] = surname_only_counts.get(surname_key, 0) + 1
                surname_only_entries.append((surname_key, mp.name))
        else:
            words = mp.name.split()
            if len(words) >= _MIN_REARRANGEABLE_WORD_COUNT:
                rearranged = f"{words[-1]} {' '.join(words[1:-1])} {words[0]}"
                if rearranged != mp.name:
                    rearranged_stripped = strip_title(rearranged).strip()
                    rearranged_key = (_normalize_for_lookup(rearranged_stripped), parliament)
                    if rearranged_key not in inverted:
                        inverted[rearranged_key] = mp.name
    for surname_key, canonical in surname_only_entries:
        if surname_only_counts.get(surname_key, 0) == 1 and surname_key not in inverted:
            inverted[surname_key] = canonical
    return inverted


def _build_wordset_lookup(mps: list[Mp]) -> dict[tuple[frozenset, int, int], str]:
    triples: list[tuple[str, str, int]] = []
    for mp in mps:
        natural = _invert_to_natural(mp.name)
        if natural:
            triples.append((natural, mp.name, mp.parliament_number))
        triples.append((mp.name, mp.name, mp.parliament_number))
    counts: dict[tuple[frozenset, int, int], int] = {}
    entries: list[tuple[tuple[frozenset, int, int], str]] = []
    for display, canonical_name, parliament in triples:
        words = _period_normalize(display).split()
        key = (frozenset(words), len(words), parliament)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, canonical_name))
    wordset: dict[tuple[frozenset, int, int], str] = {}
    for key, canonical_name in entries:
        if counts[key] == 1 and key not in wordset:
            wordset[key] = canonical_name
    return wordset


def _build_prefix_lookup(mps: list[Mp]) -> dict[tuple[str, int], str]:
    forms: list[tuple[str, str, int]] = []
    for mp in mps:
        natural = _invert_to_natural(mp.name)
        if natural:
            forms.append((natural, mp.name, mp.parliament_number))
        forms.append((mp.name, mp.name, mp.parliament_number))
    prefix_counts: dict[tuple[str, int], int] = {}
    prefix_entries: list[tuple[tuple[str, int], str]] = []
    for display, canonical, parliament in forms:
        words = _period_normalize(display).split()
        for prefix_length in range(_MIN_PREFIX_WORD_COUNT, len(words)):
            prefix_str = " ".join(words[:prefix_length])
            prefix_key = (prefix_str, parliament)
            prefix_counts[prefix_key] = prefix_counts.get(prefix_key, 0) + 1
            prefix_entries.append((prefix_key, canonical))
    prefix: dict[tuple[str, int], str] = {}
    for prefix_key, canonical in prefix_entries:
        if prefix_counts[prefix_key] == 1 and prefix_key not in prefix:
            prefix[prefix_key] = canonical
    return prefix


def _build_surname_fallback_lookup(mps: list[Mp]) -> dict[tuple[str, int], str]:
    surname_counts: dict[tuple[str, int], int] = {}
    surname_entries: list[tuple[tuple[str, int], str]] = []
    for mp in mps:
        natural = _invert_to_natural(mp.name) or mp.name
        words = _period_normalize(natural).split()
        if not words:
            continue
        last_word = words[-1]
        if len(last_word) < _MIN_SURNAME_LOOKUP_LENGTH:
            continue
        surname_key = (last_word, mp.parliament_number)
        surname_counts[surname_key] = surname_counts.get(surname_key, 0) + 1
        surname_entries.append((surname_key, mp.name))
    return {key: canonical for key, canonical in surname_entries if surname_counts[key] == 1}


def build_mp_lookups(mps: list[Mp]) -> MpLookups:
    direct = _build_direct_lookup(mps)
    return MpLookups(
        direct=direct,
        bin_free=_build_bin_free_lookup(mps, direct),
        inverted=_build_inverted_lookup(mps),
        wordset=_build_wordset_lookup(mps),
        prefix=_build_prefix_lookup(mps),
        surname_fallback=_build_surname_fallback_lookup(mps),
    )


def _parse_name_and_location(text: str) -> tuple[str, Optional[str]]:
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
        for char_index in range(first_open, len(text)):
            if text[char_index] == "(":
                depth += 1
            elif text[char_index] == ")":
                depth -= 1
                if depth == 0:
                    close_idx = char_index
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

    name = strip_title(name_part.strip())
    name = _OFFICIAL_ROLE_SUFFIX_RE.sub("", name).rstrip(", ").strip()
    name = _HONORIFIC_SUFFIX_RE.sub("", name).rstrip(", ").strip()
    # Strip trailing Islamic honorific suffix: "Rahmat Bin Kenap Al-Haj" -> "Rahmat Bin Kenap"
    name = _ISLAMIC_SUFFIX_RE.sub("", name).strip()
    return name, constituency


def _parse_speaker_line(line: str) -> tuple[str, Optional[str]]:
    """
    Parse SPEAKER lines: "[Title] SPEAKER ([Title] Name [(Constituency)]).".
    Extracts the name and constituency from within the outer parentheses.
    """
    line = line.rstrip(". ")
    # Find the outermost parenthetical (greedy: first '(' to last ')')
    match = re.search(r"\((.+)\)\s*$", line)
    if not match:
        return "SPEAKER", None
    inner = match.group(1).strip()
    inner_stripped = strip_title(inner)
    return _parse_name_and_location(inner_stripped)


def _parse_entry_line(line: str) -> Optional[tuple[str, Optional[str]]]:
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

    return _parse_name_and_location(strip_title(line))


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


def _try_name_variant(
    name: str,
    parliament: int,
    lookups: MpLookups,
    include_wordset: bool = True,
) -> Optional[str]:
    normalized = _period_normalize(name)
    bin_normalized = _period_normalize(_strip_bin(name))
    result = (
        lookups.direct.get((normalized, parliament))
        or lookups.bin_free.get((bin_normalized, parliament))
        or lookups.direct.get((bin_normalized, parliament))
    )
    if result:
        return result
    if include_wordset:
        result = lookups.wordset.get((*_wordset_key(name), parliament))
        if result:
            return result
    return lookups.prefix.get((normalized, parliament))


def resolve_canonical_name(name: str, parliament: int, lookups: MpLookups) -> Optional[str]:
    """
    Try to match a name string to canonical Mp.name using the full lookup cascade.
    Returns canonical Mp.name if found, None if no match.
    Reusable by any module that needs MP name resolution.
    """
    canonical = _MANUAL_OVERRIDES.get((_period_normalize(name), parliament))
    if canonical:
        return canonical
    canonical = lookups.inverted.get((_normalize_for_lookup(name), parliament))
    if canonical:
        return canonical
    canonical = _try_name_variant(name, parliament, lookups)
    if canonical:
        return canonical

    spelled = _spelling_normalize(name)
    if spelled != name:
        canonical = _try_name_variant(spelled, parliament, lookups)
        if canonical:
            return canonical

    no_haji = _strip_middle_haji(name)
    if no_haji != name:
        canonical = _try_name_variant(no_haji, parliament, lookups, include_wordset=False)
        if canonical:
            return canonical

    # CamelCase split fallback for source markdown that concatenated names without
    # spaces ("AbdullahTarmugi"). Re-strip title after splitting in case the missing
    # space prevented strip_title from matching at extraction time.
    split = re.sub(r"([a-z\.])([A-Z])", r"\1 \2", name)
    if split != name:
        split_stripped = strip_title(split).strip()
        canonical = (
            _MANUAL_OVERRIDES.get((_period_normalize(split_stripped), parliament))
            or _try_name_variant(split_stripped, parliament, lookups)
        )
        if canonical:
            return canonical

    # Surname-only fallback: if name reduces to a single token, try it as the unique
    # last name in this parliament.  Only fires for unambiguous cases.
    words_pn = _period_normalize(name).split()
    if len(words_pn) == 1:
        return lookups.surname_fallback.get((words_pn[0], parliament))
    return None


def resolve(name: str, parliament: int, lookups: MpLookups) -> Optional[str]:
    return resolve_canonical_name(normalize_name(name), parliament, lookups)


def get_sitting_attendance(sitting: Sitting, lookups: MpLookups) -> list[SittingAttendance]:
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
            name = normalize_name(name)
            if parliament is not None:
                canonical = resolve_canonical_name(name, parliament, lookups)
                if canonical:
                    name = canonical
            records.append(SittingAttendance(
                sitting_id=sitting.id,
                mp_name=name,
                attendance=is_present,
                location_name=location,
            ))

    return records

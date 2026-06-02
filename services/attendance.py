import re
from dataclasses import dataclass
from typing import Optional

from database.attendance import Attendance
from database.sitting import Sitting
from database.speaker import Speaker

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
# Value: canonical Speaker.name
_MANUAL_OVERRIDES: dict[tuple[str, int], str] = {
    # Post-independence OCR variants (parl=3-6, volumes 32-51)
    # "Lai Tha Chai" / "Lai Tha Chia" are OCR of "Lai Tai Chai" (Henderson, elected 1972);
    # confirmed in volumes 32-51 which map to parl=3-6 exactly.
    ("lai tha chai", 3): "Lai Tai Chai",
    ("lai tha chai", 4): "Lai Tai Chai",
    ("lai tha chai", 5): "Lai Tai Chai",
    ("lai tha chai", 6): "Lai Tai Chai",
    ("lai tha chia", 3): "Lai Tai Chai",
    ("lai tha chia", 4): "Lai Tai Chai",
    ("lai tha chia", 5): "Lai Tai Chai",
    ("lai tha chia", 6): "Lai Tai Chai",
    # OCR single-character corruption: post-colonial and colonial name variants
    # "Chin Ham Tong" is "Chin Harn Tong" (PAP); vols 32-39 → parl=3,4
    ("chin ham tong", 3): "Chin Harn Tong",
    ("chin ham tong", 4): "Chin Harn Tong",
    # "lbrahim Othman" — lowercase 'l' for capital 'I'; vols 45-46 → parl=6
    ("lbrahim othman", 6): "Ibrahim Othman",
    # "Yong Nyuk Lm" — truncated "Lin"; vol 14 → parl=0(fb1), vol 32 → parl=3
    ("yong nyuk lm", 1): "Yong Nyuk Lin",
    ("yong nyuk lm", 3): "Yong Nyuk Lin",
    # "Leong Keng Sung" — 'u' for 'e'; vols 15,19 → parl=0(fb1)
    ("leong keng sung", 1): "Leong Keng Seng",
    # Rahmat Bin Kenap variants: OCR suffix corruption and prefix confusion
    # "A1-Haj" is OCR of "Al-Haj" (digit 1 for letter l); vols 32-34 → parl=3
    ("rahmat bin kenap a1-haj", 3): "Rahmat Bin Kenap",
    # "Haii Rahmat bin Kenap" — "Haii" prefix is OCR of "Haji"; vols 36,39 → parl=4
    ("haii rahmat bin kenap", 4): "Rahmat Bin Kenap",
    # "Rahmat bin Kensp" — "Kensp" for "Kenap"; vol 38 → parl=4
    ("rahmat bin kensp", 4): "Rahmat Bin Kenap",
    # Colonial-era OCR single-char variants — parl=1 covers colonial (direct + parl=0 fallback);
    # additional parliament entries cover the same OCR form in post-colonial volumes.
    # "A. Rahim lshak" — lowercase 'l' for capital 'I' in "Ishak"; vols 36(p4), 41-44(p5)
    ("a rahim lshak", 1): "A. Rahim Ishak",
    ("a rahim lshak", 4): "A. Rahim Ishak",
    ("a rahim lshak", 5): "A. Rahim Ishak",
    # "Jek Youn Thong" — vols 38(p4), 40(p5)
    ("jek youn thong", 1): "Jek Yeun Thong",
    ("jek youn thong", 4): "Jek Yeun Thong",
    ("jek youn thong", 5): "Jek Yeun Thong",
    # "Jek Yuen Thong" — vols 6/13-25(p0-1), 32(p3), 39(p4), 47(p6)
    ("jek yuen thong", 1): "Jek Yeun Thong",
    ("jek yuen thong", 3): "Jek Yeun Thong",
    ("jek yuen thong", 4): "Jek Yeun Thong",
    ("jek yuen thong", 6): "Jek Yeun Thong",
    # "Wee loon Boon" — vol 34(p3)
    ("wee loon boon", 1): "Wee Toon Boon",
    ("wee loon boon", 3): "Wee Toon Boon",
    # "Wee Toon. Boon" — vol 28(p2); period after lowercase 'n' survives _period_normalize
    ("wee toon. boon", 2): "Wee Toon Boon",
    # "Yaacoh Bin Mohamed" — vols 13/17(p0), 25(p1)
    ("yaacoh bin mohamed", 1): "Yaacob Bin Mohamed",
    # "Toh Chih Chye" — vol 44(p5)
    ("toh chih chye", 1): "Toh Chin Chye",
    ("toh chih chye", 5): "Toh Chin Chye",
    # "Ng Kah Tins" — vol 23(p0 → fb1)
    ("ng kah tins", 1): "Ng Kah Ting",
    # "Ho Chong Choon" — vol 37(p4)
    ("ho chong choon", 1): "Ho Cheng Choon",
    ("ho chong choon", 4): "Ho Cheng Choon",
    # "Ho Kah Loong" — vols 39(p4), 41/44(p5)
    ("ho kah loong", 1): "Ho Kah Leong",
    ("ho kah loong", 4): "Ho Kah Leong",
    ("ho kah loong", 5): "Ho Kah Leong",
    # "Lob Miaw Gong" — vol 22(p0 → fb1)
    ("lob miaw gong", 1): "Loh Miaw Gong",
    # "Sia Kat Hui" — vol 33(p3)
    ("sia kat hui", 1): "Sia Kah Hui",
    ("sia kat hui", 3): "Sia Kah Hui",
    # "Buang Bin Omar Junied" — vol 26(p1)
    ("buang bin omar junied", 1): "Buang Bin Omar Junid",
    # "Wang Soon Fong" — vols 19/21(p0 → fb1), 25(p1)
    ("wang soon fong", 1): "Wong Soon Fong",
    # "Urn Cheng Lock" — vol 17(p0 → fb1)
    ("urn cheng lock", 1): "Lim Cheng Lock",
    # "Gob" → "Goh": OCR confusion of 'b' for 'h' in two colonial-era names
    # Goh Keng Swee: vols 13(parl=0→fb1), 25(parl=1), 27/30/31(parl=2), 33(parl=3)
    ("gob keng swee", 1): "Goh Keng Swee",
    ("gob keng swee", 2): "Goh Keng Swee",
    ("gob keng swee", 3): "Goh Keng Swee",
    # Goh Chew Chua: vols 2/4(parl=1), 12/16(parl=0→fb1)
    ("gob chew chua", 1): "Goh Chew Chua",
    # Colonial-era variant spellings
    # "D.S. Marshall" is David Marshall (Labour Front Chief Minister)
    ("d s marshall", 1): "David Marshall",
    # "G.E.N. Oehlers" is George E.N. Oehlers (Labour Front)
    ("g e n oehlers", 1): "George Oehlers",
    # "Rahamat" is a spelling variant of "Rahmat" (already in Speaker table)
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
    # Speaker table has typo "Gahni" instead of "Ghani"
    ("ahmad khalis bin abdul ghani", 10): "Ahmad Khalis bin Abdul Gahni",
    # "B M M" is an abbreviation of "Bin Masagos Mohamad"
    ("masagos zulkifli b m m", 11): "Masagos Zulkifli Bin Masagos Mohamad",
    ("masagos zulkifli b m m", 12): "Masagos Zulkifli Bin Masagos Mohamad",
    # Extracted name lacks the ", Dr" title suffix present in Speaker.name
    ("lim chun leng, michael", 8): "Lim Chun Leng, Michael, Dr",
    ("lim chun leng, michael", 9): "Lim Chun Leng, Michael, Dr",
    ("lim chun leng, michael", 10): "Lim Chun Leng, Michael, Dr",
    # One-letter spelling difference in Speaker.name
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
    # Apostrophe variant: "Ya'acob" vs "Yaacob" in Speaker table
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
    Note: lone-initial period ("S. Iswaran") is NOT stripped because some Speaker.name
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
    # This does NOT affect the stored speaker_name -- only the lookup search key.
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


def _invert_to_natural(speaker_name: str) -> Optional[str]:
    """Convert 'Surname, Firstname[, TitleSuffix]' to natural 'Firstname Surname' form.
    Returns None if the name is not in inverted format."""
    if ", " not in speaker_name:
        return None
    parts = speaker_name.split(", ")
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
class SpeakerLookups:
    inverted: dict[tuple[str, int], str]
    direct: dict[tuple[str, int], str]
    bin_free: dict[tuple[str, int], str]
    wordset: dict[tuple[frozenset, int, int], str]
    wordset_subset: dict[tuple[frozenset, int], str]
    prefix: dict[tuple[str, int], str]
    surname_fallback: dict[tuple[str, int], str]


def _build_direct_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    counts: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        key = (_period_normalize(speaker.name), speaker.parliament_number)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, speaker.name))
    return {key: canonical for key, canonical in entries if counts[key] == 1}


def _build_bin_free_lookup(
    speakers: list[Speaker],
    direct: dict[tuple[str, int], str],
) -> dict[tuple[str, int], str]:
    counts: dict[tuple[str, int], int] = {}
    entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        key = (_period_normalize(_strip_bin(speaker.name)), speaker.parliament_number)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, speaker.name))
    return {key: canonical for key, canonical in entries if counts[key] == 1 and key not in direct}


def _build_inverted_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    inverted: dict[tuple[str, int], str] = {}
    surname_only_counts: dict[tuple[str, int], int] = {}
    surname_only_entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        parliament = speaker.parliament_number
        if ", " in speaker.name:
            natural_stripped = _invert_to_natural(speaker.name)
            key = (_normalize_for_lookup(natural_stripped), parliament)
            inverted[key] = speaker.name
            surname = speaker.name.split(", ")[0]
            surname_words = surname.split()
            if len(surname_words) >= _MIN_MULTIWORD_SURNAME_LENGTH:
                surname_key = (_normalize_for_lookup(surname), parliament)
                surname_only_counts[surname_key] = surname_only_counts.get(surname_key, 0) + 1
                surname_only_entries.append((surname_key, speaker.name))
        else:
            words = speaker.name.split()
            if len(words) >= _MIN_REARRANGEABLE_WORD_COUNT:
                rearranged = f"{words[-1]} {' '.join(words[1:-1])} {words[0]}"
                if rearranged != speaker.name:
                    rearranged_stripped = strip_title(rearranged).strip()
                    rearranged_key = (_normalize_for_lookup(rearranged_stripped), parliament)
                    if rearranged_key not in inverted:
                        inverted[rearranged_key] = speaker.name
    for surname_key, canonical in surname_only_entries:
        if surname_only_counts.get(surname_key, 0) == 1 and surname_key not in inverted:
            inverted[surname_key] = canonical
    return inverted


def _build_wordset_lookup(speakers: list[Speaker]) -> dict[tuple[frozenset, int, int], str]:
    triples: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = _invert_to_natural(speaker.name)
        if natural:
            triples.append((natural, speaker.name, speaker.parliament_number))
        triples.append((speaker.name, speaker.name, speaker.parliament_number))
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


def _build_wordset_subset_lookup(speakers: list[Speaker]) -> dict[tuple[frozenset, int], str]:
    """Like _build_wordset_lookup but keyed by (frozenset(words), parliament) without word count.
    Only emits entries for names with 3+ words (after title stripping) to avoid false positives.
    Allows matching names where the word count differs, e.g. "Aline Wong" matching "Wong Aline K".
    """
    _MIN_WORDSET_SUBSET_WORDS = 3
    triples: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = _invert_to_natural(speaker.name)
        if natural:
            triples.append((natural, speaker.name, speaker.parliament_number))
        triples.append((speaker.name, speaker.name, speaker.parliament_number))
    counts: dict[tuple[frozenset, int], int] = {}
    entries: list[tuple[tuple[frozenset, int], str]] = []
    for display, canonical_name, parliament in triples:
        words = _period_normalize(strip_title(display)).split()
        if len(words) < _MIN_WORDSET_SUBSET_WORDS:
            continue
        words = [w for w in words if len(w) > 1]
        key = (frozenset(words), parliament)
        counts[key] = counts.get(key, 0) + 1
        entries.append((key, canonical_name))
    wordset_subset: dict[tuple[frozenset, int], str] = {}
    for key, canonical_name in entries:
        if counts[key] == 1 and key not in wordset_subset:
            wordset_subset[key] = canonical_name
    return wordset_subset


def _build_prefix_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    forms: list[tuple[str, str, int]] = []
    for speaker in speakers:
        natural = _invert_to_natural(speaker.name)
        if natural:
            forms.append((natural, speaker.name, speaker.parliament_number))
        forms.append((speaker.name, speaker.name, speaker.parliament_number))
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


def _build_surname_fallback_lookup(speakers: list[Speaker]) -> dict[tuple[str, int], str]:
    surname_counts: dict[tuple[str, int], int] = {}
    surname_entries: list[tuple[tuple[str, int], str]] = []
    for speaker in speakers:
        natural = _invert_to_natural(speaker.name) or speaker.name
        words = _period_normalize(natural).split()
        if not words:
            continue
        last_word = words[-1]
        if len(last_word) < _MIN_SURNAME_LOOKUP_LENGTH:
            continue
        surname_key = (last_word, speaker.parliament_number)
        surname_counts[surname_key] = surname_counts.get(surname_key, 0) + 1
        surname_entries.append((surname_key, speaker.name))
    return {key: canonical for key, canonical in surname_entries if surname_counts[key] == 1}


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


def _parse_name_and_location(text: str) -> tuple[str, Optional[str]]:
    """
    Extract (speaker_name, location_name) from text like:
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
    lookups: SpeakerLookups,
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
        _wss_words = [w for w in _period_normalize(name).split() if len(w) > 1]
        result = lookups.wordset_subset.get((frozenset(_wss_words), parliament))
        if result:
            return result
    return lookups.prefix.get((normalized, parliament))


def resolve_canonical_name(name: str, parliament: int, lookups: SpeakerLookups) -> Optional[str]:
    """
    Try to match a name string to canonical Speaker.name using the full lookup cascade.
    Returns canonical Speaker.name if found, None if no match.
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


def resolve(name: str, parliament: int, lookups: SpeakerLookups) -> Optional[str]:
    return resolve_canonical_name(normalize_name(name), parliament, lookups)


def get_sitting_attendance(sitting: Sitting, lookups: SpeakerLookups) -> list[Attendance]:
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
            records.append(Attendance(
                sitting_id=sitting.id,
                speaker_name=name,
                attendance=is_present,
                location_name=location,
            ))

    return records

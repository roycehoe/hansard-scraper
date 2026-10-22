import re
from typing import Optional

# NOTE: longest first, so a shorter prefix never matches ahead of a longer one.
TITLE_PREFIXES = (
    "The Honourable Mr ", "The Honourable Mrs ", "The Honourable Dr ",
    "The Honourable Miss ", "The Honourable Ms ", "The Honourable Inche ",
    "The Honourable Encik ", "The Honourable ",
    "The Hon. Mr ", "The Hon. Mrs ", "The Hon. Dr ",
    "The Hon. Miss ", "The Hon. Ms ", "The Hon. Inche ",
    "The Hon. ",
    "Assoc. Prof. ", "Assoc Prof ",
    "Er Dr ", "Er ",
    "BG (NS) ", "BG [NS] ", "MG [NS] ", "MG (NS) ",
    "RAdm (NS) ", "RAdm ",
    "BG ", "MG ",
    "Prof. ", "Prof ",
    "Maj. ", "Maj ",
    "Dr. ", "Dr, ", "Mr. ", "Mr, ", "Mi. ", "mr ", "Dr ", "Mr ", "Mrs ", "Miss ", "Ms ", "Mdm ", "Madam ",
    "Inche ", "Encik ", "Sir ", "Dato ", "Tun Dato ", "Tun ",
    "Asst Prof ", "Asst. Prof. ",
    "Tuan Haji ", "Haji ", "Hj. ", "Hj ",
    "Cdre (Res) ", "Cdre ", "[NS] ", "(NS) ",
)

_INVERTED_TITLE_SUFFIXES = frozenset({"Dr", "Mdm", "Mr", "Mrs", "Ms", "Prof", "Assoc Prof", "RAdm", "BG"})

_MIN_INVERTED_TITLE_SUFFIX_PART_COUNT = 3

_SPACE_BETWEEN_PERIODED_INITIALS_PATTERN = r"(?<=[A-Z]\.) (?=[A-Z]\.)"
_MOHD_PERIOD_PATTERN = r"\bMohd\."
_PERIOD_BETWEEN_INITIALS_PATTERN = r"(?<=[A-Z])\.(?=[A-Z])"
_INITIAL_PERIOD_PATTERN = r"([A-Z])\."
_WHITESPACE_RUN_PATTERN = r"\s+"
_BIN_PARTICLE_PATTERN = r"\s+bin(?:te)?\s+"
_MIDDLE_HAJI_PATTERN = r"\s+(?:[Tt]uan\s+)?(?:[Hh]aji|[Hh]j\.?)\s+"
_MOHAMED_VARIANT_PATTERN = r"\bMohamad\b|\bMohammed\b|\bMohammad\b"
_SPACED_INITIALS_PATTERN = r"\b([A-Z])((?:\s+[A-Z])+)\b"


def normalize_name(name: str) -> str:
    # NOTE: a lone-initial period ("S. Iswaran") stays, because some Speaker.name values keep it ("A. Rahim Ishak") and others drop it.
    name = re.sub(_SPACE_BETWEEN_PERIODED_INITIALS_PATTERN, "", name)
    return re.sub(_MOHD_PERIOD_PATTERN, "Mohd", name)


def period_normalize(name: str) -> str:
    normalized = re.sub(_PERIOD_BETWEEN_INITIALS_PATTERN, " ", name)
    normalized = re.sub(_INITIAL_PERIOD_PATTERN, r"\1", normalized)
    normalized = re.sub(_WHITESPACE_RUN_PATTERN, " ", normalized)
    return normalized.strip().lower()


def strip_bin(name: str) -> str:
    return re.sub(_BIN_PARTICLE_PATTERN, " ", name, flags=re.IGNORECASE).strip()


def strip_middle_haji(name: str) -> str:
    return re.sub(_MIDDLE_HAJI_PATTERN, " ", name).strip()


def spelling_normalize(name: str) -> str:
    normalized = re.sub(_MOHAMED_VARIANT_PATTERN, "Mohamed", name)
    normalized = normalized.replace("-", " ")
    normalized = re.sub(
        _SPACED_INITIALS_PATTERN,
        lambda initials_match: initials_match.group(1) + initials_match.group(2).replace(" ", ""),
        normalized,
    )
    return re.sub(_WHITESPACE_RUN_PATTERN, " ", normalized).strip()


def strip_title(text: str) -> str:
    while True:
        for prefix in TITLE_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        else:
            return text


def invert_to_natural(speaker_name: str) -> Optional[str]:
    if ", " not in speaker_name:
        return None
    parts = speaker_name.split(", ")
    if len(parts) >= _MIN_INVERTED_TITLE_SUFFIX_PART_COUNT and parts[-1] in _INVERTED_TITLE_SUFFIXES:
        return strip_title(f"{' '.join(parts[1:-1])} {parts[0]}").strip()
    return strip_title(f"{', '.join(parts[1:])} {parts[0]}").strip()

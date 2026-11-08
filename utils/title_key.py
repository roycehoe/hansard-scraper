import re

_NON_KEY_PATTERN = re.compile(r"[\W_]+")
_LEADING_THE = re.compile(r"^The\s+")
_TRAILING_CHAPTER = re.compile(r"\s*\(Chapter\s+[A-Za-z0-9]+\)\s*$")
_TRAILING_YEAR = re.compile(r"[,\s]*\d{4}\s*$")
_TRAILING_LAW_WORD = re.compile(r"\s*\b(?:Act|Ordinance|Bill)\s*$", re.IGNORECASE)
_AMENDMENT_OR_NUMBER_KEY_PART = re.compile(r"amendment(?!s)(?:no\d+)?|no\d+")


def get_title_key(title: str) -> str:
    return _NON_KEY_PATTERN.sub("", title.lower())


def is_leading_the_title(printed_title: str) -> bool:
    return _LEADING_THE.match(printed_title) is not None


def get_bill_title_key(printed_title: str) -> str:
    without_the = _LEADING_THE.sub("", printed_title)
    without_chapter = _TRAILING_CHAPTER.sub("", without_the)
    without_year = _TRAILING_YEAR.sub("", without_chapter)
    if _TRAILING_LAW_WORD.search(without_year) is None:
        return get_title_key(f"{without_year} Bill")
    return get_title_key(_TRAILING_LAW_WORD.sub(" Bill", without_year))


def get_loose_title_key(title_key: str) -> str:
    return _AMENDMENT_OR_NUMBER_KEY_PART.sub("", title_key)

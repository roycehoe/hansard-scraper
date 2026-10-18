import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from utils.markdown_parser import PROC_TEXT_CLOSE_TAG, PROC_TEXT_OPEN_TAG

HEADLINE_MAX_PARLIAMENT = 11
HEADLINE_GROUP = f"Parliaments 0 to {HEADLINE_MAX_PARLIAMENT}"
LINKED_CATEGORY = "linked"
NAMED_UNLINKED_CATEGORY = "named_unlinked"
ADR_EXCLUDED_CATEGORY = "adr_excluded"
NO_SPEAKER_CATEGORY = "no_speaker"

_ADR_EXCLUDED_SPEAKER_RE = re.compile(r"hon\.? members?", re.IGNORECASE)
_MARKUP_AND_SPACE_RE = re.compile(r"[\s*_\\#|]+")
_PROC_TEXT_TAG_RE = re.compile(re.escape(PROC_TEXT_OPEN_TAG) + "|" + re.escape(PROC_TEXT_CLOSE_TAG))


@dataclass
class ReportTypeFigures:
    report_count: int = 0
    zero_row_report_count: int = 0
    collapse_report_count: int = 0
    collapse_character_count: int = 0
    body_total: int = 0
    category_to_row_count: Counter[str] = field(default_factory=Counter)
    category_to_character_count: Counter[str] = field(default_factory=Counter)


@dataclass
class GroupFigures:
    group: str
    report_count: int
    reports_with_rows_count: int
    category_to_row_count: Counter[str]
    category_to_character_count: Counter[str]
    body_total: int
    body_in_zero_row_reports: int
    report_type_to_figures: dict[str, ReportTypeFigures]


@dataclass
class AttributionFigures:
    groups: list[GroupFigures]


def get_countable_character_count(text: str) -> int:
    return len(_MARKUP_AND_SPACE_RE.sub("", _PROC_TEXT_TAG_RE.sub("", text)))


def is_adr_excluded(speaker: str) -> bool:
    return bool(_ADR_EXCLUDED_SPEAKER_RE.search(speaker)) or speaker.startswith(("(", "_"))


def get_speech_category(speaker: Optional[str], speaker_id: Optional[int]) -> str:
    if speaker is None:
        return NO_SPEAKER_CATEGORY
    if is_adr_excluded(speaker):
        return ADR_EXCLUDED_CATEGORY
    if speaker_id is None:
        return NAMED_UNLINKED_CATEGORY
    return LINKED_CATEGORY


def get_group(parliament_number: int) -> str:
    if parliament_number <= HEADLINE_MAX_PARLIAMENT:
        return HEADLINE_GROUP
    return f"Parliament {parliament_number}"

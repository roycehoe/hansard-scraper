import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass(frozen=True)
class GroupFigures:
    group: str
    report_count: int
    reports_with_rows_count: int
    category_to_row_count: Counter[str]
    category_to_character_count: Counter[str]
    body_total: int
    body_in_zero_row_reports: int
    report_type_to_figures: dict[str, ReportTypeFigures]


def get_countable_character_count(text: str) -> int:
    return len(_MARKUP_AND_SPACE_RE.sub("", _PROC_TEXT_TAG_RE.sub("", text)))


def _is_adr_excluded(speaker: str) -> bool:
    return bool(_ADR_EXCLUDED_SPEAKER_RE.search(speaker)) or speaker.startswith(("(", "_"))


def get_speech_category(speaker: Optional[str], speaker_id: Optional[int]) -> str:
    if speaker is None:
        return NO_SPEAKER_CATEGORY
    if _is_adr_excluded(speaker):
        return ADR_EXCLUDED_CATEGORY
    if speaker_id is None:
        return NAMED_UNLINKED_CATEGORY
    return LINKED_CATEGORY


def get_group(parliament_number: int) -> str:
    if parliament_number <= HEADLINE_MAX_PARLIAMENT:
        return HEADLINE_GROUP
    return f"Parliament {parliament_number}"


def _build_group_json(group_figures: GroupFigures) -> dict[str, object]:
    return {
        "group": group_figures.group,
        "report_count": group_figures.report_count,
        "reports_with_rows_count": group_figures.reports_with_rows_count,
        "zero_row_report_count": group_figures.report_count - group_figures.reports_with_rows_count,
        "linked_row_count": group_figures.category_to_row_count[LINKED_CATEGORY],
        "named_unlinked_row_count": group_figures.category_to_row_count[NAMED_UNLINKED_CATEGORY],
        "adr_excluded_row_count": group_figures.category_to_row_count[ADR_EXCLUDED_CATEGORY],
        "no_speaker_row_count": group_figures.category_to_row_count[NO_SPEAKER_CATEGORY],
        "row_count": sum(group_figures.category_to_row_count.values()),
        "linked_character_count": group_figures.category_to_character_count[LINKED_CATEGORY],
        "body_character_count": group_figures.body_total,
        "body_in_zero_row_reports": group_figures.body_in_zero_row_reports,
        "report_types": [
            {
                "report_type": report_type,
                "report_count": figures.report_count,
                "zero_row_report_count": figures.zero_row_report_count,
                "collapse_report_count": figures.collapse_report_count,
                "collapse_character_count": figures.collapse_character_count,
                "body_total": figures.body_total,
                "category_to_row_count": dict(figures.category_to_row_count),
                "category_to_character_count": dict(figures.category_to_character_count),
            }
            for report_type, figures in sorted(group_figures.report_type_to_figures.items())
        ],
    }


def build_attribution_figures_json(attribution_figures: list[GroupFigures], measured_at: datetime) -> dict[str, object]:
    return {
        "measured_at": measured_at.isoformat(),
        "groups": [_build_group_json(group_figures) for group_figures in attribution_figures],
    }

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.hansard_website_response import HansardWebsiteResponse
from database.report import Report
from utils.markdown_header import SITTING_NUMBER_FIELD, get_header_number
from utils.markdown_parser import get_cleaned_report_markdown
from utils.text import fix_mojibake

_BRACKET_PATTERN = r"\(([^)]*)\)"
_HTML_TAG_PATTERN = r"<[^>]+>"
_TITLE_PART_SEPARATOR = ","
_SITTING_DATE_FORMAT = "%d-%m-%Y"


@dataclass
class ReportHeader:
    title: str
    subtitle: Optional[str] = None


def _replace_bracket(match: re.Match) -> str:
    if match.group(1).isupper():
        return match.group(0)
    return ""


def _get_collapsed_title(title: str) -> str:
    parts = {part.strip() for part in title.split(_TITLE_PART_SEPARATOR)}
    if len(parts) == 1:
        return parts.pop()
    return title


def build_report_header(raw_title: str) -> ReportHeader:
    raw_title = re.sub(_HTML_TAG_PATTERN, " ", raw_title.replace("\n", " ")).strip()
    if raw_title[-1] != ")":
        return ReportHeader(title=_get_collapsed_title(raw_title))

    contents = [
        match.group(1)
        for match in re.finditer(_BRACKET_PATTERN, raw_title)
        if not match.group(1).isupper()
    ]
    title = _get_collapsed_title(re.sub(_BRACKET_PATTERN, _replace_bracket, raw_title).strip())
    if not contents:
        return ReportHeader(title=title)
    return ReportHeader(title=title, subtitle=f"({contents[-1]})")


def _get_sitting_number(raw_sitting_number: Optional[str], markdown_content: Optional[str]) -> Optional[int]:
    if raw_sitting_number is not None:
        return int(raw_sitting_number)
    if markdown_content is None:
        return None
    return get_header_number(markdown_content, SITTING_NUMBER_FIELD)


def build_report(hansard_website_response: HansardWebsiteResponse) -> Report:
    sitting_date = datetime.strptime(hansard_website_response.sitting_date, _SITTING_DATE_FORMAT)
    raw_title = fix_mojibake(hansard_website_response.title)
    db_report_header = build_report_header(raw_title)
    markdown_content = (
        get_cleaned_report_markdown(hansard_website_response.content, hansard_website_response.report_version)
        if hansard_website_response.content is not None
        else None
    )

    return Report(
        volumeNo=int(hansard_website_response.volume_number),
        parlNo=int(hansard_website_response.parliament_number),
        sittingNo=_get_sitting_number(hansard_website_response.sitting_number, markdown_content),
        sittingDate=sitting_date,
        sno=int(hansard_website_response.speech_number),
        original_title=raw_title,
        title=db_report_header.title,
        subtitle=db_report_header.subtitle,
        reportId=hansard_website_response.report_id,
        reportType=hansard_website_response.report_type,
        content=hansard_website_response.content,
        markdown_content=markdown_content,
        htmlFileName=hansard_website_response.html_file_name,
        reportVersion=hansard_website_response.report_version,
    )

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.hansard_website_response import HansardWebsiteResponse
from database.report import Report
from utils.markdown_header import SITTING_NUMBER_FIELD, get_header_number
from utils.markdown_parser import get_cleaned_report_markdown
from utils.text import fix_mojibake

_HTML_TAG_PATTERN = r"<[^>]+>"
_TITLE_PART_SEPARATOR = ","
_OPENING_BRACKET = "("
_CLOSING_BRACKET = ")"
_SITTING_DATE_FORMAT = "%d-%m-%Y"


@dataclass
class ReportHeader:
    title: str
    subtitle: Optional[str] = None


def _get_trailing_bracket_start(title: str) -> Optional[int]:
    depth = 0
    for index in range(len(title) - 1, -1, -1):
        if title[index] == _CLOSING_BRACKET:
            depth += 1
        if title[index] == _OPENING_BRACKET:
            depth -= 1
        if depth == 0:
            return index
    return None


def _split_off_subtitle(title: str) -> ReportHeader:
    title = title.strip()
    if not title.endswith(_CLOSING_BRACKET):
        return ReportHeader(title=title)
    bracket_start = _get_trailing_bracket_start(title)
    if bracket_start is None:
        return ReportHeader(title=title)
    if not any(character.islower() for character in title[bracket_start + 1:-1]):
        return ReportHeader(title=title)
    return ReportHeader(title=title[:bracket_start].strip(), subtitle=title[bracket_start:])


def _split_title_parts(title: str) -> list[str]:
    parts = [""]
    depth = 0
    for character in title:
        if character == _TITLE_PART_SEPARATOR and depth == 0:
            parts.append("")
            continue
        if character == _OPENING_BRACKET:
            depth += 1
        if character == _CLOSING_BRACKET:
            depth -= 1
        parts[-1] += character
    return parts


def build_report_header(raw_title: str) -> ReportHeader:
    raw_title = re.sub(_HTML_TAG_PATTERN, " ", raw_title.replace("\n", " ")).strip()
    part_headers = [_split_off_subtitle(part) for part in _split_title_parts(raw_title)]
    part_titles = {part_header.title for part_header in part_headers}
    if len(part_titles) != 1:
        return _split_off_subtitle(raw_title)

    subtitles = [part_header.subtitle for part_header in part_headers if part_header.subtitle is not None]
    if not subtitles:
        return ReportHeader(title=part_titles.pop())
    return ReportHeader(title=part_titles.pop(), subtitle=subtitles[-1])


def _get_sitting_number(raw_sitting_number: Optional[str], markdown_content: Optional[str]) -> Optional[int]:
    if raw_sitting_number is not None:
        return int(raw_sitting_number)
    if markdown_content is None:
        return None
    return get_header_number(markdown_content, SITTING_NUMBER_FIELD)


def build_report(hansard_website_response: HansardWebsiteResponse) -> Report:
    sitting_date = datetime.strptime(hansard_website_response.sitting_date, _SITTING_DATE_FORMAT)
    raw_title = fix_mojibake(hansard_website_response.title)
    report_header = build_report_header(raw_title)
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
        title=report_header.title,
        subtitle=report_header.subtitle,
        reportId=hansard_website_response.report_id,
        reportType=hansard_website_response.report_type,
        content=hansard_website_response.content,
        markdown_content=markdown_content,
        htmlFileName=hansard_website_response.html_file_name,
        reportVersion=hansard_website_response.report_version,
    )

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.hansard_website_response import HansardWebsiteResponse
from database.report import Report
from utils.markdown_parser import get_cleaned_report_markdown
from utils.text import fix_mojibake


@dataclass
class ReportHeader:
    title: str
    subtitle: Optional[str] = None


def _get_db_report_header(raw_title: str) -> ReportHeader:
    raw_title = raw_title.replace("\n", " ")
    if raw_title[-1] != ")":
        return ReportHeader(title=raw_title)

    subtitle = None

    def _get_bracket_replacement(bracket_match: re.Match) -> str:
        nonlocal subtitle
        content = bracket_match.group(1)
        if content.isupper():
            return bracket_match.group(0)
        subtitle = f"({content})"
        return ""

    title = re.sub(r"\(([^)]*)\)", _get_bracket_replacement, raw_title).strip()
    return ReportHeader(title=title, subtitle=subtitle)


def build_report(hansard_website_response: HansardWebsiteResponse) -> Report:
    sitting_date = datetime.strptime(hansard_website_response.sitting_date, "%d-%m-%Y")
    raw_title = fix_mojibake(hansard_website_response.title)
    db_report_header = _get_db_report_header(raw_title)

    return Report(
        volumeNo=int(hansard_website_response.volume_number),
        parlNo=int(hansard_website_response.parliament_number),
        sittingNo=(
            int(hansard_website_response.sitting_number)
            if hansard_website_response.sitting_number is not None
            else None
        ),
        sittingDate=sitting_date,
        sno=int(hansard_website_response.speech_number),
        original_title=raw_title,
        title=db_report_header.title,
        subtitle=db_report_header.subtitle,
        reportId=hansard_website_response.report_id,
        reportType=hansard_website_response.report_type,
        content=hansard_website_response.content,
        markdown_content=(
            get_cleaned_report_markdown(hansard_website_response.content)
            if hansard_website_response.content is not None
            else None
        ),
        htmlFileName=hansard_website_response.html_file_name,
        reportVersion=hansard_website_response.report_version,
    )

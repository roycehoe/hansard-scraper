import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.handsard_website_response import HandsardWebsiteResponse
from database.report import Report
from utils.markdown_parser import get_cleaned_handsard_markdown


def _fix_mojibake(s: str) -> str:
    """Fix Windows-1252 mojibake in stored titles (e.g. â€™ → ', âˆ' → −)."""
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


@dataclass
class ReportHeader:
    title: str
    subtitle: Optional[str] = None


def _get_db_report_header(raw_title: str) -> ReportHeader:
    raw_title = raw_title.replace("\n", " ")
    if raw_title[-1] != ")":
        return ReportHeader(title=raw_title)

    subtitle = None

    def _handle_bracket(m: re.Match) -> str:
        nonlocal subtitle
        content = m.group(1)
        if content.isupper():
            return m.group(0)
        subtitle = f"({content})"
        return ""

    title = re.sub(r"\(([^)]*)\)", _handle_bracket, raw_title).strip()
    return ReportHeader(title=title, subtitle=subtitle)


def get_db_report_in(handsard_website_response: HandsardWebsiteResponse) -> Report:
    sitting_date = datetime.strptime(handsard_website_response.sitting_date, "%d-%m-%Y")
    raw_title = _fix_mojibake(handsard_website_response.title)
    db_report_header = _get_db_report_header(raw_title)

    return Report(
        volumeNo=int(handsard_website_response.volume_number),
        parlNo=int(handsard_website_response.parliament_number),
        sittingNo=(
            int(handsard_website_response.sitting_number)
            if handsard_website_response.sitting_number is not None
            else None
        ),
        sittingDate=sitting_date,
        sno=int(handsard_website_response.speech_number),
        original_title=raw_title,
        title=db_report_header.title,
        subtitle=db_report_header.subtitle,
        reportId=handsard_website_response.report_id,
        reportType=handsard_website_response.report_type,
        content=handsard_website_response.content,
        markdown_content=(
            get_cleaned_handsard_markdown(handsard_website_response.content)
            if handsard_website_response.content is not None
            else None
        ),
        htmlFileName=handsard_website_response.html_file_name,
        reportVersion=handsard_website_response.report_version,
    )

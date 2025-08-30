import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.report import HandsardWebsiteResponse, Report
from gateway.handsard_topic import get_handsard_topic_response
from schemas import HandsardSearchResult
from utils.markdown_parser import get_cleaned_handsard_markdown


@dataclass
class ReportHeader:
    title: str
    subtitle: Optional[str] = None


def _has_no_subtitle(raw_title: str) -> bool:
    return raw_title[-1] != ")"


def _get_raw_db_report_in(handsard_search_result: HandsardSearchResult) -> Report:
    sitting_date = datetime.strptime(handsard_search_result.sittingDate, "%d-%m-%Y")
    return Report(
        volumeNo=int(handsard_search_result.volumeNo),
        parlNo=int(handsard_search_result.parlNo),
        sittingNo=(
            handsard_search_result.sittingNo
            if handsard_search_result.sittingNo is None
            else int(handsard_search_result.sittingNo)
        ),
        sittingDate=sitting_date,
        sno=int(handsard_search_result.sno),
        title=re.sub(r"[\r\n]+", " ", handsard_search_result.title).strip(),
        subtitle=(
            handsard_search_result.subtitle
            if handsard_search_result.subtitle is None
            else re.sub(r"[\r\n]+", " ", handsard_search_result.subtitle).strip()
        ),
        reportId=handsard_search_result.reportId,
        reportType=handsard_search_result.reportType,
        htmlFileName=(
            handsard_search_result.htmlFileName
            if handsard_search_result.htmlFileName is None
            else handsard_search_result.htmlFileName
        ),
        reportVersion=handsard_search_result.reportVersion,
    )


def _get_db_report_header(raw_title: str) -> ReportHeader:
    if _has_no_subtitle(raw_title):
        return ReportHeader(title=raw_title)

    title = ""
    subtitle = None
    in_brackets_content = ""
    is_in_brackets = False

    for letter in raw_title:
        if letter == "(":
            is_in_brackets = True
            continue

        if is_in_brackets:
            if letter != ")":
                in_brackets_content += letter
                continue
            if not in_brackets_content.isupper():
                subtitle = f"({in_brackets_content})"
            else:
                title += f"({in_brackets_content})"

            in_brackets_content = ""
            is_in_brackets = False
            continue

        title += letter

    if subtitle is None:
        return ReportHeader(title=title.strip())
    return ReportHeader(title=title.strip(), subtitle=subtitle.strip())


def get_db_report_in(handsard_website_response: HandsardWebsiteResponse) -> Report:
    sitting_date = datetime.strptime(handsard_website_response.sitting_date, "%d-%m-%Y")
    db_report_header = _get_db_report_header(handsard_website_response.title)

    return Report(
        volumeNo=int(handsard_website_response.volume_number),
        parlNo=int(handsard_website_response.parliament_number),
        sittingNo=(
            handsard_website_response.sitting_number
            if handsard_website_response.sitting_number is None
            else int(handsard_website_response.sitting_number)
        ),
        sittingDate=sitting_date,
        sno=int(handsard_website_response.speech_number),
        title=db_report_header.title,
        subtitle=db_report_header.subtitle,
        reportId=handsard_website_response.report_id,
        reportType=handsard_website_response.report_type,
        markdown_content=(
            get_cleaned_handsard_markdown(handsard_website_response.content)
            if handsard_website_response.content is not None
            else None
        ),
        htmlFileName=(
            handsard_website_response.html_file_name
            if handsard_website_response.html_file_name is None
            else handsard_website_response.html_file_name
        ),
        reportVersion=handsard_website_response.report_version,
    )

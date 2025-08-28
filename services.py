import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.report import Report
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
        title=re.sub("\n", " ", handsard_search_result.title),
        subtitle=(
            handsard_search_result.subtitle
            if handsard_search_result.subtitle is None
            else re.sub("\n", " ", handsard_search_result.subtitle)
        ),
        reportId=handsard_search_result.reportId,
        reportType=handsard_search_result.reportType,
        columnStart=(
            handsard_search_result.columnStart
            if handsard_search_result.columnStart is None
            else handsard_search_result.columnStart
        ),
        columnEnd=(
            handsard_search_result.columnEnd
            if handsard_search_result.columnEnd is None
            else handsard_search_result.columnEnd
        ),
        htmlFileName=(
            handsard_search_result.htmlFileName
            if handsard_search_result.htmlFileName is None
            else handsard_search_result.htmlFileName
        ),
        reportVersion=handsard_search_result.reportVersion,
    )


def _get_db_report_content(report: Report) -> Optional[str]:
    try:
        response = get_handsard_topic_response(
            report.html_file_name
            if report.html_file_name is not None
            else report.report_id
        )
    except Exception:  # 2 topics return no response
        return None
    html_content = response.get("htmlContent")
    if html_content is None:
        return None
    return html_content.replace("\x00", "\ufffd")


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

    return ReportHeader(title=title, subtitle=subtitle)


def get_db_report_in(handsard_search_result: HandsardSearchResult) -> Report:
    report = _get_raw_db_report_in(handsard_search_result)

    report.content = _get_db_report_content(report)
    if report.content is not None:
        report.markdown_content = get_cleaned_handsard_markdown(report.content)

    if report.subtitle is not None:
        return report

    db_report_header = _get_db_report_header(report.title)
    report.title = db_report_header.title
    report.subtitle = db_report_header.subtitle

    return report

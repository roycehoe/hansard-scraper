from datetime import datetime
from typing import Optional

from database.report import Report
from handsard_topic import get_handsard_topic_response
from schemas import HandsardSearchResult


def get_db_report_in(handsard_search_result: HandsardSearchResult) -> Report:
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
        title=handsard_search_result.title,
        subtitle=(
            handsard_search_result.subtitle
            if handsard_search_result.subtitle is None
            else handsard_search_result.subtitle
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
        content=None,
        reportVersion=handsard_search_result.reportVersion,
    )


def get_db_report_content_in(report: Report) -> Optional[str]:
    response = get_handsard_topic_response(
        report.html_file_name if report.html_file_name is not None else report.report_id
    )
    html_content = response.get("htmlContent")
    if html_content is None:
        return None
    return html_content.replace("\x00", "\ufffd")

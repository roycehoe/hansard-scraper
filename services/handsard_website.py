import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.report import HandsardWebsiteResponse, Report
from gateway.handsard_topic import get_handsard_topic_response
from schemas import HandsardSearchResult
from utils.markdown_parser import get_cleaned_handsard_markdown


def get_handsard_website_report_content(
    handsard_search_result: HandsardSearchResult,
) -> Optional[str]:
    try:
        response = get_handsard_topic_response(
            handsard_search_result.htmlFileName
            if handsard_search_result.htmlFileName is not None
            else handsard_search_result.reportId
        )
    except Exception:  # 2 topics return no response
        return None
    html_content = response.get("htmlContent")
    if html_content is None:
        return None
    return html_content.replace("\x00", "\ufffd")


def get_handsard_website_result_in(
    handsard_search_result: HandsardSearchResult,
) -> HandsardWebsiteResponse:
    return HandsardWebsiteResponse(
        volumeNo=handsard_search_result.volumeNo,
        parlNo=handsard_search_result.parlNo,
        sittingNo=handsard_search_result.sittingNo,
        sittingDate=handsard_search_result.sittingDate,
        sno=handsard_search_result.sno,
        title=handsard_search_result.title,
        subtitle=handsard_search_result.subtitle,
        reportId=handsard_search_result.reportId,
        reportType=handsard_search_result.reportType,
        htmlFileName=handsard_search_result.htmlFileName,
        content=get_handsard_website_report_content(handsard_search_result),
        reportVersion=handsard_search_result.reportVersion,
    )

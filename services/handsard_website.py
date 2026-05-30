from typing import Optional

from database.handsard_website_response import HandsardWebsiteResponse
from gateway.handsard_topic import get_handsard_topic_response
from schemas.handsard_search_result import HandsardSearchResult


def _get_handsard_website_report_content(
    handsard_search_result: HandsardSearchResult,
) -> Optional[str]:
    try:
        response = get_handsard_topic_response(
            handsard_search_result.htmlFileName or handsard_search_result.reportId
        )
    except Exception:  # 2 topics return no response
        return None
    html_content = response.get("htmlContent")
    if html_content is None:
        return None
    return html_content.replace("\x00", "\ufffd")


def build_handsard_website_response(
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
        content=_get_handsard_website_report_content(handsard_search_result),
        reportVersion=handsard_search_result.reportVersion,
    )

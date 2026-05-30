from typing import Optional

from database.handsard_website_response import HandsardWebsiteResponse
from exceptions import HansardGatewayError
from gateway.handsard_topic import get_handsard_topic_response
from logs import logger
from schemas.handsard_search_result import HandsardSearchResult


def _get_handsard_website_report_content(
    handsard_search_result: HandsardSearchResult,
) -> Optional[str]:
    try:
        response = get_handsard_topic_response(
            handsard_search_result.html_file_name or handsard_search_result.report_id
        )
    except HansardGatewayError as e:
        logger.warning(f"No content for {handsard_search_result.report_id}: {e}")
        return None
    html_content = response.get("htmlContent")
    if html_content is None:
        return None
    return html_content.replace("\x00", "\ufffd")


def build_handsard_website_response(
    handsard_search_result: HandsardSearchResult,
) -> HandsardWebsiteResponse:
    return HandsardWebsiteResponse(
        volumeNo=handsard_search_result.volume_no,
        parlNo=handsard_search_result.parl_no,
        sittingNo=handsard_search_result.sitting_no,
        sittingDate=handsard_search_result.sitting_date,
        sno=handsard_search_result.sno,
        title=handsard_search_result.title,
        subtitle=handsard_search_result.subtitle,
        reportId=handsard_search_result.report_id,
        reportType=handsard_search_result.report_type,
        htmlFileName=handsard_search_result.html_file_name,
        content=_get_handsard_website_report_content(handsard_search_result),
        reportVersion=handsard_search_result.report_version,
    )

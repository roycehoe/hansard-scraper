from typing import Optional

from database.hansard_website_response import HansardWebsiteResponse
from enums import ReportVersion
from schemas.hansard_search_result import HansardSearchResult
from schemas.hansard_topic_response import HansardTopicResponse

_NEWER_SYSTEM_ID_SUFFIX = "#"
_NUL_REPLACEMENT = "�"


def get_topic_id(report_id: str, html_file_name: Optional[str], report_version: str) -> str:
    if report_version == ReportVersion.SPRS3:
        return report_id.rstrip(_NEWER_SYSTEM_ID_SUFFIX)
    return html_file_name or report_id


def get_topic_html_content(hansard_topic_response: HansardTopicResponse, report_version: str) -> Optional[str]:
    if report_version == ReportVersion.SPRS3:
        if hansard_topic_response.result_html is None:
            return None
        html_content = hansard_topic_response.result_html.content
    else:
        html_content = hansard_topic_response.html_content
    if html_content is None:
        return None
    return html_content.replace("\x00", _NUL_REPLACEMENT)


def build_hansard_website_response(
    hansard_search_result: HansardSearchResult,
    content: Optional[str],
) -> HansardWebsiteResponse:
    return HansardWebsiteResponse(
        volumeNo=hansard_search_result.volume_no,
        parlNo=hansard_search_result.parl_no,
        sittingNo=hansard_search_result.sitting_no,
        sittingDate=hansard_search_result.sitting_date,
        sno=hansard_search_result.sno,
        title=hansard_search_result.title,
        subtitle=hansard_search_result.subtitle,
        reportId=hansard_search_result.report_id,
        reportType=hansard_search_result.report_type,
        htmlFileName=hansard_search_result.html_file_name,
        content=content,
        reportVersion=hansard_search_result.report_version,
    )

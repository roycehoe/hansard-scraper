from typing import Optional

from database.hansard_website_response import HansardWebsiteResponse
from schemas.hansard_search_result import HansardSearchResult


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

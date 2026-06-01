from typing import Optional

from database.handsard_website_response import HandsardWebsiteResponse
from schemas.handsard_search_result import HandsardSearchResult


def build_handsard_website_response(
    handsard_search_result: HandsardSearchResult,
    content: Optional[str],
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
        content=content,
        reportVersion=handsard_search_result.report_version,
    )

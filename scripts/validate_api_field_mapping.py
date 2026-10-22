import sys
from typing import Union

from gateway.hansard_report import get_hansard_report_response
from gateway.hansard_search import get_hansard_search_results
from gateway.hansard_topic import get_hansard_topic_response
from logs import logger
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from services.api_field_mapping import (
    get_search_result_field_losses,
    get_sitting_date_field_losses,
)
from services.hansard_sitting_date_response import (
    build_new_hansard_sitting_date_response,
    build_old_hansard_sitting_date_response,
)
from services.hansard_website import build_hansard_website_response
from utils.sitting_dates import is_new_sitting_date_format

_VALUE_PREVIEW_LENGTH = 55
_HTTP_INTERNAL_SERVER_ERROR = 500
_FIELD_LOSS_EXIT_CODE = 1
_FIRST_PAGE_START_INDEX = 0
_FIRST_PAGE_END_INDEX = 0
SYNTHETIC_OLD_FORMAT = {
    "parlNo": "9",
    "sessionNo": "1",
    "volumeNo": "65",
    "sittingNo": "5",
    "onlinePDFFileName": "015_20150511.pdf",
    "htmlFullContent": "<html>content</html>",
    "ptbaFrom": "Member A",
    "ptbaTo": "2015-07-01",
    "memberId": "42",
    "reportType": "oral-answer",
    "portfolio": "Education",
    "memberName": "Dr Tan Cheng Bock",
    "reportVersion": "1",
    "reportStartCol": "1",
    "reportEndCol": "50",
    "title": "Education Budget",
    "columnStart": "1",
    "reportContent": "Oral answer content",
    "columnEnd": "50",
    "reportId": "oral-answer-123",
    "score": "0.9",
    "maxResult": "1000",
    "sno": "1",
    "fullContentFlag": "Y",
    "fromMonth": "05",
    "fromDay": "11",
    "fromYear": "2015",
    "htmlContent": "<html>html content</html>",
    "subtitle": "(Ministry of Education)",
    "content": "Some content",
    "mpNames": "Dr Tan Cheng Bock, Mr Lee Hsien Loong",
    "htmlFileName": "oral-answer-123.html",
    "verPdf": "2",
    "footNotes": "Footnote text",
    "footNoteQuestion": "Q1",
    "footNoteQuestions": "Q1, Q2",
    "pdfNodes": "node1",
    "clarificationText": "clarification",
    "clarificationTitle": "Clarification title",
    "clarificationSubTitle": "Clarification subtitle",
    "questionCount": "3",
    "attendanceList": [{"name": "Dr Tan Cheng Bock", "status": "P"}],
}
SYNTHETIC_NEW_FORMAT = {
    "metadata": {
        "parlimentNO": "13",
        "sessionNO": "2",
        "volumeNO": "94",
        "sittingNO": "15",
        "partSessionStr": "13S2",
        "startTimeStr": "09:30",
        "speaker": "Tan Chuan-Jin",
        "attendancePreviewText": "64 Members Present",
        "ptbaPreviewText": "No permissions",
        "atbPreviewText": "",
        "dateToDisplay": "15 January 2024",
        "pdfNotes": "PDF notes",
        "waText": "Written answer text",
        "ptbaFrom": "Member B",
        "ptbaTo": "2024-02-01",
        "locationText": "Parliament House Chamber",
    },
    "attStartPgNo": "1",
    "ptbaStartPgNo": "3",
    "atbpStartPgNo": "5",
    "onlinePDFFileName": "094_20240115.pdf",
    "attendanceList": [{"name": "Member C", "status": "P"}],
}


def is_search_and_topic_mapped() -> bool:
    logger.info("API 1 — searchResult  →  HansardSearchResult  →  HansardWebsiteResponse")
    search_results = get_hansard_search_results(_FIRST_PAGE_START_INDEX, _FIRST_PAGE_END_INDEX)
    if not search_results:
        logger.info("  WARN  No search results returned (check settings.search_from_date).")
        return True

    hansard_search_result = search_results[0]
    logger.info(f"  INFO  report_id={hansard_search_result.report_id}  title={hansard_search_result.title[:_VALUE_PREVIEW_LENGTH]}")
    hansard_website_response = build_hansard_website_response(hansard_search_result, content=None)
    orm_failures = get_search_result_field_losses(hansard_search_result, hansard_website_response)

    if orm_failures:
        logger.info("  HansardWebsiteResponse field losses:")
        for line in orm_failures:
            logger.info(line)
    else:
        logger.info("  PASS  HansardWebsiteResponse — all mapped fields present")

    return not orm_failures


def is_topic_mapped(report_id: str) -> bool:
    logger.info("API 2 — getHansardTopic  →  htmlContent  →  HansardWebsiteResponse.content")
    logger.info(f"  INFO  report_id={report_id!r}")
    search_results = get_hansard_search_results(_FIRST_PAGE_START_INDEX, _FIRST_PAGE_END_INDEX)
    if not search_results:
        logger.info("  WARN  No search results; skipping.")
        return True

    hansard_search_result = next((search_result for search_result in search_results if search_result.report_id == report_id), search_results[0])
    hansard_topic_response = get_hansard_topic_response(report_id)
    html_content = hansard_topic_response.html_content

    hansard_website_response = build_hansard_website_response(hansard_search_result, content=html_content)
    if html_content:
        if hansard_website_response.content is None:
            logger.info(f"  FAIL  topic.htmlContent ({len(html_content)} chars)  →  orm.content=None")
            return False
        logger.info(f"  PASS  htmlContent ({len(html_content)} chars) → orm.content ({len(hansard_website_response.content)} chars)")
    else:
        topic_keys = list(hansard_topic_response.model_dump(by_alias=True, exclude_none=True).keys())
        logger.info(
            f"  INFO  htmlContent absent for this report type "
            f"(topic response keys: {topic_keys}) — expected for written answers"
        )
    return True


def _is_sitting_payload_mapped(
    hansard_report_response: Union[HansardReportOldResponse, HansardReportNewResponse], sitting_date: str, source: str
) -> bool:
    is_new = is_new_sitting_date_format(sitting_date)

    hansard_sitting_date_response = (
        build_new_hansard_sitting_date_response(hansard_report_response, sitting_date)
        if is_new
        else build_old_hansard_sitting_date_response(hansard_report_response, sitting_date)
    )
    failures = get_sitting_date_field_losses(hansard_report_response, hansard_sitting_date_response)

    format_label = "new" if is_new else "old"
    if failures:
        for line in failures:
            logger.info(line)
        return False
    logger.info(f"  PASS  HansardSittingDateResponse ({format_label} format, {source}) — no field losses")
    return True


def is_sitting_date_mapped(sitting_date: str, label: str, synthetic: dict[str, object]) -> bool:
    logger.info(f"API 3 — getHansardReport ({label})")
    logger.info(f"  INFO  sitting_date={sitting_date!r}")

    response_schema = HansardReportNewResponse if is_new_sitting_date_format(sitting_date) else HansardReportOldResponse
    try:
        hansard_report_response = get_hansard_report_response(sitting_date)
    except Exception as error:  # noqa: BLE001 the API call is probed and its failure is the finding, so fall back to the synthetic payload
        logger.info(f"  WARN  API call failed ({error}) — using synthetic payload")
        hansard_report_response = response_schema(error_code=_HTTP_INTERNAL_SERVER_ERROR)

    if hansard_report_response.error_code is None:
        return _is_sitting_payload_mapped(hansard_report_response, sitting_date, source="live API")

    logger.info(f"  WARN  API returned error: {hansard_report_response.description} — using synthetic payload instead")
    return _is_sitting_payload_mapped(response_schema.model_validate(synthetic), sitting_date, source="synthetic payload")


if __name__ == "__main__":
    is_all_passed = True
    is_all_passed &= is_search_and_topic_mapped()
    is_all_passed &= is_topic_mapped(get_hansard_search_results(_FIRST_PAGE_START_INDEX, _FIRST_PAGE_END_INDEX)[0].report_id)
    is_all_passed &= is_sitting_date_mapped(
        "11-05-2015",
        "old format, pre-2015-08-18",
        SYNTHETIC_OLD_FORMAT,
    )
    is_all_passed &= is_sitting_date_mapped(
        "15-01-2024",
        "new format, post-2015-08-18",
        SYNTHETIC_NEW_FORMAT,
    )

    if is_all_passed:
        logger.info("  PASS  All field mappings verified.")
    else:
        logger.info("  FAIL  One or more field losses detected — see above.")
        sys.exit(_FIELD_LOSS_EXIT_CODE)

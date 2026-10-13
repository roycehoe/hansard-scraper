"""Validates that every non-None field in a raw API response survives parsing into the ORM.

For live APIs that respond: calls the real endpoint and verifies field coverage.
For endpoints that are unavailable: falls back to a synthetic payload that exercises
every mapped field, which is a stricter test than hitting an endpoint that may omit fields.

No data is written to the database.

Usage:
    PYTHONPATH=. poetry run python scripts/validate_api_field_mapping.py
"""

import sys
from typing import Any, Union

from gateway.hansard_report import get_hansard_report_response
from gateway.hansard_search import get_hansard_search_results
from gateway.hansard_topic import get_hansard_topic_response
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from services.hansard_sitting_date_response import (
    build_new_hansard_sitting_date_response,
    build_old_hansard_sitting_date_response,
)
from services.hansard_website import build_hansard_website_response
from utils.sitting_dates import is_new_sitting_date_format

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"
INFO = "\033[34mINFO\033[0m"

_VALUE_PREVIEW_LENGTH = 55
_HTTP_INTERNAL_SERVER_ERROR = 500

# Synthetic payload for old-format sitting dates (pre-18 Aug 2015).
# Covers every field mapped by build_old_hansard_sitting_date_response.
_SYNTHETIC_OLD_FORMAT = {
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

# Synthetic payload for new-format sitting dates (18 Aug 2015 onwards).
# Covers every field mapped by build_new_hansard_sitting_date_response.
_SYNTHETIC_NEW_FORMAT = {
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


def _get_orm_field_to_value(orm_object) -> dict[str, Any]:
    return {key: value for key, value in vars(orm_object).items() if not key.startswith("_")}


def _section(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print("─" * 64)


def validate_search_and_topic() -> bool:
    _section("API 1 — searchResult  →  HansardSearchResult  →  HansardWebsiteResponse")
    search_results = get_hansard_search_results(0, 0)
    if not search_results:
        print(f"  {WARN}  No search results returned (check settings.search_from_date).")
        return True

    hansard_search_result = search_results[0]
    raw = hansard_search_result.model_dump(by_alias=True)
    print(f"  {INFO}  report_id={hansard_search_result.report_id}  title={hansard_search_result.title[:_VALUE_PREVIEW_LENGTH]}")

    # ORM build: check the explicitly mapped fields
    hansard_website_response = build_hansard_website_response(hansard_search_result, content=None)
    orm_field_to_value = _get_orm_field_to_value(hansard_website_response)
    raw_key_to_orm_field = {
        "volumeNo": "volume_number",
        "parlNo": "parliament_number",
        "sittingNo": "sitting_number",
        "sittingDate": "sitting_date",
        "sno": "speech_number",
        "title": "title",
        "subtitle": "subtitle",
        "reportId": "report_id",
        "reportType": "report_type",
        "htmlFileName": "html_file_name",
        "reportVersion": "report_version",
    }
    orm_failures = []
    for raw_key, orm_field in raw_key_to_orm_field.items():
        raw_value = raw.get(raw_key)
        if raw_value is None or raw_value == "":
            continue
        orm_value = orm_field_to_value.get(orm_field)
        if orm_value is None:
            orm_failures.append(
                f"  {FAIL}  raw[{raw_key!r}]={str(raw_value)[:_VALUE_PREVIEW_LENGTH]!r}  →  HansardWebsiteResponse.{orm_field}=None"
            )

    if orm_failures:
        print("\n  HansardWebsiteResponse field losses:")
        for line in orm_failures:
            print(line)
    else:
        print(f"  {PASS}  HansardWebsiteResponse — all mapped fields present")

    return not orm_failures


def validate_topic(report_id: str) -> bool:
    _section("API 2 — getHansardTopic  →  htmlContent  →  HansardWebsiteResponse.content")
    print(f"  {INFO}  report_id={report_id!r}")
    search_results = get_hansard_search_results(0, 0)
    if not search_results:
        print(f"  {WARN}  No search results; skipping.")
        return True

    hansard_search_result = next((search_result for search_result in search_results if search_result.report_id == report_id), search_results[0])
    hansard_topic_response = get_hansard_topic_response(report_id)
    html_content = hansard_topic_response.html_content

    hansard_website_response = build_hansard_website_response(hansard_search_result, content=html_content)
    if html_content:
        if hansard_website_response.content is None:
            print(f"  {FAIL}  topic.htmlContent ({len(html_content)} chars)  →  orm.content=None")
            return False
        print(f"  {PASS}  htmlContent ({len(html_content)} chars) → orm.content ({len(hansard_website_response.content)} chars)")
    else:
        topic_keys = list(hansard_topic_response.model_dump(by_alias=True, exclude_none=True).keys())
        print(
            f"  {INFO}  htmlContent absent for this report type "
            f"(topic response keys: {topic_keys}) — expected for written answers"
        )
    return True


def _validate_sitting_payload(
    hansard_report_response: Union[HansardReportOldResponse, HansardReportNewResponse], sitting_date: str, source: str
) -> bool:
    is_new = is_new_sitting_date_format(sitting_date)
    raw = hansard_report_response.model_dump(by_alias=True)

    if hansard_report_response.error_code is not None:
        print(f"  {WARN}  API returned error: {hansard_report_response.description} — using synthetic payload instead")
        return None  # signal to caller to fall back

    if is_new:
        hansard_sitting_date_response = build_new_hansard_sitting_date_response(hansard_report_response, sitting_date)
        metadata = raw["metadata"] or {}
        metadata_key_to_orm_field = {
            "parlimentNO": "parlement_no",
            "sessionNO": "session_no",
            "volumeNO": "volume_no",
            "sittingNO": "sitting_no",
            "partSessionStr": "part_session_str",
            "startTimeStr": "start_time_str",
            "speaker": "speaker",
            "attendancePreviewText": "attendance_preview_text",
            "ptbaPreviewText": "ptba_preview_text",
            "atbPreviewText": "atb_preview_text",
            "dateToDisplay": "date_to_display",
            "pdfNotes": "pdf_notes",
            "waText": "wa_text",
            "ptbaFrom": "ptba_from",
            "ptbaTo": "ptba_to",
            "locationText": "location_text",
        }
        raw_key_to_orm_field = {
            "attStartPgNo": "att_start_pg_no",
            "ptbaStartPgNo": "ptba_start_pg_no",
            "atbpStartPgNo": "atbp_start_pg_no",
            "onlinePDFFileName": "online_pdf_file_name",
        }
        orm_field_to_value = _get_orm_field_to_value(hansard_sitting_date_response)
        failures = []
        for metadata_key, orm_field in metadata_key_to_orm_field.items():
            value = metadata.get(metadata_key)
            if value is None or value == "":
                continue
            if orm_field_to_value.get(orm_field) is None:
                failures.append(f"  {FAIL}  metadata[{metadata_key!r}]={str(value)[:_VALUE_PREVIEW_LENGTH]!r}  →  .{orm_field}=None")
        for raw_key, orm_field in raw_key_to_orm_field.items():
            value = raw.get(raw_key)
            if value is None or value == "":
                continue
            if orm_field_to_value.get(orm_field) is None:
                failures.append(f"  {FAIL}  raw[{raw_key!r}]={str(value)[:_VALUE_PREVIEW_LENGTH]!r}  →  .{orm_field}=None")
    else:
        hansard_sitting_date_response = build_old_hansard_sitting_date_response(hansard_report_response, sitting_date)
        raw_key_to_orm_field = {
            "parlNo": "parlement_no",
            "sessionNo": "session_no",
            "volumeNo": "volume_no",
            "sittingNo": "sitting_no",
            "onlinePDFFileName": "online_pdf_file_name",
            "htmlFullContent": "html_full_content",
            "ptbaFrom": "ptba_from",
            "ptbaTo": "ptba_to",
            "memberId": "member_id",
            "reportType": "report_type",
            "portfolio": "portfolio",
            "memberName": "member_name",
            "reportVersion": "report_version",
            "reportStartCol": "report_start_col",
            "reportEndCol": "report_end_col",
            "title": "title",
            "columnStart": "column_start",
            "reportContent": "report_content",
            "columnEnd": "column_end",
            "reportId": "report_id",
            "maxResult": "max_result",
            "sno": "sno",
            "fullContentFlag": "full_content_flag",
            "fromMonth": "from_month",
            "fromDay": "from_day",
            "fromYear": "from_year",
            "htmlContent": "html_content",
            "subtitle": "subtitle",
            "content": "content",
            "mpNames": "speaker_names",
            "htmlFileName": "html_file_name",
            "verPdf": "ver_pdf",
            "footNotes": "foot_notes",
            "footNoteQuestion": "foot_note_question",
            "footNoteQuestions": "foot_note_questions",
            "pdfNodes": "pdf_nodes",
            "clarificationText": "clarification_text",
            "clarificationTitle": "clarification_title",
            "clarificationSubTitle": "clarification_sub_title",
            "questionCount": "question_count",
        }
        orm_field_to_value = _get_orm_field_to_value(hansard_sitting_date_response)
        failures = []
        for raw_key, orm_field in raw_key_to_orm_field.items():
            value = raw.get(raw_key)
            if value is None or value == "" or value == []:
                continue
            if orm_field_to_value.get(orm_field) is None:
                failures.append(
                    f"  {FAIL}  raw[{raw_key!r}]={str(value)[:_VALUE_PREVIEW_LENGTH]!r}  →  .{orm_field}=None"
                )

    format_label = "new" if is_new else "old"
    if failures:
        for line in failures:
            print(line)
        return False
    print(f"  {PASS}  HansardSittingDateResponse ({format_label} format, {source}) — no field losses")
    return True


def validate_sitting_date(sitting_date: str, label: str, synthetic: dict) -> bool:
    _section(f"API 3 — getHansardReport ({label})")
    print(f"  {INFO}  sitting_date={sitting_date!r}")

    response_schema = HansardReportNewResponse if is_new_sitting_date_format(sitting_date) else HansardReportOldResponse
    try:
        hansard_report_response = get_hansard_report_response(sitting_date)
    except Exception as error:  # noqa: BLE001 the API call is probed and its failure is the finding, so fall back to the synthetic payload
        print(f"  {WARN}  API call failed ({error}) — using synthetic payload")
        hansard_report_response = response_schema(error_code=_HTTP_INTERNAL_SERVER_ERROR)

    is_passed = _validate_sitting_payload(hansard_report_response, sitting_date, source="live API")
    if is_passed is None:
        # API returned an error — fall back to synthetic
        is_passed = _validate_sitting_payload(
            response_schema.model_validate(synthetic), sitting_date, source="synthetic payload"
        )

    return bool(is_passed)


if __name__ == "__main__":
    is_all_passed = True
    is_all_passed &= validate_search_and_topic()
    is_all_passed &= validate_topic(get_hansard_search_results(0, 0)[0].report_id)
    is_all_passed &= validate_sitting_date(
        "11-05-2015",
        "old format, pre-2015-08-18",
        _SYNTHETIC_OLD_FORMAT,
    )
    is_all_passed &= validate_sitting_date(
        "15-01-2024",
        "new format, post-2015-08-18",
        _SYNTHETIC_NEW_FORMAT,
    )

    print(f"\n{'─' * 64}")
    if is_all_passed:
        print(f"  {PASS}  All field mappings verified.")
    else:
        print(f"  {FAIL}  One or more field losses detected — see above.")
        sys.exit(1)

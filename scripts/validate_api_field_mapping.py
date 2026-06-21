"""Validates that every non-None field in a raw API response survives parsing into the ORM.

For live APIs that respond: calls the real endpoint and verifies field coverage.
For endpoints that are unavailable: falls back to a synthetic payload that exercises
every mapped field, which is a stricter test than hitting an endpoint that may omit fields.

No data is written to the database.

Usage:
    PYTHONPATH=. poetry run python scripts/validate_api_field_mapping.py
"""

import sys
from datetime import datetime
from typing import Any

from gateway.handsard_report import get_handsard_report_response
from gateway.handsard_search import get_handsard_search_results
from gateway.handsard_topic import get_handsard_topic_response
from schemas.handsard_search_result import HandsardSearchResult
from services.handsard_sitting_date_response import (
    build_new_handsard_sitting_date_response,
    build_old_handsard_sitting_date_response,
)
from services.handsard_website import build_handsard_website_response
from settings import settings

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"
INFO = "\033[34mINFO\033[0m"

# Synthetic payload for old-format sitting dates (pre-18 Aug 2015).
# Covers every field mapped by build_old_handsard_sitting_date_response.
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

# Synthetic payload for new-format sitting dates (18 Aug 2015 onwards).
# Covers every field mapped by build_new_handsard_sitting_date_response.
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


def _orm_fields(obj) -> dict[str, Any]:
    return {k: v for k, v in vars(obj).items() if not k.startswith("_")}


def _to_snake(name: str) -> str:
    import re
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1).lower()


def _section(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print("─" * 64)


def validate_search_and_topic() -> bool:
    _section("API 1 — searchResult  →  HandsardSearchResult  →  HandsardWebsiteResponse")
    raw_list = get_handsard_search_results(0, 0)
    if not raw_list:
        print(f"  {WARN}  No search results returned (check settings.search_from_date).")
        return True

    raw = raw_list[0]
    print(f"  {INFO}  report_id={raw.get('reportId')}  title={raw.get('title', '')[:55]}")

    # Pydantic parse: check every field that has a value in raw is non-None in parsed
    parsed = HandsardSearchResult.model_validate(raw)
    parsed_dict = parsed.model_dump()

    pydantic_failures = []
    for raw_key, raw_val in raw.items():
        if raw_val is None or raw_val == "" or raw_val == []:
            continue
        snake = _to_snake(raw_key)
        if snake not in parsed_dict:
            continue
        if parsed_dict[snake] is None:
            pydantic_failures.append(
                f"  {FAIL}  raw[{raw_key!r}]={str(raw_val)[:55]!r}  →  HandsardSearchResult.{snake}=None"
            )

    if pydantic_failures:
        print("\n  HandsardSearchResult field losses:")
        for line in pydantic_failures:
            print(line)
    else:
        print(f"  {PASS}  HandsardSearchResult — all raw fields survive Pydantic parse")

    # ORM build: check the explicitly mapped fields
    orm = build_handsard_website_response(parsed, content=None)
    orm_dict = _orm_fields(orm)
    mapped_raw_keys = {
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
    for raw_key, orm_field in mapped_raw_keys.items():
        raw_val = raw.get(raw_key)
        if raw_val is None or raw_val == "":
            continue
        orm_val = orm_dict.get(orm_field)
        if orm_val is None:
            orm_failures.append(
                f"  {FAIL}  raw[{raw_key!r}]={str(raw_val)[:55]!r}  →  HandsardWebsiteResponse.{orm_field}=None"
            )

    if orm_failures:
        print("\n  HandsardWebsiteResponse field losses:")
        for line in orm_failures:
            print(line)
    else:
        print(f"  {PASS}  HandsardWebsiteResponse — all mapped fields present")

    return not (pydantic_failures or orm_failures)


def validate_topic(report_id: str) -> bool:
    _section("API 2 — getHansardTopic  →  htmlContent  →  HandsardWebsiteResponse.content")
    print(f"  {INFO}  report_id={report_id!r}")
    raw_list = get_handsard_search_results(0, 0)
    if not raw_list:
        print(f"  {WARN}  No search results; skipping.")
        return True

    raw = next((r for r in raw_list if r.get("reportId") == report_id), raw_list[0])
    parsed = HandsardSearchResult.model_validate(raw)
    topic_raw = get_handsard_topic_response(report_id)
    html_content = topic_raw.get("htmlContent") if isinstance(topic_raw, dict) else None

    orm = build_handsard_website_response(parsed, content=html_content)
    if html_content:
        if orm.content is None:
            print(f"  {FAIL}  topic.htmlContent ({len(html_content)} chars)  →  orm.content=None")
            return False
        print(f"  {PASS}  htmlContent ({len(html_content)} chars) → orm.content ({len(orm.content)} chars)")
    else:
        topic_keys = list(topic_raw.keys()) if isinstance(topic_raw, dict) else []
        print(
            f"  {INFO}  htmlContent absent for this report type "
            f"(topic response keys: {topic_keys}) — expected for written answers"
        )
    return True


def _validate_sitting_payload(raw: dict, sitting_date: str, source: str) -> bool:
    cutoff = settings.sitting_date_format_change
    is_new = datetime.strptime(sitting_date, "%Y-%m-%d") >= cutoff

    if "errorCode" in raw:
        print(f"  {WARN}  API returned error: {raw.get('description')} — using synthetic payload instead")
        return None  # signal to caller to fall back

    if is_new:
        data = build_new_handsard_sitting_date_response(raw, sitting_date)
        metadata = raw.get("metadata") or {}
        new_mapped = {
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
        top_mapped = {
            "attStartPgNo": "att_start_pg_no",
            "ptbaStartPgNo": "ptba_start_pg_no",
            "atbpStartPgNo": "atbp_start_pg_no",
            "onlinePDFFileName": "online_pdf_file_name",
        }
        orm_dict = _orm_fields(data.response)
        failures = []
        for meta_key, orm_field in new_mapped.items():
            val = metadata.get(meta_key)
            if val is None or val == "":
                continue
            if orm_dict.get(orm_field) is None:
                failures.append(f"  {FAIL}  metadata[{meta_key!r}]={str(val)[:55]!r}  →  .{orm_field}=None")
        for rk, of in top_mapped.items():
            val = raw.get(rk)
            if val is None or val == "":
                continue
            if orm_dict.get(of) is None:
                failures.append(f"  {FAIL}  raw[{rk!r}]={str(val)[:55]!r}  →  .{of}=None")
    else:
        data = build_old_handsard_sitting_date_response(raw, sitting_date)
        old_mapped = {
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
        orm_dict = _orm_fields(data.response)
        failures = []
        for raw_key, orm_field in old_mapped.items():
            val = raw.get(raw_key)
            if val is None or val == "" or val == []:
                continue
            if orm_dict.get(orm_field) is None:
                failures.append(
                    f"  {FAIL}  raw[{raw_key!r}]={str(val)[:55]!r}  →  .{orm_field}=None"
                )

    fmt = "new" if is_new else "old"
    if failures:
        for line in failures:
            print(line)
        return False
    print(f"  {PASS}  HandsardSittingDateResponse ({fmt} format, {source}) — no field losses")
    return True


def validate_sitting_date(sitting_date: str, label: str, synthetic: dict) -> bool:
    _section(f"API 3 — getHansardReport ({label})")
    print(f"  {INFO}  sitting_date={sitting_date!r}")

    try:
        raw = get_handsard_report_response(sitting_date)
    except Exception as e:
        print(f"  {WARN}  API call failed ({e}) — using synthetic payload")
        raw = {"errorCode": 500}

    result = _validate_sitting_payload(raw, sitting_date, source="live API")
    if result is None:
        # API returned an error — fall back to synthetic
        result = _validate_sitting_payload(synthetic, sitting_date, source="synthetic payload")

    return bool(result)


if __name__ == "__main__":
    all_passed = True
    all_passed &= validate_search_and_topic()
    all_passed &= validate_topic(get_handsard_search_results(0, 0)[0].get("reportId", ""))
    all_passed &= validate_sitting_date(
        "2015-05-11",
        "old format, pre-2015-08-18",
        SYNTHETIC_OLD_FORMAT,
    )
    all_passed &= validate_sitting_date(
        "2024-01-15",
        "new format, post-2015-08-18",
        SYNTHETIC_NEW_FORMAT,
    )

    print(f"\n{'─' * 64}")
    if all_passed:
        print(f"  {PASS}  All field mappings verified.")
    else:
        print(f"  {FAIL}  One or more field losses detected — see above.")
        sys.exit(1)

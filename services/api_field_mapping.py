from typing import Optional, Union

from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.hansard_website_response import HansardWebsiteResponse
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from schemas.hansard_search_result import HansardSearchResult
from schemas.hansard_topic_response import HansardTopicResponse

_VALUE_PREVIEW_LENGTH = 55
_TOPIC_FIELD_LOSS = "  FAIL  topic body holds text but the mapped field is empty"
_SEARCH_KEY_TO_ORM_FIELD = {
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
_NEW_FORMAT_METADATA_KEY_TO_ORM_FIELD = {
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
_NEW_FORMAT_KEY_TO_ORM_FIELD = {
    "attStartPgNo": "att_start_pg_no",
    "ptbaStartPgNo": "ptba_start_pg_no",
    "atbpStartPgNo": "atbp_start_pg_no",
    "onlinePDFFileName": "online_pdf_file_name",
}
_OLD_FORMAT_KEY_TO_ORM_FIELD = {
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


def _get_orm_field_to_value(orm_object: object) -> dict[str, object]:
    return {key: value for key, value in vars(orm_object).items() if not key.startswith("_")}


def get_search_result_field_losses(hansard_search_result: HansardSearchResult, hansard_website_response: HansardWebsiteResponse) -> list[str]:
    raw_key_to_value = hansard_search_result.model_dump(by_alias=True)
    orm_field_to_value = _get_orm_field_to_value(hansard_website_response)
    orm_failures = []
    for raw_key, orm_field in _SEARCH_KEY_TO_ORM_FIELD.items():
        raw_value = raw_key_to_value.get(raw_key)
        if raw_value is None or raw_value == "":
            continue
        orm_value = orm_field_to_value.get(orm_field)
        if orm_value is None:
            orm_failures.append(
                f"  FAIL  raw[{raw_key!r}]={str(raw_value)[:_VALUE_PREVIEW_LENGTH]!r}  →  HansardWebsiteResponse.{orm_field}=None"
            )
    return orm_failures


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""


def get_topic_field_losses(hansard_topic_response: HansardTopicResponse, html_content: Optional[str]) -> list[str]:
    if html_content is not None and html_content != "":
        return []
    if _is_non_empty_str(hansard_topic_response.html_content):
        return [_TOPIC_FIELD_LOSS]
    if hansard_topic_response.result_html is not None and _is_non_empty_str(hansard_topic_response.result_html.content):
        return [_TOPIC_FIELD_LOSS]
    return []


def get_sitting_date_field_losses(
    hansard_report_response: Union[HansardReportOldResponse, HansardReportNewResponse],
    hansard_sitting_date_response: HansardSittingDateResponse,
) -> list[str]:
    raw_key_to_value = hansard_report_response.model_dump(by_alias=True)
    orm_field_to_value = _get_orm_field_to_value(hansard_sitting_date_response)
    failures = []
    if isinstance(hansard_report_response, HansardReportNewResponse):
        metadata = {} if raw_key_to_value["metadata"] is None else raw_key_to_value["metadata"]
        for metadata_key, orm_field in _NEW_FORMAT_METADATA_KEY_TO_ORM_FIELD.items():
            value = metadata.get(metadata_key)
            if value is None or value == "":
                continue
            if orm_field_to_value.get(orm_field) is None:
                failures.append(f"  FAIL  metadata[{metadata_key!r}]={str(value)[:_VALUE_PREVIEW_LENGTH]!r}  →  .{orm_field}=None")
        for raw_key, orm_field in _NEW_FORMAT_KEY_TO_ORM_FIELD.items():
            value = raw_key_to_value.get(raw_key)
            if value is None or value == "":
                continue
            if orm_field_to_value.get(orm_field) is None:
                failures.append(f"  FAIL  raw[{raw_key!r}]={str(value)[:_VALUE_PREVIEW_LENGTH]!r}  →  .{orm_field}=None")
        return failures
    for raw_key, orm_field in _OLD_FORMAT_KEY_TO_ORM_FIELD.items():
        value = raw_key_to_value.get(raw_key)
        if value is None or value == "" or value == []:
            continue
        if orm_field_to_value.get(orm_field) is None:
            failures.append(
                f"  FAIL  raw[{raw_key!r}]={str(value)[:_VALUE_PREVIEW_LENGTH]!r}  →  .{orm_field}=None"
            )
    return failures

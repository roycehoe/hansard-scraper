# NOTE: every field here, including HansardReportAttendanceEntry, is Optional with a None default, which STYLE.md forbids on a response schema.
# This is a licensed exception: getHansardReport returns an old, a new or an error body, and the builders read all three.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class HansardReportOldResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    parl_no: Optional[object] = None
    session_no: Optional[object] = None
    volume_no: Optional[object] = None
    sitting_no: Optional[object] = None
    online_pdf_file_name: Optional[str] = Field(default=None, alias="onlinePDFFileName")
    html_full_content: Optional[str] = None
    ptba_from: Optional[str] = None
    ptba_to: Optional[str] = None
    member_id: Optional[object] = None
    report_type: Optional[object] = None
    portfolio: Optional[str] = None
    member_name: Optional[str] = None
    report_version: Optional[object] = None
    report_start_col: Optional[object] = None
    report_end_col: Optional[object] = None
    title: Optional[str] = None
    column_start: Optional[object] = None
    report_content: Optional[object] = None
    column_end: Optional[object] = None
    report_id: Optional[object] = None
    score: Optional[object] = None
    max_result: Optional[object] = None
    sno: Optional[object] = None
    full_content_flag: Optional[object] = None
    from_month: Optional[object] = None
    from_day: Optional[object] = None
    from_year: Optional[object] = None
    html_content: Optional[object] = None
    subtitle: Optional[object] = None
    content: Optional[object] = None
    mp_names: Optional[object] = None
    html_file_name: Optional[object] = None
    ver_pdf: Optional[object] = None
    foot_notes: Optional[object] = None
    foot_note_question: Optional[object] = None
    foot_note_questions: Optional[object] = None
    foot_note: Optional[list] = None
    atbp_list: Optional[list] = None
    ptba_list: Optional[list] = None
    attendance_list: Optional[list] = None
    pdf_nodes: Optional[object] = None
    clarification_text: Optional[object] = None
    clarification_title: Optional[object] = None
    clarification_sub_title: Optional[object] = None
    question_count: Optional[object] = None
    error_code: Optional[object] = None
    description: Optional[object] = None


class HansardReportMetadata(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    parliment_no: Optional[int] = Field(default=None, alias="parlimentNO")
    session_no: Optional[int] = Field(default=None, alias="sessionNO")
    volume_no: Optional[int] = Field(default=None, alias="volumeNO")
    sitting_no: Optional[int] = Field(default=None, alias="sittingNO")
    part_session_str: Optional[str] = None
    start_time_str: Optional[str] = None
    speaker: Optional[str] = None
    attendance_preview_text: Optional[str] = None
    ptba_preview_text: Optional[str] = None
    atb_preview_text: Optional[str] = None
    date_to_display: Optional[str] = None
    pdf_notes: Optional[str] = None
    wa_text: Optional[str] = None
    ptba_from: Optional[str] = None
    ptba_to: Optional[str] = None
    location_text: Optional[str] = None


class HansardReportAttendanceEntry(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    mp_name: Optional[str] = None
    attendance: Optional[bool] = None
    location_name: Optional[str] = None


class HansardReportNewResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    metadata: Optional[HansardReportMetadata] = None
    att_start_pg_no: Optional[int] = None
    ptba_start_pg_no: Optional[int] = None
    atbp_start_pg_no: Optional[int] = None
    online_pdf_file_name: Optional[str] = Field(default=None, alias="onlinePDFFileName")
    html_full_content: Optional[str] = None
    attendance_list: Optional[list] = None
    ptba_list: Optional[object] = None
    takes_section_vo_list: Optional[object] = Field(default=None, alias="takesSectionVOList")
    annexure_list: Optional[object] = None
    vernacular_list: Optional[object] = None
    a2b_list: Optional[object] = Field(default=None, alias="a2bList")
    error_code: Optional[object] = None
    description: Optional[object] = None

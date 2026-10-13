# NOTE: every field here is Optional with a None default, which STYLE.md forbids on a response schema.
# This is a licensed exception: getHansardTopic returns three body shapes, and the caller reads only html_content.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class HansardTopicResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    member_id: Optional[object] = None
    volume_no: Optional[object] = None
    report_type: Optional[object] = None
    session_no: Optional[object] = None
    portfolio: Optional[object] = None
    member_name: Optional[object] = None
    report_version: Optional[object] = None
    report_start_col: Optional[object] = None
    sitting_no: Optional[object] = None
    report_end_col: Optional[object] = None
    title: Optional[object] = None
    column_start: Optional[object] = None
    parl_no: Optional[object] = None
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
    html_full_content: Optional[object] = None
    html_content: Optional[str] = None
    subtitle: Optional[object] = None
    sitting_date: Optional[object] = None
    content: Optional[object] = None
    mp_names: Optional[object] = None
    html_file_name: Optional[object] = None
    ver_pdf: Optional[object] = None
    foot_notes: Optional[object] = None
    foot_note_question: Optional[object] = None
    foot_note_questions: Optional[object] = None
    foot_note: Optional[object] = None
    atbp_list: Optional[object] = None
    ptba_list: Optional[object] = None
    attendance_list: Optional[object] = None
    online_pdf_file_name: Optional[object] = Field(default=None, alias="onlinePDFFileName")
    pdf_nodes: Optional[object] = None
    clarification_text: Optional[object] = None
    clarification_title: Optional[object] = None
    clarification_sub_title: Optional[object] = None
    ptba_from: Optional[object] = None
    ptba_to: Optional[object] = None
    question_count: Optional[object] = None
    result_data: Optional[object] = None
    result_html: Optional[object] = Field(default=None, alias="resultHTML")
    type: Optional[object] = None
    error_code: Optional[object] = None
    description: Optional[object] = None

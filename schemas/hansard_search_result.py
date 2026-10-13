from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class HansardSearchResult(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    member_id: Optional[object] = None
    volume_no: str
    report_type: str
    session_no: Optional[object] = None
    portfolio: Optional[object] = None
    member_name: Optional[object] = None
    report_version: str
    report_start_col: Optional[object] = None
    sitting_no: Optional[str] = None
    report_end_col: Optional[object] = None
    title: str
    column_start: str
    parl_no: str
    report_content: Optional[object] = None
    column_end: str
    report_id: str
    score: Optional[object] = None
    max_result: Optional[str] = None
    sno: str
    full_content_flag: Optional[object] = None
    from_month: Optional[str] = None
    from_day: Optional[str] = None
    from_year: Optional[str] = None
    html_full_content: Optional[object] = None
    html_content: Optional[object] = None
    subtitle: Optional[object] = None
    sitting_date: str
    content: Optional[str] = None
    mp_names: Optional[object] = None
    html_file_name: Optional[str] = None
    ver_pdf: Optional[object] = None
    foot_notes: Optional[object] = None
    foot_note_question: Optional[object] = None
    foot_note_questions: Optional[object] = None
    foot_note: Optional[list] = None
    atbp_list: Optional[list] = None
    ptba_list: Optional[list] = None
    attendance_list: Optional[list] = None
    online_pdf_file_name: Optional[object] = Field(default=None, alias="onlinePDFFileName")
    pdf_nodes: Optional[object] = None
    clarification_text: Optional[object] = None
    clarification_title: Optional[object] = None
    clarification_sub_title: Optional[object] = None
    ptba_from: Optional[object] = None
    ptba_to: Optional[object] = None
    question_count: Optional[object] = None

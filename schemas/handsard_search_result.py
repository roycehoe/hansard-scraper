from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class HandsardSearchResult(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    member_id: Optional[Any] = None
    volume_no: str
    report_type: str
    session_no: Optional[Any] = None
    portfolio: Optional[Any] = None
    member_name: Optional[Any] = None
    report_version: str
    report_start_col: Optional[Any] = None
    sitting_no: Optional[str] = None
    report_end_col: Optional[Any] = None
    title: str
    column_start: str
    parl_no: str
    report_content: Optional[Any] = None
    column_end: str
    report_id: str
    score: Optional[Any] = None
    max_result: Optional[str] = None
    sno: str
    full_content_flag: Optional[Any] = None
    from_month: Optional[str] = None
    from_day: Optional[str] = None
    from_year: Optional[str] = None
    html_full_content: Optional[Any] = None
    html_content: Optional[Any] = None
    subtitle: Optional[Any] = None
    sitting_date: str
    content: Optional[str] = None
    mp_names: Optional[Any] = None
    html_file_name: Optional[str] = None
    ver_pdf: Optional[Any] = None
    foot_notes: Optional[Any] = None
    foot_note_question: Optional[Any] = None
    foot_note_questions: Optional[Any] = None
    foot_note: Optional[list] = None
    atbp_list: Optional[list] = None
    ptba_list: Optional[list] = None
    attendance_list: Optional[list] = None
    online_pdf_file_name: Optional[Any] = Field(default=None, alias="onlinePDFFileName")
    pdf_nodes: Optional[Any] = None
    clarification_text: Optional[Any] = None
    clarification_title: Optional[Any] = None
    clarification_sub_title: Optional[Any] = None
    ptba_from: Optional[Any] = None
    ptba_to: Optional[Any] = None
    question_count: Optional[Any] = None

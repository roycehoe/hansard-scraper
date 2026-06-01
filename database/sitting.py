from typing import Any, Optional

from pydantic import ConfigDict, model_validator
from pydantic.alias_generators import to_camel
from sqlmodel import Field, SQLModel


class Sitting(SQLModel, table=True):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def strip_nul(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v.replace("\x00", "") if isinstance(v, str) else v for k, v in data.items()}
        return data

    id: Optional[int] = Field(default=None, primary_key=True)

    # Shared fields (old and new format)
    parlement_no: Optional[int] = None
    session_no: Optional[int] = None
    volume_no: Optional[int] = None
    sitting_no: Optional[int] = None
    sitting_date: Optional[str] = None
    online_pdf_file_name: Optional[str] = Field(default=None, alias="onlinePDFFileName")
    html_full_content: Optional[str] = None
    ptba_from: Optional[str] = None
    ptba_to: Optional[str] = None

    # New format only (from metadata and top-level scalars)
    part_session_str: Optional[str] = None
    start_time_str: Optional[str] = None
    speaker: Optional[str] = None
    attendance_preview_text: Optional[str] = None
    ptba_preview_text: Optional[str] = None
    atb_preview_text: Optional[str] = None
    date_to_display: Optional[str] = None
    pdf_notes: Optional[str] = None
    wa_text: Optional[str] = None
    location_text: Optional[str] = None
    att_start_pg_no: Optional[int] = None
    ptba_start_pg_no: Optional[int] = None
    atbp_start_pg_no: Optional[int] = None

    # Old format only
    member_id: Optional[str] = None
    report_type: Optional[str] = None
    portfolio: Optional[str] = None
    member_name: Optional[str] = None
    report_version: Optional[str] = None
    report_start_col: Optional[str] = None
    report_end_col: Optional[str] = None
    title: Optional[str] = None
    column_start: Optional[str] = None
    report_content: Optional[str] = None
    column_end: Optional[str] = None
    report_id: Optional[str] = None
    score: Optional[str] = None
    max_result: Optional[str] = None
    sno: Optional[str] = None
    full_content_flag: Optional[str] = None
    from_month: Optional[str] = None
    from_day: Optional[str] = None
    from_year: Optional[str] = None
    html_content: Optional[str] = None
    subtitle: Optional[str] = None
    content: Optional[str] = None
    mp_names: Optional[str] = None
    html_file_name: Optional[str] = None
    ver_pdf: Optional[str] = None
    foot_notes: Optional[str] = None
    foot_note_question: Optional[str] = None
    foot_note_questions: Optional[str] = None
    foot_note: Optional[str] = None       # serialised JSON list
    atbp_list: Optional[str] = None       # serialised JSON list
    ptba_list: Optional[str] = None       # serialised JSON list
    attendance_list: Optional[str] = None  # serialised JSON list
    pdf_nodes: Optional[str] = None
    clarification_text: Optional[str] = None
    clarification_title: Optional[str] = None
    clarification_sub_title: Optional[str] = None
    question_count: Optional[str] = None

    markdown_content: Optional[str] = None

    # Child list data stored as serialised JSON (sections, annexures, vernaculars, a2b)
    sections: Optional[str] = None
    annexures: Optional[str] = None
    vernaculars: Optional[str] = None
    a2b: Optional[str] = None

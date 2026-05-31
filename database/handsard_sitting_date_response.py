from typing import Optional

from sqlmodel import Field, SQLModel


class HandsardSittingDateResponse(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    parlement_no: Optional[int] = None
    session_no: Optional[int] = None
    volume_no: Optional[int] = None
    sitting_no: Optional[int] = None
    sitting_date: Optional[str] = None
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
    att_start_pg_no: Optional[int] = None
    ptba_start_pg_no: Optional[int] = None
    atbp_start_pg_no: Optional[int] = None
    online_pdf_file_name: Optional[str] = None

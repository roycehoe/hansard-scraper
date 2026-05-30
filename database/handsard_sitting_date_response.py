from typing import Optional

from sqlmodel import Field, SQLModel


class HandsardSittingDateResponse(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    member_id: Optional[str] = Field(default=None, alias="memberId")
    volume_no: str = Field(alias="volumeNo")
    report_type: Optional[str] = Field(default=None, alias="reportType")
    session_no: Optional[str] = Field(default=None, alias="sessionNo")
    portfolio: Optional[str] = None
    member_name: Optional[str] = Field(default=None, alias="memberName")
    report_version: Optional[str] = Field(default=None, alias="reportVersion")
    report_start_col: Optional[str] = Field(default=None, alias="reportStartCol")
    sitting_no: Optional[str] = Field(default=None, alias="sittingNo")
    report_end_col: Optional[str] = Field(default=None, alias="reportEndCol")
    title: Optional[str] = None
    column_start: Optional[str] = Field(default=None, alias="columnStart")
    parl_no: Optional[str] = Field(default=None, alias="parlNo")
    report_content: Optional[str] = Field(default=None, alias="reportContent")
    column_end: Optional[str] = Field(default=None, alias="columnEnd")
    report_id: Optional[str] = Field(default=None, alias="reportId")
    score: Optional[str] = None
    max_result: Optional[str] = Field(default=None, alias="maxResult")
    sno: Optional[str] = None
    full_content_flag: Optional[str] = Field(default=None, alias="fullContentFlag")
    from_month: Optional[str] = Field(default=None, alias="fromMonth")
    from_day: Optional[str] = Field(default=None, alias="fromDay")
    from_year: Optional[str] = Field(default=None, alias="fromYear")
    html_full_content: Optional[str] = Field(default=None, alias="htmlFullContent")
    html_content: Optional[str] = Field(default=None, alias="htmlContent")
    subtitle: Optional[str] = None
    sitting_date: Optional[str] = Field(default=None, alias="sittingDate")
    content: Optional[str] = None
    mp_names: Optional[str] = Field(default=None, alias="mpNames")
    html_file_name: Optional[str] = Field(default=None, alias="htmlFileName")
    ver_pdf: Optional[str] = Field(default=None, alias="verPdf")
    foot_notes: Optional[str] = Field(default=None, alias="footNotes")
    foot_note_question: Optional[str] = Field(default=None, alias="footNoteQuestion")
    foot_note_questions: Optional[str] = Field(default=None, alias="footNoteQuestions")
    foot_note: Optional[str] = Field(default=None, alias="footNote")
    atbp_list: Optional[str] = Field(default=None, alias="atbpList")
    ptba_list: Optional[str] = Field(default=None, alias="ptbaList")
    attendance_list: Optional[str] = Field(default=None, alias="attendanceList")
    online_pdf_file_name: Optional[str] = Field(default=None, alias="onlinePDFFileName")
    pdf_nodes: Optional[str] = Field(default=None, alias="pdfNodes")
    clarification_text: Optional[str] = Field(default=None, alias="clarificationText")
    clarification_title: Optional[str] = Field(default=None, alias="clarificationTitle")
    clarification_sub_title: Optional[str] = Field(default=None, alias="clarificationSubTitle")
    ptba_from: Optional[str] = Field(default=None, alias="ptbaFrom")
    ptba_to: Optional[str] = Field(default=None, alias="ptbaTo")
    question_count: Optional[str] = Field(default=None, alias="questionCount")

from typing import Any, List, Optional

from pydantic import BaseModel

# class Report(SQLModel, table=True):
#     id: int | None = Field(default=None, primary_key=True)
#
#     volume_number: int = Field(alias="volumeNo")
#     parliament_number: int = Field(alias="parlNo")
#     sitting_number: EmptyStrNoneInt = Field(None, alias="sittingNo")
#     sitting_date: datetime = Field(alias="sittingDate")
#     speech_number: int = Field(alias="sno")
#
#     title: str
#     subtitle: Optional[str] = None
#     # Can be used to obtain raw report via request params
#     report_id: str = Field(alias="reportId")
#     report_type: str = Field(alias="reportType")
#
#     column_start: Optional[str] = Field(None, alias="columnStart")
#     column_end: Optional[str] = Field(None, alias="columnEnd")
#     html_file_name: Optional[str] = Field(None, alias="htmlFileName")
#     content: Optional[str] = None
#
#     report_version: str = Field(alias="reportVersion")


class HandsardSearchResult(BaseModel):
    memberId: Optional[Any] = None
    volumeNo: str
    reportType: str
    sessionNo: Optional[Any] = None
    portfolio: Optional[Any] = None
    memberName: Optional[Any] = None
    reportVersion: str
    reportStartCol: Optional[Any] = None
    sittingNo: Optional[str] = None
    reportEndCol: Optional[Any] = None
    title: str
    columnStart: str
    parlNo: str
    reportContent: Optional[Any] = None
    columnEnd: str
    reportId: str
    score: Optional[Any] = None
    maxResult: Optional[str] = None
    sno: str
    fullContentFlag: Optional[Any] = None
    fromMonth: Optional[str] = None
    fromDay: Optional[str] = None
    fromYear: Optional[str] = None
    htmlFullContent: Optional[Any] = None
    htmlContent: Optional[Any] = None
    subtitle: Optional[Any] = None
    sittingDate: str
    content: Optional[str] = None
    mpNames: Optional[Any] = None
    htmlFileName: Optional[str] = None
    verPdf: Optional[Any] = None
    footNotes: Optional[Any] = None
    footNoteQuestion: Optional[Any] = None
    footNoteQuestions: Optional[Any] = None
    footNote: Optional[List] = None
    atbpList: Optional[List] = None
    ptbaList: Optional[List] = None
    attendanceList: Optional[List] = None
    onlinePDFFileName: Optional[Any] = None
    pdfNodes: Optional[Any] = None
    clarificationText: Optional[Any] = None
    clarificationTitle: Optional[Any] = None
    clarificationSubTitle: Optional[Any] = None
    ptbaFrom: Optional[Any] = None
    ptbaTo: Optional[Any] = None
    questionCount: Optional[Any] = None

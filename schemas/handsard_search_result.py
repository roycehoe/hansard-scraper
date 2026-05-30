from typing import Any, List, Optional

from pydantic import BaseModel


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

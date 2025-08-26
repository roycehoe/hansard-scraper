from typing import Annotated, Any, List, Optional

from pydantic import BaseModel, BeforeValidator, Field


class HandsardSearchResult(BaseModel):
    memberId: Any
    volumeNo: str
    reportType: str
    sessionNo: Any
    portfolio: Any
    memberName: Any
    reportVersion: str
    reportStartCol: Any
    sittingNo: str
    reportEndCol: Any
    title: str
    columnStart: str
    parlNo: str
    reportContent: Any
    columnEnd: str
    reportId: str
    score: Any
    maxResult: str
    sno: str
    fullContentFlag: Any
    fromMonth: str
    fromDay: str
    fromYear: str
    htmlFullContent: Any
    htmlContent: Any
    subtitle: Optional[str]
    sittingDate: str
    content: Any
    mpNames: Any
    htmlFileName: Any
    verPdf: Any
    footNotes: Any
    footNoteQuestion: Any
    footNoteQuestions: Any
    footNote: List
    atbpList: List
    ptbaList: List
    attendanceList: List
    onlinePDFFileName: Any
    pdfNodes: Any
    clarificationText: Any
    clarificationTitle: Any
    clarificationSubTitle: Any
    ptbaFrom: Any
    ptbaTo: Any
    questionCount: Any

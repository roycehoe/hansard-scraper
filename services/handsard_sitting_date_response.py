import json
from dataclasses import dataclass
from typing import Optional

from database.attendance import Attendance
from database.handsard_sitting_date_response import HandsardSittingDateResponse


@dataclass
class HandsardSittingDateData:
    response: HandsardSittingDateResponse
    attendance: list[Attendance]


def _to_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _serialise_list(value) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value) if isinstance(value, list) else value


def build_old_handsard_sitting_date_response(result: dict, sitting_date: str) -> HandsardSittingDateData:
    """Handles the flat response format returned for sittings before 18 Aug 2015."""
    response = HandsardSittingDateResponse(
        parlement_no=_to_int(result.get("parlNo")),
        session_no=_to_int(result.get("sessionNo")),
        volume_no=_to_int(result.get("volumeNo")),
        sitting_no=_to_int(result.get("sittingNo")),
        sitting_date=sitting_date,
        online_pdf_file_name=result.get("onlinePDFFileName"),
        html_full_content=result.get("htmlFullContent"),
        ptba_from=result.get("ptbaFrom"),
        ptba_to=result.get("ptbaTo"),
        member_id=result.get("memberId"),
        report_type=result.get("reportType"),
        portfolio=result.get("portfolio"),
        member_name=result.get("memberName"),
        report_version=result.get("reportVersion"),
        report_start_col=result.get("reportStartCol"),
        report_end_col=result.get("reportEndCol"),
        title=result.get("title"),
        column_start=result.get("columnStart"),
        report_content=result.get("reportContent"),
        column_end=result.get("columnEnd"),
        report_id=result.get("reportId"),
        score=result.get("score"),
        max_result=result.get("maxResult"),
        sno=result.get("sno"),
        full_content_flag=result.get("fullContentFlag"),
        from_month=result.get("fromMonth"),
        from_day=result.get("fromDay"),
        from_year=result.get("fromYear"),
        html_content=result.get("htmlContent"),
        subtitle=result.get("subtitle"),
        content=result.get("content"),
        speaker_names=result.get("mpNames"),
        html_file_name=result.get("htmlFileName"),
        ver_pdf=result.get("verPdf"),
        foot_notes=result.get("footNotes"),
        foot_note_question=result.get("footNoteQuestion"),
        foot_note_questions=result.get("footNoteQuestions"),
        foot_note=_serialise_list(result.get("footNote")),
        atbp_list=_serialise_list(result.get("atbpList")),
        ptba_list=_serialise_list(result.get("ptbaList")),
        attendance_list=_serialise_list(result.get("attendanceList")),
        pdf_nodes=result.get("pdfNodes"),
        clarification_text=result.get("clarificationText"),
        clarification_title=result.get("clarificationTitle"),
        clarification_sub_title=result.get("clarificationSubTitle"),
        question_count=result.get("questionCount"),
    )

    attendance = [
        Attendance(**item)
        for item in result.get("attendanceList") or []
        if isinstance(item, dict)
    ]

    return HandsardSittingDateData(response=response, attendance=attendance)


def build_new_handsard_sitting_date_response(result: dict, sitting_date: str) -> HandsardSittingDateData:
    """Handles the nested response format returned for sittings from 18 Aug 2015 onwards."""
    metadata = result.get("metadata") or {}

    response = HandsardSittingDateResponse(
        parlement_no=metadata.get("parlimentNO"),
        session_no=metadata.get("sessionNO"),
        volume_no=metadata.get("volumeNO"),
        sitting_no=metadata.get("sittingNO"),
        sitting_date=sitting_date,
        part_session_str=metadata.get("partSessionStr"),
        start_time_str=metadata.get("startTimeStr"),
        speaker=metadata.get("speaker"),
        attendance_preview_text=metadata.get("attendancePreviewText"),
        ptba_preview_text=metadata.get("ptbaPreviewText"),
        atb_preview_text=metadata.get("atbPreviewText"),
        date_to_display=metadata.get("dateToDisplay"),
        pdf_notes=metadata.get("pdfNotes"),
        wa_text=metadata.get("waText"),
        ptba_from=metadata.get("ptbaFrom"),
        ptba_to=metadata.get("ptbaTo"),
        location_text=metadata.get("locationText"),
        att_start_pg_no=result.get("attStartPgNo"),
        ptba_start_pg_no=result.get("ptbaStartPgNo"),
        atbp_start_pg_no=result.get("atbpStartPgNo"),
        online_pdf_file_name=result.get("onlinePDFFileName"),
    )

    attendance = [
        Attendance(**item)
        for item in result.get("attendanceList") or []
    ]

    return HandsardSittingDateData(response=response, attendance=attendance)

import json
from dataclasses import dataclass
from typing import Optional

from database.attendance import Attendance
from database.hansard_sitting_date_response import HansardSittingDateResponse


@dataclass
class HansardSittingDateData:
    response: HansardSittingDateResponse
    attendance: list[Attendance]


def _get_int(value: object) -> Optional[int]:
    try:
        return int(value)
    except TypeError:
        return None
    except ValueError:
        return None


def _serialise_list(value: object) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value) if isinstance(value, list) else value


def build_old_hansard_sitting_date_response(hansard_report_response: dict, sitting_date: str) -> HansardSittingDateData:
    """Handles the flat response format returned for sittings before 18 Aug 2015."""
    hansard_sitting_date_response = HansardSittingDateResponse(
        parlement_no=_get_int(hansard_report_response.get("parlNo")),
        session_no=_get_int(hansard_report_response.get("sessionNo")),
        volume_no=_get_int(hansard_report_response.get("volumeNo")),
        sitting_no=_get_int(hansard_report_response.get("sittingNo")),
        sitting_date=sitting_date,
        online_pdf_file_name=hansard_report_response.get("onlinePDFFileName"),
        html_full_content=hansard_report_response.get("htmlFullContent"),
        ptba_from=hansard_report_response.get("ptbaFrom"),
        ptba_to=hansard_report_response.get("ptbaTo"),
        member_id=hansard_report_response.get("memberId"),
        report_type=hansard_report_response.get("reportType"),
        portfolio=hansard_report_response.get("portfolio"),
        member_name=hansard_report_response.get("memberName"),
        report_version=hansard_report_response.get("reportVersion"),
        report_start_col=hansard_report_response.get("reportStartCol"),
        report_end_col=hansard_report_response.get("reportEndCol"),
        title=hansard_report_response.get("title"),
        column_start=hansard_report_response.get("columnStart"),
        report_content=hansard_report_response.get("reportContent"),
        column_end=hansard_report_response.get("columnEnd"),
        report_id=hansard_report_response.get("reportId"),
        score=hansard_report_response.get("score"),
        max_result=hansard_report_response.get("maxResult"),
        sno=hansard_report_response.get("sno"),
        full_content_flag=hansard_report_response.get("fullContentFlag"),
        from_month=hansard_report_response.get("fromMonth"),
        from_day=hansard_report_response.get("fromDay"),
        from_year=hansard_report_response.get("fromYear"),
        html_content=hansard_report_response.get("htmlContent"),
        subtitle=hansard_report_response.get("subtitle"),
        content=hansard_report_response.get("content"),
        speaker_names=hansard_report_response.get("mpNames"),
        html_file_name=hansard_report_response.get("htmlFileName"),
        ver_pdf=hansard_report_response.get("verPdf"),
        foot_notes=hansard_report_response.get("footNotes"),
        foot_note_question=hansard_report_response.get("footNoteQuestion"),
        foot_note_questions=hansard_report_response.get("footNoteQuestions"),
        foot_note=_serialise_list(hansard_report_response.get("footNote")),
        atbp_list=_serialise_list(hansard_report_response.get("atbpList")),
        ptba_list=_serialise_list(hansard_report_response.get("ptbaList")),
        attendance_list=_serialise_list(hansard_report_response.get("attendanceList")),
        pdf_nodes=hansard_report_response.get("pdfNodes"),
        clarification_text=hansard_report_response.get("clarificationText"),
        clarification_title=hansard_report_response.get("clarificationTitle"),
        clarification_sub_title=hansard_report_response.get("clarificationSubTitle"),
        question_count=hansard_report_response.get("questionCount"),
    )

    attendance = [
        Attendance(**item)
        for item in hansard_report_response.get("attendanceList") or []
        if isinstance(item, dict)
    ]

    return HansardSittingDateData(response=hansard_sitting_date_response, attendance=attendance)


def build_new_hansard_sitting_date_response(hansard_report_response: dict, sitting_date: str) -> HansardSittingDateData:
    """Handles the nested response format returned for sittings from 18 Aug 2015 onwards."""
    metadata = hansard_report_response.get("metadata") or {}

    hansard_sitting_date_response = HansardSittingDateResponse(
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
        att_start_pg_no=hansard_report_response.get("attStartPgNo"),
        ptba_start_pg_no=hansard_report_response.get("ptbaStartPgNo"),
        atbp_start_pg_no=hansard_report_response.get("atbpStartPgNo"),
        online_pdf_file_name=hansard_report_response.get("onlinePDFFileName"),
    )

    attendance = [
        Attendance(**item)
        for item in hansard_report_response.get("attendanceList") or []
    ]

    return HansardSittingDateData(response=hansard_sitting_date_response, attendance=attendance)

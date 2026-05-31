from dataclasses import dataclass

from database.handsard_sitting_date_response import HandsardSittingDateResponse
from database.sitting_a2b import SittingA2b
from database.sitting_annexure import SittingAnnexure
from database.sitting_attendance import SittingAttendance
from database.sitting_ptba import SittingPtba
from database.sitting_section import SittingSection
from database.sitting_vernacular import SittingVernacular


@dataclass
class HandsardSittingDateData:
    response: HandsardSittingDateResponse
    attendance: list[SittingAttendance]
    ptba: list[SittingPtba]
    sections: list[SittingSection]
    annexures: list[SittingAnnexure]
    vernaculars: list[SittingVernacular]
    a2b: list[SittingA2b]


def build_old_handsard_sitting_date_response(result: dict) -> HandsardSittingDateData:
    """Handles the flat response format returned for sittings before 18 Aug 2015."""

    def _to_int(value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    response = HandsardSittingDateResponse(
        parlement_no=_to_int(result.get("parlNo")),
        session_no=_to_int(result.get("sessionNo")),
        volume_no=_to_int(result.get("volumeNo")),
        sitting_no=_to_int(result.get("sittingNo")),
        sitting_date=result.get("sittingDate"),
        online_pdf_file_name=result.get("onlinePDFFileName"),
        html_full_content=result.get("htmlFullContent"),
    )

    attendance = [
        SittingAttendance(
            mp_name=item.get("mpName"),
            attendance=item.get("attendance"),
            location_name=item.get("locationName"),
        )
        for item in result.get("attendanceList") or []
        if isinstance(item, dict)
    ]

    ptba = [
        SittingPtba(
            mp_name=item.get("mpName"),
            from_date=item.get("from"),
            to_date=item.get("to"),
            start_dt_text=item.get("startDtText"),
            end_dt_text=item.get("endDtText"),
            start_dt_flag=item.get("startDtFlag"),
            end_dt_flag=item.get("endDtFlag"),
        )
        for item in result.get("ptbaList") or []
        if isinstance(item, dict)
    ]

    return HandsardSittingDateData(
        response=response,
        attendance=attendance,
        ptba=ptba,
        sections=[],
        annexures=[],
        vernaculars=[],
        a2b=[],
    )


def build_new_handsard_sitting_date_response(result: dict) -> HandsardSittingDateData:
    """Handles the nested response format returned for sittings from 18 Aug 2015 onwards."""
    metadata = result.get("metadata") or {}

    response = HandsardSittingDateResponse(
        parlement_no=metadata.get("parlimentNO"),
        session_no=metadata.get("sessionNO"),
        volume_no=metadata.get("volumeNO"),
        sitting_no=metadata.get("sittingNO"),
        sitting_date=metadata.get("sittingDate"),
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
        SittingAttendance(
            mp_name=item.get("mpName"),
            attendance=item.get("attendance"),
            location_name=item.get("locationName"),
        )
        for item in result.get("attendanceList") or []
    ]

    ptba = [
        SittingPtba(
            mp_name=item.get("mpName"),
            from_date=item.get("from"),
            to_date=item.get("to"),
            start_dt_text=item.get("startDtText"),
            end_dt_text=item.get("endDtText"),
            start_dt_flag=item.get("startDtFlag"),
            end_dt_flag=item.get("endDtFlag"),
        )
        for item in result.get("ptbaList") or []
    ]

    sections = [
        SittingSection(
            start_pg_no=item.get("startPgNo"),
            end_pg_no=item.get("endPgNo"),
            title=item.get("title"),
            sub_title=item.get("subTitle"),
            section_type=item.get("sectionType"),
            content=item.get("content"),
            clarification_text=item.get("clarificationText"),
            clarification_title=item.get("clarificationTitle"),
            clarification_sub_title=item.get("clarificationSubTitle"),
            report_type=item.get("reportType"),
            question_count=item.get("questionCount"),
            foot_notes=item.get("footNotes"),
            foot_note_questions=item.get("footNoteQuestions"),
            question_no=item.get("questionNo"),
        )
        for item in result.get("takesSectionVOList") or []
    ]

    annexures = [
        SittingAnnexure(
            annexure_id=item.get("annexureID"),
            sitting_date=item.get("sittingDate"),
            annexure_title=item.get("annexureTitle"),
            file_path=item.get("filePath"),
            file_name=item.get("fileName"),
            section_type=item.get("sectionType"),
            file=item.get("file"),
        )
        for item in result.get("annexureList") or []
    ]

    vernaculars = [
        SittingVernacular(
            vernacular_id=item.get("vernacularID"),
            sitting_date=item.get("sittingDate"),
            vernacular_title=item.get("vernacularTitle"),
            file_path=item.get("filePath"),
            file_name=item.get("fileName"),
        )
        for item in result.get("vernacularList") or []
    ]

    a2b = [
        SittingA2b(
            date=item.get("date"),
            bill=item.get("bill"),
            atbp_preview_text=item.get("atbpPreviewText"),
        )
        for item in result.get("a2bList") or []
    ]

    return HandsardSittingDateData(
        response=response,
        attendance=attendance,
        ptba=ptba,
        sections=sections,
        annexures=annexures,
        vernaculars=vernaculars,
        a2b=a2b,
    )

import json
from typing import Optional, Union

from database.hansard_sitting_date_response import HansardSittingDateResponse
from exceptions import HansardSittingReportError
from schemas.hansard_report_response import (
    HansardReportMetadata,
    HansardReportNewResponse,
    HansardReportOldResponse,
)


def _get_int(value: object, field_name: str, sitting_date: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except TypeError as error:
        raise HansardSittingReportError(f"Sitting {sitting_date}: {field_name} {value!r} is not an integer") from error
    except ValueError as error:
        raise HansardSittingReportError(f"Sitting {sitting_date}: {field_name} {value!r} is not an integer") from error


def _serialise_list(value: object) -> object:
    if value is None:
        return None
    return json.dumps(value) if isinstance(value, list) else value


def build_old_hansard_sitting_date_response(hansard_report_response: HansardReportOldResponse, sitting_date: str) -> HansardSittingDateResponse:
    return HansardSittingDateResponse(
        parlement_no=_get_int(hansard_report_response.parl_no, "parl_no", sitting_date),
        session_no=_get_int(hansard_report_response.session_no, "session_no", sitting_date),
        volume_no=_get_int(hansard_report_response.volume_no, "volume_no", sitting_date),
        sitting_no=_get_int(hansard_report_response.sitting_no, "sitting_no", sitting_date),
        sitting_date=sitting_date,
        online_pdf_file_name=hansard_report_response.online_pdf_file_name,
        html_full_content=hansard_report_response.html_full_content,
        ptba_from=hansard_report_response.ptba_from,
        ptba_to=hansard_report_response.ptba_to,
        member_id=hansard_report_response.member_id,
        report_type=hansard_report_response.report_type,
        portfolio=hansard_report_response.portfolio,
        member_name=hansard_report_response.member_name,
        report_version=hansard_report_response.report_version,
        report_start_col=hansard_report_response.report_start_col,
        report_end_col=hansard_report_response.report_end_col,
        title=hansard_report_response.title,
        column_start=hansard_report_response.column_start,
        report_content=hansard_report_response.report_content,
        column_end=hansard_report_response.column_end,
        report_id=hansard_report_response.report_id,
        score=hansard_report_response.score,
        max_result=hansard_report_response.max_result,
        sno=hansard_report_response.sno,
        full_content_flag=hansard_report_response.full_content_flag,
        from_month=hansard_report_response.from_month,
        from_day=hansard_report_response.from_day,
        from_year=hansard_report_response.from_year,
        html_content=hansard_report_response.html_content,
        subtitle=hansard_report_response.subtitle,
        content=hansard_report_response.content,
        speaker_names=hansard_report_response.mp_names,
        html_file_name=hansard_report_response.html_file_name,
        ver_pdf=hansard_report_response.ver_pdf,
        foot_notes=hansard_report_response.foot_notes,
        foot_note_question=hansard_report_response.foot_note_question,
        foot_note_questions=hansard_report_response.foot_note_questions,
        foot_note=_serialise_list(hansard_report_response.foot_note),
        atbp_list=_serialise_list(hansard_report_response.atbp_list),
        ptba_list=_serialise_list(hansard_report_response.ptba_list),
        attendance_list=_serialise_list(hansard_report_response.attendance_list),
        pdf_nodes=hansard_report_response.pdf_nodes,
        clarification_text=hansard_report_response.clarification_text,
        clarification_title=hansard_report_response.clarification_title,
        clarification_sub_title=hansard_report_response.clarification_sub_title,
        question_count=hansard_report_response.question_count,
    )


def build_new_hansard_sitting_date_response(hansard_report_response: HansardReportNewResponse, sitting_date: str) -> HansardSittingDateResponse:
    metadata = hansard_report_response.metadata if hansard_report_response.metadata is not None else HansardReportMetadata()

    return HansardSittingDateResponse(
        parlement_no=metadata.parliment_no,
        session_no=metadata.session_no,
        volume_no=metadata.volume_no,
        sitting_no=metadata.sitting_no,
        sitting_date=sitting_date,
        part_session_str=metadata.part_session_str,
        start_time_str=metadata.start_time_str,
        speaker=metadata.speaker,
        attendance_preview_text=metadata.attendance_preview_text,
        ptba_preview_text=metadata.ptba_preview_text,
        atb_preview_text=metadata.atb_preview_text,
        date_to_display=metadata.date_to_display,
        pdf_notes=metadata.pdf_notes,
        wa_text=metadata.wa_text,
        ptba_from=metadata.ptba_from,
        ptba_to=metadata.ptba_to,
        location_text=metadata.location_text,
        attendance_list=_serialise_list(hansard_report_response.attendance_list),
        ptba_list=_serialise_list(hansard_report_response.ptba_list),
        att_start_pg_no=hansard_report_response.att_start_pg_no,
        ptba_start_pg_no=hansard_report_response.ptba_start_pg_no,
        atbp_start_pg_no=hansard_report_response.atbp_start_pg_no,
        online_pdf_file_name=hansard_report_response.online_pdf_file_name,
    )


def build_hansard_sitting_date_response(
    hansard_report_response: Union[HansardReportOldResponse, HansardReportNewResponse], sitting_date_key: str
) -> HansardSittingDateResponse:
    if isinstance(hansard_report_response, HansardReportNewResponse):
        return build_new_hansard_sitting_date_response(hansard_report_response, sitting_date_key)
    return build_old_hansard_sitting_date_response(hansard_report_response, sitting_date_key)

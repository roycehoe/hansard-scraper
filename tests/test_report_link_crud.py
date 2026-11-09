from datetime import datetime
from typing import Optional

from sqlmodel import Session

from crud.report import CRUDReport
from crud.report_link import CRUDReportLink
from crud.speech import CRUDSpeech
from database.report import Report
from database.report_link import ReportLink
from database.speech import Speech
from enums import ReportLinkRule, ReportLinkType

_SITTING_DATE = datetime(2007, 10, 22)
_REFER_PATTERN = "%please refer to%"
_RESUMPTION_PATTERN = "%resumption of debate on%"


def _add_report(
    session: Session,
    report_id: str,
    html_file_name: Optional[str] = None,
) -> Report:
    report = Report(
        volume_number=83,
        parliament_number=11,
        sitting_date=_SITTING_DATE,
        speech_number=1,
        original_title=f"Original {report_id}",
        title=f"Title {report_id}",
        report_id=report_id,
        report_type="bill",
        content="Text.",
        report_version="sprs2",
        html_file_name=html_file_name,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _add_speech(session: Session, report: Report, ordinal: int, transcript: str) -> None:
    assert report.id is not None
    session.add(
        Speech(
            ordinal=ordinal,
            speaker="Mr A",
            transcript=transcript,
            sitting_date=_SITTING_DATE,
            report_type=report.report_type,
            report_id=report.id,
        )
    )
    session.commit()


def test_citation_rows_match_each_pattern_in_any_case_in_report_and_ordinal_order(
    scratch_session: Session,
) -> None:
    first_report = _add_report(scratch_session, "first-report")
    second_report = _add_report(scratch_session, "second-report")
    _add_speech(scratch_session, second_report, 1, "[PLEASE REFER TO the record]")
    _add_speech(scratch_session, first_report, 2, "Resumption of Debate on Bill")
    _add_speech(scratch_session, first_report, 1, "Nothing to see.")
    _add_speech(scratch_session, first_report, 3, "[Please refer to the record]")

    citation_rows = CRUDSpeech(scratch_session).get_citation_rows_by_transcript_ilike_patterns(
        [_REFER_PATTERN, _RESUMPTION_PATTERN]
    )

    assert first_report.id is not None
    assert second_report.id is not None
    assert [
        (citation_row.report_id, citation_row.ordinal, citation_row.transcript)
        for citation_row in citation_rows
    ] == [
        (first_report.id, 2, "Resumption of Debate on Bill"),
        (first_report.id, 3, "[Please refer to the record]"),
        (second_report.id, 1, "[PLEASE REFER TO the record]"),
    ]


def test_link_report_rows_hold_the_eight_columns(scratch_session: Session) -> None:
    report = _add_report(scratch_session, "linked-report", html_file_name="12-3.html")
    other_report = _add_report(scratch_session, "other-report")

    report_rows = CRUDReport(scratch_session).get_link_report_rows()

    assert report.id is not None
    assert other_report.id is not None
    assert [report_row.id for report_row in report_rows] == [report.id, other_report.id]
    report_row = report_rows[0]
    assert report_row.report_id == "linked-report"
    assert report_row.report_type == "bill"
    assert report_row.report_version == "sprs2"
    assert report_row.sitting_date == _SITTING_DATE
    assert report_row.original_title == "Original linked-report"
    assert report_row.title == "Title linked-report"
    assert report_row.html_file_name == "12-3.html"
    assert report_rows[1].html_file_name is None


def test_add_many_get_rows_and_delete_all_round_trip(scratch_session: Session) -> None:
    _add_report(scratch_session, "source-report")
    _add_report(scratch_session, "target-report")
    CRUDReportLink(scratch_session).add_many(
        [
            ReportLink(
                link_type=ReportLinkType.REPLY,
                rule=ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE,
                printed_citation="Official Report, 1 January 2000",
                source_report_id="source-report",
                target_report_id="target-report",
            )
        ]
    )
    scratch_session.commit()

    report_link_rows = CRUDReportLink(scratch_session).get_rows()

    assert len(report_link_rows) == 1
    assert report_link_rows[0].link_type == ReportLinkType.REPLY
    assert report_link_rows[0].rule == ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE
    assert report_link_rows[0].printed_citation == "Official Report, 1 January 2000"
    assert report_link_rows[0].source_report_id == "source-report"
    assert report_link_rows[0].target_report_id == "target-report"
    assert CRUDReportLink(scratch_session).delete_all() == 1
    scratch_session.commit()
    assert CRUDReportLink(scratch_session).get_rows() == []

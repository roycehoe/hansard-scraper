from collections import Counter

from sqlmodel import Session

from crud.report import CRUDReport
from crud.report_link import CRUDReportLink, ReportLinkRow
from crud.speech import CRUDSpeech
from database.report_link import ReportLink
from enums import ReportLinkType
from exceptions import HansardWriteCheckError
from logs import logger
from services.report_citation import get_printed_citations, get_resumption_heading
from services.report_link import (
    SHIPPED_REPORT_LINK_RULES,
    PlannedReportLink,
    ReportLinkPlan,
    build_report_link_plan,
)
from utils.data_files import get_report_link_title_corrections

_REPORT_LINK_TRANSCRIPT_PATTERNS = ("%please refer to%", "%resumption of debate on%")


def get_report_link_plan(session: Session) -> ReportLinkPlan:
    citation_rows = CRUDSpeech(session).get_citation_rows_by_transcript_ilike_patterns(
        _REPORT_LINK_TRANSCRIPT_PATTERNS
    )
    resumption_headings = [
        resumption_heading
        for resumption_heading in (
            get_resumption_heading(citation_row) for citation_row in citation_rows
        )
        if resumption_heading is not None
    ]
    return build_report_link_plan(
        [
            printed_citation
            for citation_row in citation_rows
            for printed_citation in get_printed_citations(citation_row)
        ],
        resumption_headings,
        CRUDReport(session).get_link_report_rows(),
        get_report_link_title_corrections(),
        SHIPPED_REPORT_LINK_RULES,
    )


def _build_report_links(planned_links: list[PlannedReportLink]) -> list[ReportLink]:
    return [
        ReportLink(
            link_type=planned_link.link_type,
            rule=planned_link.rule,
            printed_citation=planned_link.printed_citation,
            source_report_id=planned_link.source_report_id,
            target_report_id=planned_link.target_report_id,
        )
        for planned_link in planned_links
    ]


def _validate_can_commit_report_links(session: Session, plan: ReportLinkPlan) -> None:
    stored_counts = Counter(
        (report_link_row.link_type, report_link_row.rule)
        for report_link_row in CRUDReportLink(session).get_rows()
    )
    planned_counts = Counter(
        (planned_link.link_type, planned_link.rule)
        for planned_link in plan.planned_links
    )
    if stored_counts != planned_counts:
        raise HansardWriteCheckError(
            f"Stored report links by type and rule {dict(stored_counts)}, the plan has {dict(planned_counts)}"
        )


def write_report_link_plan(session: Session, plan: ReportLinkPlan) -> None:
    stored_count = len(CRUDReportLink(session).get_rows())
    deleted_count = CRUDReportLink(session).delete_all()
    if deleted_count != stored_count:
        raise HansardWriteCheckError(
            f"Deleted {deleted_count} report links, read {stored_count}"
        )
    CRUDReportLink(session).add_many(_build_report_links(plan.planned_links))
    _validate_can_commit_report_links(session, plan)


def _is_report_link_row_stale(
    report_link_row: ReportLinkRow,
    key_to_planned_link: dict[tuple[str, str, ReportLinkType], PlannedReportLink],
) -> bool:
    planned_link = key_to_planned_link.get(
        (
            report_link_row.source_report_id,
            report_link_row.target_report_id,
            report_link_row.link_type,
        )
    )
    if planned_link is None:
        return True
    return (
        planned_link.rule != report_link_row.rule
        or planned_link.printed_citation != report_link_row.printed_citation
    )


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_report_links(session: Session) -> int:
    plan = get_report_link_plan(session)
    key_to_planned_link = {
        (
            planned_link.source_report_id,
            planned_link.target_report_id,
            planned_link.link_type,
        ): planned_link
        for planned_link in plan.planned_links
    }
    report_link_rows = CRUDReportLink(session).get_rows()
    stored_keys = {
        (
            report_link_row.source_report_id,
            report_link_row.target_report_id,
            report_link_row.link_type,
        )
        for report_link_row in report_link_rows
    }
    planned_links_to_insert = [
        planned_link
        for key, planned_link in key_to_planned_link.items()
        if key not in stored_keys
    ]
    CRUDReportLink(session).add_many(_build_report_links(planned_links_to_insert))
    stale_count = sum(
        _is_report_link_row_stale(report_link_row, key_to_planned_link)
        for report_link_row in report_link_rows
    )
    logger.info(
        f"Report links: added {len(planned_links_to_insert)} rows, {stale_count} stored rows differ from the plan"
    )
    return stale_count

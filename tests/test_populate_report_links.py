from datetime import datetime

import pytest
from sqlalchemy import Connection, Engine, event
from sqlmodel import Session

from crud.report_link import CRUDReportLink
from database.report import Report
from database.report_link import ReportLink
from database.speech import Speech
from enums import ReportLinkRule, ReportLinkType, ReportType, ReportVersion
from exceptions import HansardWriteCheckError
from populate.report_links import (
    get_report_link_plan,
    populate_report_links,
    write_report_link_plan,
)

_SOURCE_REPORT_ID = "SOURCE#1"
_TARGET_REPORT_ID = "TARGET#1"
_TARGET_TITLE = "Title A"
_CITATION = (
    f'"{_TARGET_TITLE}", Official Report, 3 March 2020, Volume 94, Issue No 12, '
    "Written Answers section"
)
_TRANSCRIPT = f"[Please refer to {_CITATION}]"
_STALE_CITATION = "A citation the record no longer prints"
_FIRST_PLANNED_COUNT = 1


@pytest.fixture(autouse=True)
def _no_report_link_title_corrections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("populate.report_links.get_report_link_title_corrections", list)


def _add_report(
    session: Session,
    report_id: str,
    report_type: ReportType,
    sitting_date: datetime,
    title: str,
) -> Report:
    report = Report(
        volume_number=94,
        parliament_number=14,
        sitting_date=sitting_date,
        speech_number=1,
        original_title=title,
        title=title,
        report_id=report_id,
        report_type=report_type,
        content="Text.",
        report_version=ReportVersion.SPRS3,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _seed_citation(session: Session) -> None:
    source = _add_report(
        session,
        _SOURCE_REPORT_ID,
        ReportType.ORAL_ANSWER,
        datetime(2020, 3, 10),
        "Source title",
    )
    _add_report(
        session,
        _TARGET_REPORT_ID,
        ReportType.ORAL_ANSWER,
        datetime(2020, 3, 3),
        _TARGET_TITLE,
    )
    assert source.id is not None
    session.add(
        Speech(
            ordinal=1,
            speaker="Mr A",
            transcript=_TRANSCRIPT,
            sitting_date=source.sitting_date,
            report_type=source.report_type,
            report_id=source.id,
        )
    )
    session.commit()


def _build_stored_link(
    link_type: ReportLinkType,
    printed_citation: str,
    source_report_id: str = _SOURCE_REPORT_ID,
    target_report_id: str = _TARGET_REPORT_ID,
) -> ReportLink:
    return ReportLink(
        link_type=link_type,
        rule=ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE,
        printed_citation=printed_citation,
        source_report_id=source_report_id,
        target_report_id=target_report_id,
    )


def _get_stored_keys(session: Session) -> list[tuple[ReportLinkType, str, str, str]]:
    return [
        (
            report_link_row.link_type,
            report_link_row.source_report_id,
            report_link_row.target_report_id,
            report_link_row.printed_citation,
        )
        for report_link_row in CRUDReportLink(session).get_rows()
    ]


def test_a_first_populate_inserts_the_plan_and_a_second_adds_nothing(
    scratch_session: Session,
) -> None:
    _seed_citation(scratch_session)

    first_stale_count = populate_report_links(scratch_session)
    scratch_session.commit()
    stored_after_first = _get_stored_keys(scratch_session)
    second_stale_count = populate_report_links(scratch_session)
    scratch_session.commit()

    assert first_stale_count == 0
    assert second_stale_count == 0
    assert len(stored_after_first) == _FIRST_PLANNED_COUNT
    assert stored_after_first[0][:3] == (
        ReportLinkType.REPLY,
        _SOURCE_REPORT_ID,
        _TARGET_REPORT_ID,
    )
    assert _get_stored_keys(scratch_session) == stored_after_first


def test_a_stored_row_the_plan_lacks_stays_and_is_counted(
    scratch_session: Session,
) -> None:
    _seed_citation(scratch_session)
    stale_link = _build_stored_link(ReportLinkType.CORRECTION, _STALE_CITATION)
    CRUDReportLink(scratch_session).add_many([stale_link])
    scratch_session.commit()

    stale_count = populate_report_links(scratch_session)
    scratch_session.commit()

    assert stale_count == 1
    assert {stored_key[0] for stored_key in _get_stored_keys(scratch_session)} == {
        ReportLinkType.CORRECTION,
        ReportLinkType.REPLY,
    }


def test_a_stored_row_with_a_different_citation_stays_and_adds_no_second_row(
    scratch_session: Session,
) -> None:
    _seed_citation(scratch_session)
    CRUDReportLink(scratch_session).add_many(
        [_build_stored_link(ReportLinkType.REPLY, _STALE_CITATION)]
    )
    scratch_session.commit()

    stale_count = populate_report_links(scratch_session)
    scratch_session.commit()

    assert stale_count == 1
    assert _get_stored_keys(scratch_session) == [
        (
            ReportLinkType.REPLY,
            _SOURCE_REPORT_ID,
            _TARGET_REPORT_ID,
            _STALE_CITATION,
        )
    ]


def test_populate_inserts_the_planned_rows_and_issues_no_delete(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    _seed_citation(scratch_session)
    statements: list[str] = []

    def record_statement(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(scratch_engine, "before_cursor_execute", record_statement)
    try:
        populate_report_links(scratch_session)
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert any(statement.startswith("INSERT INTO report_link") for statement in statements)
    assert not [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("DELETE")
    ]
    assert len(_get_stored_keys(scratch_session)) == _FIRST_PLANNED_COUNT


def test_write_replaces_stored_rows_with_the_plan(scratch_session: Session) -> None:
    _seed_citation(scratch_session)
    CRUDReportLink(scratch_session).add_many(
        [_build_stored_link(ReportLinkType.CORRECTION, _STALE_CITATION)]
    )
    scratch_session.commit()

    write_report_link_plan(scratch_session, get_report_link_plan(scratch_session))
    scratch_session.commit()

    assert _get_stored_keys(scratch_session) == [
        (
            ReportLinkType.REPLY,
            _SOURCE_REPORT_ID,
            _TARGET_REPORT_ID,
            _CITATION,
        )
    ]


def test_write_refuses_a_short_delete_count_and_keeps_the_rows(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_citation(scratch_session)
    CRUDReportLink(scratch_session).add_many(
        [_build_stored_link(ReportLinkType.CORRECTION, _STALE_CITATION)]
    )
    scratch_session.commit()
    real_delete_all = CRUDReportLink.delete_all

    def delete_all_one_short(self: CRUDReportLink) -> int:
        return real_delete_all(self) - 1

    monkeypatch.setattr(CRUDReportLink, "delete_all", delete_all_one_short)
    plan = get_report_link_plan(scratch_session)

    with pytest.raises(HansardWriteCheckError, match="Deleted 0 report links, read 1"):
        write_report_link_plan(scratch_session, plan)

    scratch_session.rollback()
    assert _get_stored_keys(scratch_session) == [
        (
            ReportLinkType.CORRECTION,
            _SOURCE_REPORT_ID,
            _TARGET_REPORT_ID,
            _STALE_CITATION,
        )
    ]

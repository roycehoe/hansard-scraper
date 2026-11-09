from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, select

import populate.office_title_ministries as office_title_ministries_module
import scripts.apply_ministries as apply_ministries_script
from database.ministry import Ministry
from database.ministry_see_also import MinistrySeeAlso
from database.office_title_ministry import OfficeTitleMinistry
from database.report import Report
from database.report_put_to import ReportPutTo
from enums import (
    OfficeTitleMinistrySource,
    ReportPutToSource,
    ReportType,
    ReportVersion,
)
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from populate.office_title_ministries import populate_office_title_ministries
from schemas.ministry_list import MinistrySeeAlsoEntry
from scripts.apply_ministries import apply_ministries
from utils.data_files import get_ministry_names, get_ministry_see_also

_PARLIAMENT_NUMBER = 14
_SITTING_DATE = datetime(2025, 4, 2)
_HEALTH_TITLE = "Minister for Health"
_PRIME_MINISTER_TITLE = "Prime Minister"
_ROLE_ONLY_TITLE = "Minister"
_UNKNOWN_TITLE = "Minister for Nonsense"
_HALF_PLACED_TITLE = "Minister for Health and Minister for Nonsense"
_EDUCATION_TITLE = "Minister for Education"
_REMOVED_MINISTRY_NAME = "Defence"
_SEED_TITLES = (
    _HEALTH_TITLE,
    _PRIME_MINISTER_TITLE,
    _ROLE_ONLY_TITLE,
    _UNKNOWN_TITLE,
)
_PLAN_LOG = (
    f"Plan: {len(get_ministry_names())} ministries;"
    " 2 placements by source: CLOSED_LIST_RULE 1, HAND_KEPT_TITLE 1;"
    f" 1 role-only titles; 1 unplaced titles; {len(get_ministry_see_also())} see-also entries"
)
_UNPLACED_LOG = "Unplaced title: Minister for Nonsense"
_COMMIT_RUN_COUNT = 2
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _seed_put_to(session: Session, sprs_report_id: str, office_printed: str) -> Report:
    report = Report(
        volumeNo=_PARLIAMENT_NUMBER,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title=sprs_report_id,
        title=sprs_report_id,
        reportId=sprs_report_id,
        reportType=ReportType.ORAL_ANSWER,
        content=None,
        markdown_content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )
    session.add(report)
    session.flush()
    session.add(
        ReportPutTo(
            ordinal=1,
            office_printed=office_printed,
            printed_text=f"asked the {office_printed}",
            source=ReportPutToSource.ASKED_THE,
            first_ordinal=1,
            sprs_report_id=sprs_report_id,
        )
    )
    session.commit()
    return report


def _seed_reports(session: Session) -> list[Report]:
    return [
        _seed_put_to(session, f"report-{office_printed}", office_printed)
        for office_printed in _SEED_TITLES
    ]


def _get_ministry_name_to_id(session: Session) -> dict[str, int]:
    session.expire_all()
    return {
        ministry.name: ministry.id
        for ministry in session.exec(select(Ministry)).all()
        if ministry.id is not None
    }


def _get_stored_placements(session: Session) -> list[tuple]:
    session.expire_all()
    ministry_id_to_name = {
        ministry_id: ministry_name
        for ministry_name, ministry_id in _get_ministry_name_to_id(session).items()
    }
    return [
        (
            office_title_ministry.office_printed,
            office_title_ministry.ordinal,
            ministry_id_to_name[office_title_ministry.ministry_id],
            office_title_ministry.source,
        )
        for office_title_ministry in session.exec(
            select(OfficeTitleMinistry).order_by(
                OfficeTitleMinistry.office_printed, OfficeTitleMinistry.ordinal
            )
        ).all()
    ]


def _get_seed_placements() -> list[tuple]:
    return [
        (
            _HEALTH_TITLE,
            1,
            "Health",
            OfficeTitleMinistrySource.CLOSED_LIST_RULE,
        ),
        (
            _PRIME_MINISTER_TITLE,
            1,
            "Prime Minister's Office",
            OfficeTitleMinistrySource.HAND_KEPT_TITLE,
        ),
    ]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_ministries_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_ministries_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_reports(scratch_session)

    apply_ministries(is_commit=False)

    assert _PLAN_LOG in log_recorder.messages
    assert _UNPLACED_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_ministry_name_to_id(scratch_session) == {}
    assert _get_stored_placements(scratch_session) == []


def test_commit_writes_the_ministries_and_the_placed_titles(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_reports(scratch_session)

    apply_ministries(is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    assert sorted(_get_ministry_name_to_id(scratch_session)) == sorted(
        get_ministry_names()
    )
    assert _get_stored_placements(scratch_session) == _get_seed_placements()


def test_commit_on_a_rerun_leaves_the_same_rows_and_ministry_ids(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_reports(scratch_session)
    apply_ministries(is_commit=True)
    ministry_name_to_id = _get_ministry_name_to_id(scratch_session)

    apply_ministries(is_commit=True)

    assert log_recorder.messages.count(_PLAN_LOG) == _COMMIT_RUN_COUNT
    assert _get_ministry_name_to_id(scratch_session) == ministry_name_to_id
    assert _get_stored_placements(scratch_session) == _get_seed_placements()


def test_commit_deletes_a_ministry_removed_from_the_file_and_keeps_other_ids(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)
    apply_ministries(is_commit=True)
    ministry_name_to_id = _get_ministry_name_to_id(scratch_session)
    monkeypatch.setattr(
        office_title_ministries_module,
        "get_ministry_names",
        lambda: [
            ministry_name
            for ministry_name in get_ministry_names()
            if ministry_name != _REMOVED_MINISTRY_NAME
        ],
    )

    apply_ministries(is_commit=True)

    expected_ministry_name_to_id = dict(ministry_name_to_id)
    del expected_ministry_name_to_id[_REMOVED_MINISTRY_NAME]
    assert _get_ministry_name_to_id(scratch_session) == expected_ministry_name_to_id
    assert _get_stored_placements(scratch_session) == _get_seed_placements()


def test_commit_gives_a_title_with_an_unresolved_clause_no_row_at_all(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_put_to(scratch_session, "report-half-placed", _HALF_PLACED_TITLE)

    apply_ministries(is_commit=True)

    assert _get_stored_placements(scratch_session) == []
    assert f"Unplaced title: {_HALF_PLACED_TITLE}" in log_recorder.messages


def test_commit_refuses_a_see_also_entry_naming_an_unknown_ministry(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        office_title_ministries_module,
        "get_ministry_see_also",
        lambda: [
            MinistrySeeAlsoEntry(
                ministry_name="Health",
                see_also_ministry_name="Ministry Of Nowhere",
                note="Renamed",
                source_url="https://example.org/source",
            )
        ],
    )

    with pytest.raises(HansardWriteCheckError, match="Ministry Of Nowhere"):
        apply_ministries(is_commit=True)

    scratch_session.rollback()
    assert scratch_session.exec(select(MinistrySeeAlso)).all() == []


def test_populate_inserts_only_the_new_titles_of_the_window_and_issues_no_delete(
    scratch_engine: Engine, scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    apply_ministries(is_commit=True)
    education_report = _seed_put_to(
        scratch_session, "report-education", _EDUCATION_TITLE
    )
    report_ids = [
        report.id
        for report in [*seeded_reports, education_report]
        if report.id is not None
    ]
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
        unplaced_titles = populate_office_title_ministries(
            scratch_session, [], report_ids
        )
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert unplaced_titles == [_UNKNOWN_TITLE]
    assert any(
        statement.startswith("INSERT INTO office_title_ministry")
        for statement in statements
    )
    assert not [statement for statement in statements if statement.startswith("DELETE")]
    assert not [
        statement
        for statement in statements
        if statement.startswith(("INSERT INTO ministry ", "UPDATE ministry"))
    ]
    assert _get_stored_placements(scratch_session) == [
        (
            _EDUCATION_TITLE,
            1,
            "Education",
            OfficeTitleMinistrySource.CLOSED_LIST_RULE,
        ),
        *_get_seed_placements(),
    ]


def test_populate_returns_a_title_whose_ministry_is_missing_from_the_table(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_reports(scratch_session)
    apply_ministries(is_commit=True)
    education = scratch_session.exec(
        select(Ministry).where(Ministry.name == "Education")
    ).one()
    scratch_session.delete(education)
    scratch_session.commit()
    education_report = _seed_put_to(
        scratch_session, "report-education", _EDUCATION_TITLE
    )
    assert education_report.id is not None

    unplaced_titles = populate_office_title_ministries(
        scratch_session, [], [education_report.id]
    )
    scratch_session.commit()

    assert unplaced_titles == [_EDUCATION_TITLE]
    assert _get_stored_placements(scratch_session) == _get_seed_placements()


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)
    monkeypatch.setattr(
        apply_ministries_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_ministries(is_commit=True)

    assert _get_ministry_name_to_id(scratch_session) == {}

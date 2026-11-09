from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session

import scripts.apply_hand_kept_act_links as apply_hand_kept_act_links_script
from crud.act import CRUDAct
from crud.act_history_entry import CRUDActHistoryEntry
from crud.bill_report import CRUDBillReport
from database.act import Act, ActHistoryEntry
from enums import ActHistoryEntryKind, BillLinkSource, BillReportRole, ReportType
from exceptions import (
    HansardHandKeptEntryError,
    HansardWriteCheckError,
    HansardWriteTargetError,
)
from schemas.hand_kept_act_link import HandKeptActLink
from scripts.apply_hand_kept_act_links import (
    HandKeptRelabel,
    apply_hand_kept_act_links,
    get_hand_kept_relabels,
)
from tests.bill_seed import seed_bill, seed_bill_report

_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_FEEDING_STUFFS_TITLE = "Feeding Stuffs Ordinance, 1965"
_SECOND_TITLE = "Feeding Stuffs (Amendment) Ordinance, 1966"
_SSO_CODE = "FSA1965"
_FIRST_ORDINAL = 1
_SECOND_ORDINAL = 2
_THIRD_ORDINAL = 3
_MISSING_ORDINAL = 99
_FIRST_SITTING_DATE = datetime(1964, 11, 19)
_LAST_SITTING_DATE = datetime(1965, 6, 16)
_SEEDED_SPRS_REPORT_IDS = ("hk-first", "hk-third")


class _LogRecorder:
    def __init__(self):
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


@dataclass(frozen=True)
class _SeededEntries:
    similar_entry_id: int
    hand_kept_entry_id: int
    act_id: int
    bill_id: int
    report_ids: list[int]


def _seed_entries(session: Session) -> _SeededEntries:
    first_report_id = seed_bill_report(
        session,
        _SEEDED_SPRS_REPORT_IDS[0],
        ReportType.BILL,
        _FIRST_SITTING_DATE,
        "FEEDSTUFFS BILL",
        ["Bill read a first time."],
    )
    third_report_id = seed_bill_report(
        session,
        _SEEDED_SPRS_REPORT_IDS[1],
        ReportType.BILL,
        _LAST_SITTING_DATE,
        "FEEDSTUFFS BILL",
        ["Bill read a Third time and passed."],
    )
    bill_id = seed_bill(
        session,
        "FEEDSTUFFS BILL",
        {
            first_report_id: BillReportRole.READING,
            third_report_id: BillReportRole.READING,
        },
    )
    act = Act(sso_code=_SSO_CODE, title="Feeding Stuffs Act")
    session.add(act)
    session.flush()
    assert act.id is not None
    similar_entry = _build_entry(
        act.id,
        _FIRST_ORDINAL,
        _FEEDING_STUFFS_TITLE,
        BillLinkSource.SIMILAR_TITLE_READING_DATES,
        bill_id,
    )
    hand_kept_entry = _build_entry(
        act.id, _SECOND_ORDINAL, _SECOND_TITLE, BillLinkSource.HAND_KEPT, bill_id
    )
    session.add_all([similar_entry, hand_kept_entry])
    session.commit()
    assert similar_entry.id is not None
    assert hand_kept_entry.id is not None
    return _SeededEntries(
        similar_entry.id,
        hand_kept_entry.id,
        act.id,
        bill_id,
        [first_report_id, third_report_id],
    )


def _build_entry(
    act_id: int,
    ordinal: int,
    printed_title: str,
    bill_link_source: BillLinkSource,
    bill_id: int,
) -> ActHistoryEntry:
    return ActHistoryEntry(
        ordinal=ordinal,
        printed_text=printed_title,
        printed_law_number="1",
        printed_title=printed_title,
        kind=ActHistoryEntryKind.ORDINANCE,
        bill_link_source=bill_link_source,
        act_id=act_id,
        bill_id=bill_id,
    )


def _link(ordinal: int, printed_title: str, report_ids: list[int]) -> HandKeptActLink:
    return HandKeptActLink(
        sso_code=_SSO_CODE,
        ordinal=ordinal,
        printed_title=printed_title,
        report_ids=report_ids,
        reason="Test.",
    )


def _get_relabels(
    session: Session, links: list[HandKeptActLink]
) -> list[HandKeptRelabel]:
    return get_hand_kept_relabels(
        links,
        CRUDAct(session).get_rows(),
        CRUDActHistoryEntry(session).get_rows(),
        CRUDBillReport(session).get_rows(),
    )


def _get_stored_source(session: Session, entry_id: int) -> Optional[BillLinkSource]:
    session.expire_all()
    entry = session.get(ActHistoryEntry, entry_id)
    assert entry is not None
    return entry.bill_link_source


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_hand_kept_act_links_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_hand_kept_act_links_script, "logger", recorder)
    return recorder


@pytest.fixture
def seeded_entries(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> _SeededEntries:
    seeded_entries = _seed_entries(scratch_session)
    hand_kept_act_links = [
        _link(_FIRST_ORDINAL, _FEEDING_STUFFS_TITLE, seeded_entries.report_ids),
        _link(_SECOND_ORDINAL, _SECOND_TITLE, seeded_entries.report_ids),
    ]
    monkeypatch.setattr(
        apply_hand_kept_act_links_script,
        "get_hand_kept_act_links",
        lambda: hand_kept_act_links,
    )
    return seeded_entries


def test_the_plan_relabels_only_the_entry_that_is_not_yet_hand_kept(
    scratch_session: Session, seeded_entries: _SeededEntries
) -> None:
    relabels = _get_relabels(
        scratch_session,
        [
            _link(_FIRST_ORDINAL, _FEEDING_STUFFS_TITLE, seeded_entries.report_ids),
            _link(_SECOND_ORDINAL, _SECOND_TITLE, seeded_entries.report_ids),
        ],
    )

    assert len(relabels) == 1
    assert relabels[0].act_history_entry_id == seeded_entries.similar_entry_id
    assert relabels[0].ordinal == _FIRST_ORDINAL
    assert (
        relabels[0].stored_bill_link_source
        == BillLinkSource.SIMILAR_TITLE_READING_DATES
    )


def test_a_stored_title_that_differs_from_the_list_is_refused(
    scratch_session: Session, seeded_entries: _SeededEntries
) -> None:
    with pytest.raises(HansardHandKeptEntryError, match="stores"):
        _get_relabels(
            scratch_session,
            [_link(_FIRST_ORDINAL, "Another Ordinance", seeded_entries.report_ids)],
        )


def test_a_bill_that_holds_other_reports_than_the_list_is_refused(
    scratch_session: Session, seeded_entries: _SeededEntries
) -> None:
    with pytest.raises(HansardHandKeptEntryError, match="holds reports"):
        _get_relabels(
            scratch_session,
            [
                _link(
                    _FIRST_ORDINAL,
                    _FEEDING_STUFFS_TITLE,
                    seeded_entries.report_ids[:1],
                )
            ],
        )


def test_an_entry_the_harvest_never_stored_is_refused(
    scratch_session: Session, seeded_entries: _SeededEntries
) -> None:
    unknown_ordinal_link = _link(
        _MISSING_ORDINAL, _FEEDING_STUFFS_TITLE, seeded_entries.report_ids
    )
    unknown_act_link = HandKeptActLink(
        sso_code="XYZ1900",
        ordinal=_FIRST_ORDINAL,
        printed_title=_FEEDING_STUFFS_TITLE,
        report_ids=seeded_entries.report_ids,
        reason="Test.",
    )

    with pytest.raises(
        HansardHandKeptEntryError, match="is not a stored Legislative History entry"
    ):
        _get_relabels(scratch_session, [unknown_ordinal_link])
    with pytest.raises(
        HansardHandKeptEntryError, match="is not a stored Legislative History entry"
    ):
        _get_relabels(scratch_session, [unknown_act_link])


def test_an_entry_linked_to_no_bill_is_refused(
    scratch_session: Session, seeded_entries: _SeededEntries
) -> None:
    entry = scratch_session.get(ActHistoryEntry, seeded_entries.similar_entry_id)
    assert entry is not None
    entry.bill_id = None
    scratch_session.commit()

    with pytest.raises(HansardHandKeptEntryError, match="is linked to no bill"):
        _get_relabels(
            scratch_session,
            [_link(_FIRST_ORDINAL, _FEEDING_STUFFS_TITLE, seeded_entries.report_ids)],
        )


def test_dry_run_logs_the_pair_and_writes_nothing(
    scratch_session: Session,
    seeded_entries: _SeededEntries,
    log_recorder: _LogRecorder,
) -> None:
    apply_hand_kept_act_links(is_commit=False)

    assert (
        "FSA1965 1: SIMILAR_TITLE_READING_DATES -> HAND_KEPT" in log_recorder.messages
    )
    assert (
        "Plan: 1 of 2 hand-kept entries to relabel; "
        "1 stored entries carry SIMILAR_TITLE_READING_DATES"
    ) in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert (
        _get_stored_source(scratch_session, seeded_entries.similar_entry_id)
        == BillLinkSource.SIMILAR_TITLE_READING_DATES
    )


def test_commit_relabels_the_entry_and_leaves_the_bill_link(
    scratch_session: Session,
    seeded_entries: _SeededEntries,
    log_recorder: _LogRecorder,
) -> None:
    apply_hand_kept_act_links(is_commit=True)

    assert (
        _get_stored_source(scratch_session, seeded_entries.similar_entry_id)
        == BillLinkSource.HAND_KEPT
    )
    entry = scratch_session.get(ActHistoryEntry, seeded_entries.similar_entry_id)
    assert entry is not None
    assert entry.bill_id == seeded_entries.bill_id
    assert log_recorder.messages[-1] == "Committed"


def test_commit_on_a_rerun_writes_nothing(
    scratch_session: Session,
    seeded_entries: _SeededEntries,
    log_recorder: _LogRecorder,
) -> None:
    apply_hand_kept_act_links(is_commit=True)
    rows_after_first_run = CRUDActHistoryEntry(scratch_session).get_rows()
    log_recorder.messages.clear()

    apply_hand_kept_act_links(is_commit=True)

    assert (
        "Plan: 0 of 2 hand-kept entries to relabel; "
        "0 stored entries carry SIMILAR_TITLE_READING_DATES"
    ) in log_recorder.messages
    scratch_session.expire_all()
    assert CRUDActHistoryEntry(scratch_session).get_rows() == rows_after_first_run


def test_commit_refuses_a_similar_entry_the_list_does_not_name_and_keeps_the_rows(
    scratch_session: Session,
    seeded_entries: _SeededEntries,
    log_recorder: _LogRecorder,
) -> None:
    scratch_session.add(
        _build_entry(
            seeded_entries.act_id,
            _THIRD_ORDINAL,
            "Unlisted Ordinance, 1966",
            BillLinkSource.SIMILAR_TITLE_READING_DATES,
            seeded_entries.bill_id,
        )
    )
    scratch_session.commit()

    with pytest.raises(
        HansardWriteCheckError, match="still carry SIMILAR_TITLE_READING_DATES"
    ):
        apply_hand_kept_act_links(is_commit=True)

    scratch_session.rollback()
    assert (
        _get_stored_source(scratch_session, seeded_entries.similar_entry_id)
        == BillLinkSource.SIMILAR_TITLE_READING_DATES
    )


def test_commit_refuses_a_short_rowcount_and_keeps_the_rows(
    scratch_session: Session,
    seeded_entries: _SeededEntries,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        CRUDActHistoryEntry,
        "set_bill_link_sources_bulk",
        lambda self, act_history_entry_id_to_bill_link_source: 0,
    )

    with pytest.raises(HansardWriteCheckError, match="Relabelled 0 entries, planned 1"):
        apply_hand_kept_act_links(is_commit=True)

    assert (
        _get_stored_source(scratch_session, seeded_entries.similar_entry_id)
        == BillLinkSource.SIMILAR_TITLE_READING_DATES
    )


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    seeded_entries: _SeededEntries,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        apply_hand_kept_act_links_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_hand_kept_act_links(is_commit=True)

    assert (
        _get_stored_source(scratch_session, seeded_entries.similar_entry_id)
        == BillLinkSource.SIMILAR_TITLE_READING_DATES
    )


def test_set_bill_link_sources_bulk_updates_only_the_given_ids_and_returns_the_count(
    scratch_session: Session, scratch_engine: Engine
) -> None:
    seeded_entries = _seed_entries(scratch_session)
    untouched_entry = _build_entry(
        seeded_entries.act_id,
        _THIRD_ORDINAL,
        "Unlisted Ordinance, 1966",
        BillLinkSource.SIMILAR_TITLE_READING_DATES,
        seeded_entries.bill_id,
    )
    scratch_session.add(untouched_entry)
    scratch_session.commit()
    untouched_entry_id = untouched_entry.id
    assert untouched_entry_id is not None
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
        empty_count = CRUDActHistoryEntry(scratch_session).set_bill_link_sources_bulk(
            {}
        )
        assert empty_count == 0
        assert statements == []

        updated_count = CRUDActHistoryEntry(scratch_session).set_bill_link_sources_bulk(
            {seeded_entries.similar_entry_id: BillLinkSource.HAND_KEPT}
        )
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert updated_count == 1
    assert (
        _get_stored_source(scratch_session, seeded_entries.similar_entry_id)
        == BillLinkSource.HAND_KEPT
    )
    assert (
        _get_stored_source(scratch_session, untouched_entry_id)
        == BillLinkSource.SIMILAR_TITLE_READING_DATES
    )

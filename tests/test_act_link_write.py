from datetime import datetime
from typing import Optional

from sqlmodel import Session

from crud.act import ActRow
from crud.act_history_entry import ActHistoryEntryRow, CRUDActHistoryEntry
from crud.bill import BillRow, CRUDBill
from crud.bill_report import BillReportRow, CRUDBillReport
from enums import (
    ActHistoryEntryKind,
    ActNumberSource,
    BillLinkSource,
    BillReportRole,
    RepealedActUrlSource,
    ReportType,
)
from populate.act_links import get_act_link_write, write_act_link_plan
from schemas.act_link_plan import (
    ActLinkPlan,
    PlannedAct,
    PlannedActHistoryEntry,
    PlannedBill,
    PlannedBudgetReportLink,
)
from services.act_link_write import build_act_link_write, get_first_difference
from tests.bill_seed import seed_bill_report

_SITTING_DATE = datetime(2025, 1, 15)


def _bill(title_key: str, report_ids: list[int], is_passed: bool = True) -> PlannedBill:
    return PlannedBill(
        title=title_key,
        title_key=title_key,
        first_sitting_date=_SITTING_DATE,
        last_sitting_date=_SITTING_DATE,
        is_passed=is_passed,
        report_ids=report_ids,
        bill_number=None,
        bill_number_source=None,
        bill_class=None,
        act_number=None,
        act_number_source=None,
        repealed_act_url=None,
        repealed_act_url_source=None,
    )


def _budget_plan(
    bills: list[PlannedBill], budget_report_links: list[PlannedBudgetReportLink]
) -> ActLinkPlan:
    return _plan(bills, []).model_copy(
        update={"budget_report_links": budget_report_links}
    )


def _entry(ordinal: int, bill_index: Optional[int]) -> PlannedActHistoryEntry:
    return PlannedActHistoryEntry(
        ordinal=ordinal,
        printed_text=f"text {ordinal}",
        printed_law_number="Act 1",
        printed_title="Title",
        printed_bill_number=None,
        first_reading_date=None,
        second_reading_date=None,
        third_reading_date=None,
        commencement_date=None,
        kind=ActHistoryEntryKind.ACT,
        defects=[],
        bill_index=bill_index,
        bill_link_source=None
        if bill_index is None
        else BillLinkSource.FIRST_READING_DATE,
        bill_number_bill_index=None,
    )


def _plan(bills: list[PlannedBill], acts: list[PlannedAct]) -> ActLinkPlan:
    return ActLinkPlan(
        bills=bills,
        split_merges=[],
        skipped_reports=[],
        egazette_links=[],
        budget_report_links=[],
        budget_report_count=0,
        acts=acts,
        unfetched_sso_codes=[],
        unparsed_entries=[],
    )


def _seed_report_ids(session: Session, count: int) -> list[int]:
    return [
        seed_bill_report(
            session,
            f"report-{number}",
            ReportType.BILL,
            _SITTING_DATE,
            "Some Bill",
            ["Bill read a First time."],
        )
        for number in range(count)
    ]


def _write(session: Session, plan: ActLinkPlan) -> None:
    write_act_link_plan(session, plan, get_act_link_write(session, plan))
    session.flush()


def _get_entry_id_to_bill_report_ids(
    session: Session,
) -> dict[tuple[int, int], tuple[int, list[int]]]:
    bill_id_to_report_ids: dict[int, list[int]] = {}
    for bill_report_row in CRUDBillReport(session).get_rows():
        bill_id_to_report_ids.setdefault(bill_report_row.bill_id, []).append(
            bill_report_row.report_id
        )
    return {
        (entry_row.act_id, entry_row.ordinal): (
            entry_row.id,
            bill_id_to_report_ids.get(entry_row.bill_id or 0, []),
        )
        for entry_row in CRUDActHistoryEntry(session).get_rows()
    }


def test_two_bills_merging_move_their_entries_to_the_merged_bill(
    scratch_session: Session,
) -> None:
    first, second, third = _seed_report_ids(scratch_session, 3)
    first_plan = _plan(
        [_bill("a", [first]), _bill("b", [second]), _bill("c", [third])],
        [
            PlannedAct(
                sso_code="X",
                title="X",
                entries=[_entry(1, 0), _entry(2, 1), _entry(3, 2)],
            )
        ],
    )
    _write(scratch_session, first_plan)
    third_bill_id = next(
        bill_row.id
        for bill_row in CRUDBill(scratch_session).get_rows()
        if bill_row.title_key == "c"
    )
    entry_ids = [row.id for row in CRUDActHistoryEntry(scratch_session).get_rows()]
    second_plan = _plan(
        [_bill("ab", [first, second]), _bill("c", [third])],
        [
            PlannedAct(
                sso_code="X",
                title="X",
                entries=[_entry(1, 0), _entry(2, 0), _entry(3, 1)],
            )
        ],
    )

    _write(scratch_session, second_plan)

    bill_rows = CRUDBill(scratch_session).get_rows()
    assert [bill_row.title_key for bill_row in bill_rows] == ["c", "ab"]
    assert bill_rows[0].id == third_bill_id
    (stored_bill_report_row,) = [
        bill_report_row
        for bill_report_row in CRUDBillReport(scratch_session).get_rows()
        if bill_report_row.bill_id == third_bill_id
    ]
    assert stored_bill_report_row.report_id == third
    entry_rows = CRUDActHistoryEntry(scratch_session).get_rows()
    assert [row.id for row in entry_rows] == entry_ids
    assert entry_rows[0].bill_id == entry_rows[1].bill_id == bill_rows[1].id
    assert entry_rows[2].bill_id == third_bill_id
    assert (
        get_first_difference(get_act_link_write(scratch_session, second_plan)) is None
    )


def test_an_entry_relinked_to_another_bill_keeps_its_id(
    scratch_session: Session,
) -> None:
    first, second = _seed_report_ids(scratch_session, 2)
    bills = [_bill("a", [first]), _bill("b", [second])]
    _write(
        scratch_session,
        _plan(
            bills,
            [PlannedAct(sso_code="X", title="X", entries=[_entry(1, 0), _entry(2, 0)])],
        ),
    )
    before = CRUDActHistoryEntry(scratch_session).get_rows()
    relinked_plan = _plan(
        bills,
        [PlannedAct(sso_code="X", title="X", entries=[_entry(1, 0), _entry(2, 1)])],
    )
    act_link_write = get_act_link_write(scratch_session, relinked_plan)

    assert [
        entry_update.is_bill_changed for entry_update in act_link_write.entry_updates
    ] == [True]
    _write(scratch_session, relinked_plan)

    after = CRUDActHistoryEntry(scratch_session).get_rows()
    assert [row.id for row in after] == [row.id for row in before]
    assert after[0] == before[0]
    assert after[1].bill_id != before[1].bill_id
    assert after[1].bill_id == CRUDBill(scratch_session).get_rows()[1].id


def test_an_act_added_and_an_act_removed(scratch_session: Session) -> None:
    (first,) = _seed_report_ids(scratch_session, 1)
    bills = [_bill("a", [first])]
    _write(
        scratch_session,
        _plan(
            bills,
            [
                PlannedAct(sso_code="OLD", title="Old", entries=[_entry(1, 0)]),
                PlannedAct(sso_code="KEEP", title="Keep", entries=[_entry(1, 0)]),
            ],
        ),
    )
    stored_before = {
        entry_row.act_id: entry_row.id
        for entry_row in CRUDActHistoryEntry(scratch_session).get_rows()
    }
    changed_plan = _plan(
        bills,
        [
            PlannedAct(sso_code="KEEP", title="Keep", entries=[_entry(1, 0)]),
            PlannedAct(sso_code="NEW", title="New", entries=[_entry(1, None)]),
        ],
    )

    _write(scratch_session, changed_plan)

    entry_rows = CRUDActHistoryEntry(scratch_session).get_rows()
    assert [entry_row.act_id for entry_row in entry_rows] == sorted(
        {entry_row.act_id for entry_row in entry_rows}
    )
    assert len(entry_rows) > 1
    assert entry_rows[0].id in stored_before.values()
    assert entry_rows[1].bill_id is None
    assert (
        get_first_difference(get_act_link_write(scratch_session, changed_plan)) is None
    )


def test_writing_the_same_plan_twice_changes_nothing(scratch_session: Session) -> None:
    first, second = _seed_report_ids(scratch_session, 2)
    plan = _plan(
        [_bill("a", [first]), _bill("b", [second])],
        [PlannedAct(sso_code="X", title="X", entries=[_entry(1, 0), _entry(2, 1)])],
    )
    _write(scratch_session, plan)
    bills_before = CRUDBill(scratch_session).get_rows()
    entries_before = CRUDActHistoryEntry(scratch_session).get_rows()

    act_link_write = get_act_link_write(scratch_session, plan)
    _write(scratch_session, plan)

    assert act_link_write.bill_indexes_to_insert == []
    assert act_link_write.bill_updates == []
    assert act_link_write.entries_to_insert == []
    assert act_link_write.entry_updates == []
    assert get_first_difference(act_link_write) is None
    assert CRUDBill(scratch_session).get_rows() == bills_before
    assert CRUDActHistoryEntry(scratch_session).get_rows() == entries_before


def _stored_bill(bill_id: int, title: str = "a") -> BillRow:
    return BillRow(
        bill_id,
        title,
        title,
        _SITTING_DATE,
        _SITTING_DATE,
        True,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def _stored_entry(
    entry_id: int, act_id: int, ordinal: int, bill_id: Optional[int]
) -> ActHistoryEntryRow:
    planned_entry = _entry(ordinal, None if bill_id is None else 0)
    return ActHistoryEntryRow(
        entry_id,
        act_id,
        ordinal,
        planned_entry.printed_text,
        planned_entry.printed_law_number,
        planned_entry.printed_title,
        None,
        None,
        None,
        None,
        None,
        planned_entry.kind,
        planned_entry.bill_link_source,
        bill_id,
    )


def test_diff_keeps_updates_inserts_and_deletes_apart() -> None:
    plan = _plan(
        [_bill("a2", [1]), _bill("new", [9])],
        [
            PlannedAct(sso_code="X", title="X2", entries=[_entry(1, 0), _entry(3, 1)]),
            PlannedAct(sso_code="N", title="N", entries=[]),
        ],
    )

    act_link_write = build_act_link_write(
        [_stored_bill(10), _stored_bill(11, "gone")],
        [
            BillReportRow(1, 10, 1, BillReportRole.READING),
            BillReportRow(2, 11, 2, BillReportRole.READING),
        ],
        [ActRow(5, "X", "X"), ActRow(6, "Z", "Z")],
        [
            _stored_entry(100, 5, 1, 10),
            _stored_entry(101, 5, 2, 11),
            _stored_entry(102, 6, 1, None),
        ],
        [],
        plan,
    )

    assert act_link_write.kept_bill_index_to_id == {0: 10}
    assert [bill_update.title for bill_update in act_link_write.bill_updates] == ["a2"]
    assert act_link_write.bill_indexes_to_insert == [1]
    assert act_link_write.bill_ids_to_delete == [11]
    assert [planned_act.sso_code for planned_act in act_link_write.acts_to_insert] == [
        "N"
    ]
    assert [act_update.id for act_update in act_link_write.act_updates] == [5]
    assert act_link_write.act_ids_to_delete == [6]
    assert [
        (insert.sso_code, insert.planned_entry.ordinal)
        for insert in act_link_write.entries_to_insert
    ] == [("X", 3)]
    assert act_link_write.entry_updates == []
    assert act_link_write.entry_ids_to_delete == [101, 102]
    assert get_first_difference(act_link_write) == "Planned bill 1 is not stored"


def test_diff_updates_an_entry_whose_bill_is_new() -> None:
    plan = _plan(
        [_bill("a", [1]), _bill("b", [2])],
        [PlannedAct(sso_code="X", title="X", entries=[_entry(1, 1)])],
    )

    act_link_write = build_act_link_write(
        [_stored_bill(10)],
        [BillReportRow(1, 10, 1, BillReportRole.READING)],
        [ActRow(5, "X", "X")],
        [_stored_entry(100, 5, 1, 10)],
        [],
        plan,
    )

    assert [
        (update.id, update.is_bill_changed) for update in act_link_write.entry_updates
    ] == [(100, True)]


def test_diff_updates_a_bill_whose_act_number_changes() -> None:
    planned_bill = _bill("a", [1]).model_copy(
        update={
            "act_number": "7/2025",
            "act_number_source": ActNumberSource.ACTS_SUPPLEMENT_LISTING,
        }
    )

    act_link_write = build_act_link_write(
        [_stored_bill(10)],
        [BillReportRow(1, 10, 1, BillReportRole.READING)],
        [],
        [],
        [],
        _plan([planned_bill], []),
    )

    assert [
        (bill_update.id, bill_update.act_number, bill_update.act_number_source)
        for bill_update in act_link_write.bill_updates
    ] == [(10, "7/2025", ActNumberSource.ACTS_SUPPLEMENT_LISTING)]
    assert get_first_difference(act_link_write) == (
        "Stored bill 10 differs from the plan"
    )


def test_diff_updates_a_bill_whose_repealed_act_url_changes() -> None:
    planned_bill = _bill("a", [1]).model_copy(
        update={
            "repealed_act_url": "https://sso.agc.gov.sg/Act/AA1987/Repealed/20200101",
            "repealed_act_url_source": RepealedActUrlSource.REPEALED_ACTS_LISTING,
        }
    )

    act_link_write = build_act_link_write(
        [_stored_bill(10)],
        [BillReportRow(1, 10, 1, BillReportRole.READING)],
        [],
        [],
        [],
        _plan([planned_bill], []),
    )

    assert [
        (
            bill_update.id,
            bill_update.repealed_act_url,
            bill_update.repealed_act_url_source,
        )
        for bill_update in act_link_write.bill_updates
    ] == [
        (
            10,
            "https://sso.agc.gov.sg/Act/AA1987/Repealed/20200101",
            RepealedActUrlSource.REPEALED_ACTS_LISTING,
        )
    ]
    assert get_first_difference(act_link_write) == (
        "Stored bill 10 differs from the plan"
    )


def test_a_new_budget_link_is_inserted_with_the_budget_debate_role(
    scratch_session: Session,
) -> None:
    reading, budget = _seed_report_ids(scratch_session, 2)
    bills = [_bill("supplybill", [reading])]
    _write(scratch_session, _budget_plan(bills, []))
    bill_id = CRUDBill(scratch_session).get_rows()[0].id
    plan = _budget_plan(
        bills, [PlannedBudgetReportLink(report_id=budget, bill_index=0)]
    )

    act_link_write = get_act_link_write(scratch_session, plan)

    assert [
        (insert.bill_index, insert.report_id)
        for insert in act_link_write.budget_report_inserts
    ] == [(0, budget)]
    assert get_first_difference(act_link_write) == (
        f"Planned budget report {budget} link to bill 0 is not stored"
    )
    _write(scratch_session, plan)
    assert [
        (row.bill_id, row.report_id, row.role)
        for row in CRUDBillReport(scratch_session).get_rows()
    ] == [
        (bill_id, reading, BillReportRole.READING),
        (bill_id, budget, BillReportRole.BUDGET_DEBATE),
    ]
    assert get_first_difference(get_act_link_write(scratch_session, plan)) is None


def test_a_stored_budget_link_the_plan_lacks_is_deleted(
    scratch_session: Session,
) -> None:
    reading, budget = _seed_report_ids(scratch_session, 2)
    bills = [_bill("supplybill", [reading])]
    _write(
        scratch_session,
        _budget_plan(bills, [PlannedBudgetReportLink(report_id=budget, bill_index=0)]),
    )
    empty_plan = _budget_plan(bills, [])

    act_link_write = get_act_link_write(scratch_session, empty_plan)

    assert len(act_link_write.budget_report_ids_to_delete) == 1
    assert get_first_difference(act_link_write) is not None
    _write(scratch_session, empty_plan)
    assert [row.role for row in CRUDBillReport(scratch_session).get_rows()] == [
        BillReportRole.READING
    ]


def test_a_kept_reading_set_keeps_its_bill_id_when_a_budget_row_is_added(
    scratch_session: Session,
) -> None:
    reading, budget = _seed_report_ids(scratch_session, 2)
    bills = [_bill("supplybill", [reading])]
    _write(scratch_session, _budget_plan(bills, []))
    bill_id_before = CRUDBill(scratch_session).get_rows()[0].id
    plan = _budget_plan(
        bills, [PlannedBudgetReportLink(report_id=budget, bill_index=0)]
    )
    _write(scratch_session, plan)

    act_link_write = get_act_link_write(scratch_session, plan)

    assert act_link_write.kept_bill_index_to_id == {0: bill_id_before}
    assert act_link_write.bill_indexes_to_insert == []
    assert [row.id for row in CRUDBill(scratch_session).get_rows()] == [bill_id_before]


def test_the_first_difference_names_a_missing_budget_row() -> None:
    plan = _budget_plan(
        [_bill("a", [1])], [PlannedBudgetReportLink(report_id=7, bill_index=0)]
    )

    act_link_write = build_act_link_write(
        [_stored_bill(10)],
        [BillReportRow(1, 10, 1, BillReportRole.READING)],
        [],
        [],
        [],
        plan,
    )

    assert get_first_difference(act_link_write) == (
        "Planned budget report 7 link to bill 0 is not stored"
    )


def test_a_stored_budget_row_does_not_change_the_bill_identity() -> None:
    plan = _budget_plan(
        [_bill("a", [1])], [PlannedBudgetReportLink(report_id=7, bill_index=0)]
    )

    act_link_write = build_act_link_write(
        [_stored_bill(10)],
        [
            BillReportRow(1, 10, 1, BillReportRole.READING),
            BillReportRow(2, 10, 7, BillReportRole.BUDGET_DEBATE),
        ],
        [],
        [],
        [],
        plan,
    )

    assert act_link_write.kept_bill_index_to_id == {0: 10}
    assert act_link_write.budget_report_inserts == []
    assert act_link_write.budget_report_ids_to_delete == []
    assert get_first_difference(act_link_write) is None

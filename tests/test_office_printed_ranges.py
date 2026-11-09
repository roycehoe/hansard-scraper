import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, select

from crud.attendance_office import AttendanceOfficeSittingRow
from crud.office_printed_range import OfficePrintedRangeRow
from database.attendance import Attendance
from database.office_printed_range import OfficePrintedRange
from database.sitting import Sitting
from database.speaker import Speaker
from enums import AttendanceOfficeSource, OfficeClass
from populate.attendance_offices import populate_attendance_offices
from populate.office_printed_ranges import (
    get_office_printed_range_plan,
    populate_office_printed_ranges,
    write_office_printed_range_plan,
)
from services.office_printed_range import (
    build_office_printed_ranges,
    get_office_printed_range_changes,
)
from utils.sitting_dates import get_sitting_date_key

_FINANCE = "Minister for Finance"
_DEFENCE = "Minister for Defence"
_BUILT_AT = datetime(2026, 11, 9, tzinfo=timezone.utc)
_LATER_BUILT_AT = datetime(2026, 11, 10, tzinfo=timezone.utc)
_SORTED_SITTING_DATES = [datetime(2025, 3, day) for day in range(1, 8)]
_SENIOR_MINISTER_OF_STATE = "Senior Minister of State for Finance"
_PARLIAMENT_NUMBER = 14
_SITTING_DAYS = (1, 2, 3)
_FIRST_SPEAKER_ID = 10
_SECOND_SPEAKER_ID = 20
_FIRST_TWO_SITTINGS_COUNT = 2
_ALL_THREE_SITTINGS_COUNT = 3
_DEFENCE_SITTINGS = 37
_FINANCE_SITTINGS = 3
_SITTING_COUNT = 80
_STORED_RANGE_ID = 7
_LAST_ROW_ID = 4


def _build_row(
    row_id: int,
    day: int,
    speaker_id: Optional[int],
    office_printed: str = _FINANCE,
) -> AttendanceOfficeSittingRow:
    return AttendanceOfficeSittingRow(
        id=row_id,
        sitting_id=day,
        sitting_date=f"{day}-3-2025",
        speaker_id=speaker_id,
        office_printed=office_printed,
        office_class=OfficeClass.MINISTER,
        entry_line_printed=f"line {row_id}",
        source=AttendanceOfficeSource.AFTER_CONSTITUENCY_BRACKET,
    )


def _build_range_row(
    row_id: int,
    speaker_id: int,
    first_day: int,
    last_day: int,
    sitting_count: int,
    office_printed: str = _FINANCE,
) -> OfficePrintedRangeRow:
    return OfficePrintedRangeRow(
        id=row_id,
        speaker_id=speaker_id,
        office_printed=office_printed,
        sitting_count=sitting_count,
        first_sitting_date=datetime(2025, 3, first_day),
        last_sitting_date=datetime(2025, 3, last_day),
    )


def test_three_sittings_of_one_text_make_one_range() -> None:
    rows = [_build_row(row_id, row_id, _FIRST_SPEAKER_ID) for row_id in (1, 2, 3)]

    office_printed_ranges = build_office_printed_ranges(
        rows, _SORTED_SITTING_DATES, _BUILT_AT
    )

    assert len(office_printed_ranges) == 1
    office_printed_range = office_printed_ranges[0]
    assert office_printed_range.sitting_count == _ALL_THREE_SITTINGS_COUNT
    assert office_printed_range.first_attendance_office_id == 1
    assert office_printed_range.last_attendance_office_id == _ALL_THREE_SITTINGS_COUNT
    assert office_printed_range.first_sitting_date == datetime(2025, 3, 1)
    assert office_printed_range.last_sitting_date == datetime(2025, 3, 3)
    assert office_printed_range.speaker_id == _FIRST_SPEAKER_ID
    assert office_printed_range.office_class == OfficeClass.MINISTER
    assert office_printed_range.built_at == _BUILT_AT


def test_other_text_in_the_middle_gives_three_ranges() -> None:
    rows = [
        _build_row(1, 1, _FIRST_SPEAKER_ID, _FINANCE),
        _build_row(2, 2, _FIRST_SPEAKER_ID, _DEFENCE),
        _build_row(3, 3, _FIRST_SPEAKER_ID, _FINANCE),
    ]

    office_printed_ranges = build_office_printed_ranges(
        rows, _SORTED_SITTING_DATES, _BUILT_AT
    )

    assert [
        office_printed_range.office_printed for office_printed_range in office_printed_ranges
    ] == [_FINANCE, _DEFENCE, _FINANCE]


def test_a_middle_sitting_with_no_row_gives_two_ranges() -> None:
    rows = [
        _build_row(1, 1, _FIRST_SPEAKER_ID),
        _build_row(3, 3, _FIRST_SPEAKER_ID),
    ]

    office_printed_ranges = build_office_printed_ranges(
        rows, _SORTED_SITTING_DATES, _BUILT_AT
    )

    assert [
        office_printed_range.sitting_count for office_printed_range in office_printed_ranges
    ] == [1, 1]


def test_a_single_sitting_gives_a_one_sitting_range() -> None:
    office_printed_ranges = build_office_printed_ranges(
        [_build_row(1, 4, _FIRST_SPEAKER_ID)], _SORTED_SITTING_DATES, _BUILT_AT
    )

    assert len(office_printed_ranges) == 1
    assert office_printed_ranges[0].sitting_count == 1
    assert office_printed_ranges[0].first_sitting_date == datetime(2025, 3, 4)
    assert office_printed_ranges[0].last_sitting_date == datetime(2025, 3, 4)


def test_two_speakers_never_join() -> None:
    rows = [
        _build_row(1, 1, _FIRST_SPEAKER_ID),
        _build_row(2, 2, _SECOND_SPEAKER_ID),
    ]

    office_printed_ranges = build_office_printed_ranges(
        rows, _SORTED_SITTING_DATES, _BUILT_AT
    )

    assert [
        office_printed_range.speaker_id for office_printed_range in office_printed_ranges
    ] == [_FIRST_SPEAKER_ID, _SECOND_SPEAKER_ID]


def test_a_row_with_no_speaker_id_is_skipped() -> None:
    rows = [_build_row(1, 1, None), _build_row(2, 2, _FIRST_SPEAKER_ID)]

    office_printed_ranges = build_office_printed_ranges(
        rows, _SORTED_SITTING_DATES, _BUILT_AT
    )

    assert [
        office_printed_range.first_attendance_office_id
        for office_printed_range in office_printed_ranges
    ] == [2]


def test_a_window_run_extends_the_range_that_ends_the_sitting_before() -> None:
    range_rows = [_build_range_row(_STORED_RANGE_ID, _FIRST_SPEAKER_ID, 1, 2, _FIRST_TWO_SITTINGS_COUNT)]
    rows = [_build_row(3, 3, _FIRST_SPEAKER_ID), _build_row(_LAST_ROW_ID, 4, _FIRST_SPEAKER_ID)]

    changes = get_office_printed_range_changes(
        rows, range_rows, _SORTED_SITTING_DATES, _LATER_BUILT_AT
    )

    assert changes.office_printed_ranges == []
    assert len(changes.office_printed_range_updates) == 1
    office_printed_range_update = changes.office_printed_range_updates[0]
    assert office_printed_range_update.id == _STORED_RANGE_ID
    assert office_printed_range_update.last_attendance_office_id == _LAST_ROW_ID
    assert office_printed_range_update.last_sitting_date == datetime(2025, 3, 4)
    assert office_printed_range_update.sitting_count == _FIRST_TWO_SITTINGS_COUNT + 2
    assert office_printed_range_update.built_at == _LATER_BUILT_AT


def test_a_window_run_with_other_text_is_a_new_range() -> None:
    range_rows = [_build_range_row(_STORED_RANGE_ID, _FIRST_SPEAKER_ID, 1, 2, _FIRST_TWO_SITTINGS_COUNT)]
    rows = [_build_row(3, 3, _FIRST_SPEAKER_ID, _DEFENCE)]

    changes = get_office_printed_range_changes(
        rows, range_rows, _SORTED_SITTING_DATES, _LATER_BUILT_AT
    )

    assert len(changes.office_printed_ranges) == 1
    assert changes.office_printed_range_updates == []


def test_a_window_run_after_a_sitting_with_no_row_is_a_new_range() -> None:
    range_rows = [_build_range_row(_STORED_RANGE_ID, _FIRST_SPEAKER_ID, 1, 2, _FIRST_TWO_SITTINGS_COUNT)]
    rows = [_build_row(4, 4, _FIRST_SPEAKER_ID)]

    changes = get_office_printed_range_changes(
        rows, range_rows, _SORTED_SITTING_DATES, _LATER_BUILT_AT
    )

    assert len(changes.office_printed_ranges) == 1
    assert changes.office_printed_range_updates == []


def test_only_the_first_window_run_of_a_speaker_can_extend() -> None:
    range_rows = [_build_range_row(_STORED_RANGE_ID, _FIRST_SPEAKER_ID, 1, 2, _FIRST_TWO_SITTINGS_COUNT)]
    rows = [
        _build_row(3, 3, _FIRST_SPEAKER_ID),
        _build_row(5, 5, _FIRST_SPEAKER_ID),
    ]

    changes = get_office_printed_range_changes(
        rows, range_rows, _SORTED_SITTING_DATES, _LATER_BUILT_AT
    )

    assert len(changes.office_printed_range_updates) == 1
    assert len(changes.office_printed_ranges) == 1
    assert changes.office_printed_ranges[0].first_sitting_date == datetime(2025, 3, 5)


def test_a_run_at_the_first_sitting_is_a_new_range() -> None:
    range_rows = [_build_range_row(_STORED_RANGE_ID, _FIRST_SPEAKER_ID, 2, 3, _FIRST_TWO_SITTINGS_COUNT)]
    rows = [_build_row(1, 1, _FIRST_SPEAKER_ID)]

    changes = get_office_printed_range_changes(
        rows, range_rows, _SORTED_SITTING_DATES, _LATER_BUILT_AT
    )

    assert len(changes.office_printed_ranges) == 1
    assert changes.office_printed_range_updates == []


def test_a_speaker_who_prints_finance_defence_then_finance_gets_three_lines() -> None:
    sorted_sitting_dates = [
        datetime(2025, 1, 1) + timedelta(days=day) for day in range(_SITTING_COUNT)
    ]
    office_printed_by_position = (
        [_FINANCE] * _FINANCE_SITTINGS
        + [_DEFENCE] * _DEFENCE_SITTINGS
        + [_FINANCE] * _FINANCE_SITTINGS
    )
    rows = [
        AttendanceOfficeSittingRow(
            id=position + 1,
            sitting_id=position + 1,
            sitting_date=get_sitting_date_key(sorted_sitting_dates[position].date()),
            speaker_id=_SECOND_SPEAKER_ID,
            office_printed=office_printed,
            office_class=OfficeClass.MINISTER,
            entry_line_printed="line",
            source=AttendanceOfficeSource.AFTER_CONSTITUENCY_BRACKET,
        )
        for position, office_printed in enumerate(office_printed_by_position)
    ]

    office_printed_ranges = build_office_printed_ranges(
        rows, sorted_sitting_dates, _BUILT_AT
    )

    assert [
        (office_printed_range.office_printed, office_printed_range.sitting_count)
        for office_printed_range in office_printed_ranges
    ] == [
        (_FINANCE, _FINANCE_SITTINGS),
        (_DEFENCE, _DEFENCE_SITTINGS),
        (_FINANCE, _FINANCE_SITTINGS),
    ]


def _build_entry_line(name: str, office: Optional[str]) -> str:
    if office is None:
        return f"Mr {name} (Bishan-Toa Payoh)."
    return f"Mr {name} (Bishan-Toa Payoh), {office}."


def _seed_three_sittings(
    session: Session, entry_lines_by_day: dict[int, list[str]], listed_names_by_day: dict[int, list[str]]
) -> list[int]:
    chee = Speaker(
        name="Chee Hong Tat",
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    goh = Speaker(
        name="Goh Chok Tong",
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    session.add_all([chee, goh])
    sittings = [
        Sitting(
            sitting_date=f"{day}-3-2025",
            parlement_no=_PARLIAMENT_NUMBER,
            attendance_list=json.dumps(
                [
                    {"mpName": entry_line, "attendance": True}
                    for entry_line in entry_lines_by_day[day]
                ]
            ),
        )
        for day in _SITTING_DAYS
    ]
    session.add_all(sittings)
    session.flush()
    name_to_speaker_id = {"Chee Hong Tat": chee.id, "Goh Chok Tong": goh.id}
    for day, sitting in zip(_SITTING_DAYS, sittings):
        assert sitting.id is not None
        session.add_all(
            [
                Attendance(
                    sitting_id=sitting.id,
                    speaker_name=name,
                    is_present=True,
                    speaker_id=name_to_speaker_id[name],
                )
                for name in listed_names_by_day[day]
            ]
        )
    session.flush()
    return [sitting.id for sitting in sittings if sitting.id is not None]


def _get_stored_ranges(session: Session) -> list[OfficePrintedRange]:
    return list(
        session.exec(
            select(OfficePrintedRange).order_by(
                OfficePrintedRange.speaker_id, OfficePrintedRange.first_sitting_date
            )
        ).all()
    )


def test_a_listed_member_who_prints_no_office_at_the_middle_sitting_gives_two_ranges(
    scratch_session: Session,
) -> None:
    chee_with_office = _build_entry_line("Chee Hong Tat", _SENIOR_MINISTER_OF_STATE)
    sitting_ids = _seed_three_sittings(
        scratch_session,
        {
            1: [chee_with_office],
            2: [_build_entry_line("Chee Hong Tat", None)],
            3: [chee_with_office],
        },
        {1: ["Chee Hong Tat"], 2: ["Chee Hong Tat"], 3: ["Chee Hong Tat"]},
    )
    populate_attendance_offices(scratch_session, sitting_ids)

    plan = get_office_printed_range_plan(scratch_session)

    assert [
        office_printed_range.sitting_count for office_printed_range in plan.office_printed_ranges
    ] == [1, 1]
    assert plan.rows_without_speaker_id == 0


def test_a_member_not_listed_at_the_middle_sitting_gives_two_ranges(
    scratch_session: Session,
) -> None:
    goh_with_office = _build_entry_line("Goh Chok Tong", _FINANCE)
    sitting_ids = _seed_three_sittings(
        scratch_session,
        {1: [goh_with_office], 2: [], 3: [goh_with_office]},
        {1: ["Goh Chok Tong"], 2: [], 3: ["Goh Chok Tong"]},
    )
    populate_attendance_offices(scratch_session, sitting_ids)

    plan = get_office_printed_range_plan(scratch_session)

    assert [
        office_printed_range.sitting_count for office_printed_range in plan.office_printed_ranges
    ] == [1, 1]


def test_write_stores_the_planned_ranges_and_checks_them(
    scratch_session: Session,
) -> None:
    chee_with_office = _build_entry_line("Chee Hong Tat", _SENIOR_MINISTER_OF_STATE)
    sitting_ids = _seed_three_sittings(
        scratch_session,
        {1: [chee_with_office], 2: [chee_with_office], 3: [chee_with_office]},
        {day: ["Chee Hong Tat"] for day in _SITTING_DAYS},
    )
    populate_attendance_offices(scratch_session, sitting_ids)

    write_office_printed_range_plan(
        scratch_session, get_office_printed_range_plan(scratch_session)
    )

    stored_ranges = _get_stored_ranges(scratch_session)
    assert [stored_range.sitting_count for stored_range in stored_ranges] == [
        _ALL_THREE_SITTINGS_COUNT
    ]


def test_populate_extends_a_stored_range_and_issues_no_delete(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    chee_with_office = _build_entry_line("Chee Hong Tat", _SENIOR_MINISTER_OF_STATE)
    sitting_ids = _seed_three_sittings(
        scratch_session,
        {1: [chee_with_office], 2: [chee_with_office], 3: [chee_with_office]},
        {day: ["Chee Hong Tat"] for day in _SITTING_DAYS},
    )
    first_sitting_ids = sitting_ids[:_FIRST_TWO_SITTINGS_COUNT]
    last_sitting_ids = sitting_ids[_FIRST_TWO_SITTINGS_COUNT:]
    populate_attendance_offices(scratch_session, first_sitting_ids)
    populate_office_printed_ranges(scratch_session, first_sitting_ids)
    populate_attendance_offices(scratch_session, last_sitting_ids)
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
        late_sitting_dates = populate_office_printed_ranges(
            scratch_session, last_sitting_ids
        )
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert late_sitting_dates == []
    assert not [
        statement for statement in statements if statement.startswith("DELETE")
    ]
    stored_ranges = _get_stored_ranges(scratch_session)
    assert [stored_range.sitting_count for stored_range in stored_ranges] == [
        _ALL_THREE_SITTINGS_COUNT
    ]
    assert stored_ranges[0].last_sitting_date == datetime(2025, 3, 3)


def test_populate_returns_a_late_sitting_and_writes_no_range(
    scratch_session: Session,
) -> None:
    chee_with_office = _build_entry_line("Chee Hong Tat", _SENIOR_MINISTER_OF_STATE)
    sitting_ids = _seed_three_sittings(
        scratch_session,
        {1: [chee_with_office], 2: [chee_with_office], 3: [chee_with_office]},
        {day: ["Chee Hong Tat"] for day in _SITTING_DAYS},
    )
    populate_attendance_offices(scratch_session, sitting_ids)

    late_sitting_dates = populate_office_printed_ranges(
        scratch_session, sitting_ids[:1]
    )

    assert late_sitting_dates == ["1-3-2025"]
    assert _get_stored_ranges(scratch_session) == []

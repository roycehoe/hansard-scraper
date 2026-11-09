from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session

import scripts.build_leave_seat_check_packets as packets_script
from crud.leave_period_printing import (
    CRUDLeavePeriodPrinting,
    LeavePeriodPrintingCheckRow,
)
from crud.seat_holding import CRUDSeatHolding, SeatHoldingCheckRow
from database.leave_period import LeavePeriod, LeavePeriodPrinting
from database.seat_holding import SeatHolding
from database.sitting import Sitting
from database.speaker import Speaker
from enums import (
    LeaveEntryFormat,
    LeaveNameSource,
    LeaveOfficeSource,
    LeaveSpeakerLinkSource,
    LeaveYearSource,
)
from exceptions import HansardHandCheckError
from scripts.build_leave_seat_check_packets import (
    CheckItem,
    build_leave_seat_check_packets,
    draw_group,
    get_group_to_items,
    get_leave_printing_groups,
    get_order_break_sitting_ids,
    get_packet_entries,
    get_plant_count,
    get_seat_holding_group,
    get_shared_line_row_ids,
)

_SEED = 20_261_109
_OTHER_SEED = 20_261_110
_ALLOWED_DATABASE_URL = "postgresql://user:password@localhost:5437/hansard_positions"
_WRONG_DATABASE_URL = "postgresql://user:password@localhost:5435/hansard_launch"
_PLANTS_AT_FIFTY = 5
_PLANTS_AT_SEVEN = 1
_PLANTS_AT_ONE = 1
_LARGE_GROUP_SIZE = 60
_SAMPLE_SIZE = 50
_FORMAT_GROUP = "format|STRUCTURED_LIST|2020"

_LEAVE_ROW = LeavePeriodPrintingCheckRow(
    id=1,
    ordinal=1,
    sitting_date=date(2020, 3, 6),
    printed_name="Mr Lee Hsien Loong",
    carried_name=None,
    printed_from="5 Mar",
    printed_to="7 Mar",
    printed_line=None,
    printed_heading_from=None,
    printed_heading_to=None,
    office_printed=None,
    entry_format=LeaveEntryFormat.STRUCTURED_LIST,
    name_source=LeaveNameSource.PRINTED,
    year_source=LeaveYearSource.NEAREST_TO_SITTING,
    speaker_link_source=None,
    office_source=None,
    sitting_id=1,
    speaker_name=None,
    start_date=date(2020, 3, 5),
    end_date=date(2020, 3, 7),
    end_text=None,
)
_SEAT_ROW = SeatHoldingCheckRow(
    id=1,
    division_key="ang mo kio",
    location_name="Ang Mo Kio GRC",
    first_sitting_date=date(2016, 1, 11),
    last_sitting_date=date(2020, 3, 6),
    sitting_count=40,
    speaker_name="Lee Hsien Loong",
)
_ITEM = CheckItem(
    table_name="seat_holding",
    row_id=1,
    source_text="source",
    name=None,
    member="Lee Hsien Loong",
    office=None,
    start_date=date(2016, 1, 11),
    other_says="says",
)


def _build_leave_rows(count: int) -> list[LeavePeriodPrintingCheckRow]:
    return [
        replace(_LEAVE_ROW, id=row_id, ordinal=row_id, sitting_id=row_id)
        for row_id in range(1, count + 1)
    ]


def test_every_row_is_in_its_format_and_decade_group() -> None:
    assert get_leave_printing_groups(_LEAVE_ROW)[0] == _FORMAT_GROUP


def test_a_nearest_year_row_is_grouped_by_its_gap_to_the_sitting() -> None:
    far_row = replace(
        _LEAVE_ROW, start_date=date(2020, 1, 1), end_date=date(2020, 1, 2)
    )
    farthest_row = replace(
        _LEAVE_ROW, start_date=date(2019, 6, 1), end_date=date(2019, 6, 2)
    )
    near_row = replace(
        _LEAVE_ROW, start_date=date(2020, 2, 20), end_date=date(2020, 2, 21)
    )

    assert "year_gap|0" in get_leave_printing_groups(_LEAVE_ROW)
    assert "year_gap|31-90" in get_leave_printing_groups(far_row)
    assert "year_gap|over-90" in get_leave_printing_groups(farthest_row)
    assert "year_gap|1-30" in get_leave_printing_groups(near_row)


def test_a_heading_year_row_is_grouped_apart_from_a_nearest_year_row() -> None:
    heading_row = replace(
        _LEAVE_ROW,
        year_source=LeaveYearSource.PRINTED_COLUMN_HEADING,
        start_date=date(2001, 2, 23),
        end_date=date(2001, 2, 24),
        sitting_date=date(2003, 1, 1),
    )

    groups = get_leave_printing_groups(heading_row)

    assert "heading_year_gap|over-90" in groups
    assert not [group for group in groups if group.startswith("year_gap")]


def test_a_nearest_year_outside_the_printed_heading_is_its_own_group() -> None:
    outside_row = replace(
        _LEAVE_ROW,
        start_date=date(2019, 12, 30),
        end_date=date(2020, 1, 2),
        printed_heading_from="2020",
        printed_heading_to="2020",
    )
    inside_row = replace(
        _LEAVE_ROW, printed_heading_from="2020", printed_heading_to="2020"
    )
    end_outside_row = replace(
        _LEAVE_ROW, printed_heading_from="2020", printed_heading_to="2021"
    )

    assert "year_outside_heading" in get_leave_printing_groups(outside_row)
    assert "year_outside_heading" not in get_leave_printing_groups(inside_row)
    assert "year_outside_heading" in get_leave_printing_groups(end_outside_row)
    assert "year_outside_heading" not in get_leave_printing_groups(_LEAVE_ROW)


def test_carried_linked_and_office_rows_get_their_groups() -> None:
    check_row = replace(
        _LEAVE_ROW,
        name_source=LeaveNameSource.CARRIED_FROM_ROW_ABOVE,
        speaker_link_source=LeaveSpeakerLinkSource.ROSTER_NAME,
        office_source=LeaveOfficeSource.ATTENDANCE_LIST,
    )

    groups = get_leave_printing_groups(check_row)

    assert "carried|STRUCTURED_LIST|2020" in groups
    assert "link|ROSTER_NAME|2020" in groups
    assert "office|ATTENDANCE_LIST|2020" in groups
    assert not [
        group
        for group in get_leave_printing_groups(_LEAVE_ROW)
        if group.startswith(("carried", "link", "office"))
    ]


def test_a_seat_row_is_grouped_by_the_decade_of_its_first_sitting() -> None:
    assert get_seat_holding_group(_SEAT_ROW) == "seat|2010"


def test_the_plant_count_is_a_tenth_of_the_sample_and_at_least_one() -> None:
    assert get_plant_count(_SAMPLE_SIZE) == _PLANTS_AT_FIFTY
    assert get_plant_count(7) == _PLANTS_AT_SEVEN
    assert get_plant_count(1) == _PLANTS_AT_ONE


def test_a_line_shared_in_one_sitting_marks_its_prose_rows_only() -> None:
    prose_row = replace(
        _LEAVE_ROW, id=1, entry_format=LeaveEntryFormat.PROSE_RANGE, printed_line="L"
    )
    second_prose_row = replace(prose_row, id=2, ordinal=2)
    table_row = replace(
        prose_row, id=3, ordinal=3, entry_format=LeaveEntryFormat.TABLE_ROW
    )
    no_line_row = replace(prose_row, id=4, ordinal=4, printed_line=None)
    other_sitting_row = replace(prose_row, id=5, sitting_id=2)

    shared_ids = get_shared_line_row_ids(
        [prose_row, second_prose_row, table_row, no_line_row, other_sitting_row]
    )

    assert shared_ids == {1, 2}


def test_a_shared_line_row_goes_in_its_own_group_and_its_plant_moves_the_year() -> None:
    prose_row = replace(
        _LEAVE_ROW, id=1, entry_format=LeaveEntryFormat.PROSE_RANGE, printed_line="L"
    )
    second_prose_row = replace(prose_row, id=2, ordinal=2)

    group_to_items = get_group_to_items([prose_row, second_prose_row], [])
    group_draw = draw_group(
        _SEED, "shared_line|2020", group_to_items["shared_line|2020"]
    )

    assert len(group_draw.sample) == len(group_to_items["shared_line|2020"])
    assert [plant.item.start_date for plant in group_draw.plants] == [date(2021, 3, 5)]


def test_a_start_on_29_february_moves_to_28_february() -> None:
    leap_item = replace(_ITEM, start_date=date(2020, 2, 29))

    group_draw = draw_group(_SEED, "seat|2020", [leap_item])

    assert group_draw.plants[0].item.start_date == date(2021, 2, 28)


def test_a_group_with_no_other_name_skips_its_plant_and_counts_it() -> None:
    only_item = replace(_ITEM, name="Mr Lee Hsien Loong")

    group_draw = draw_group(_SEED, "carried|STRUCTURED_LIST|2020", [only_item])

    assert group_draw.plants == []
    assert group_draw.skipped_plant_count == 1


def test_a_link_plant_takes_another_rows_member() -> None:
    first_item = replace(_ITEM, row_id=1, member="Lee Hsien Loong")
    second_item = replace(_ITEM, row_id=2, member="Tan Wu Meng")

    group_draw = draw_group(_SEED, "link|ROSTER_NAME|2020", [first_item, second_item])

    assert len(group_draw.plants) == 1
    plant = group_draw.plants[0]
    assert plant.item.member != next(
        item.member
        for item in (first_item, second_item)
        if item.row_id == plant.item.row_id
    )


def test_an_order_break_list_goes_in_whole_with_no_plants() -> None:
    rows = [
        replace(
            _LEAVE_ROW,
            id=row_id,
            ordinal=row_id,
            start_date=start_date,
            name_source=name_source,
        )
        for row_id, start_date, name_source in [
            (1, date(2020, 3, 5), LeaveNameSource.PRINTED),
            (2, date(2020, 3, 1), LeaveNameSource.CARRIED_FROM_ROW_ABOVE),
        ]
    ] + [replace(_LEAVE_ROW, id=3, ordinal=1, sitting_id=2)]

    assert get_order_break_sitting_ids(rows) == {1}
    group_to_items = get_group_to_items(rows, [])
    group_draw = draw_group(
        _SEED, "year_order_break", group_to_items["year_order_break"]
    )

    assert [item.row_id for item in group_draw.sample] == [1, 2]
    assert group_draw.plants == []


def test_two_draws_with_one_seed_are_equal() -> None:
    group_to_items = get_group_to_items(_build_leave_rows(_LARGE_GROUP_SIZE), [])
    items = group_to_items[_FORMAT_GROUP]

    assert len(draw_group(_SEED, _FORMAT_GROUP, items).sample) == _SAMPLE_SIZE
    assert draw_group(_SEED, _FORMAT_GROUP, items) == draw_group(
        _SEED, _FORMAT_GROUP, items
    )
    assert draw_group(_SEED, _FORMAT_GROUP, items) != draw_group(
        _OTHER_SEED, _FORMAT_GROUP, items
    )


def test_adding_a_group_leaves_another_groups_draw_equal() -> None:
    leave_rows = _build_leave_rows(_LARGE_GROUP_SIZE)
    before = get_group_to_items(leave_rows, [])
    after = get_group_to_items(leave_rows, [_SEAT_ROW])

    assert "seat|2010" in after
    assert "seat|2010" not in before
    assert draw_group(_SEED, _FORMAT_GROUP, before[_FORMAT_GROUP]) == draw_group(
        _SEED, _FORMAT_GROUP, after[_FORMAT_GROUP]
    )


def test_the_packets_hold_no_row_id_group_or_plant_flag() -> None:
    group_to_items = get_group_to_items(
        _build_leave_rows(_LARGE_GROUP_SIZE), [_SEAT_ROW]
    )
    group_draws = [
        draw_group(_SEED, group, group_to_items[group])
        for group in sorted(group_to_items)
    ]

    packet_entries = get_packet_entries(_SEED, group_draws)

    packet_text = "\n".join(entry.packet.model_dump_json() for entry in packet_entries)
    assert '"row_id"' not in packet_text
    assert '"group"' not in packet_text
    assert '"is_plant"' not in packet_text
    assert _FORMAT_GROUP not in packet_text
    assert sum(entry.key_entry.is_plant for entry in packet_entries) > 0
    assert len({entry.packet.packet_id for entry in packet_entries}) == len(
        packet_entries
    )
    assert packet_entries == get_packet_entries(_SEED, group_draws)


def test_a_database_with_another_label_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        packets_script, "settings", SimpleNamespace(database_url=_WRONG_DATABASE_URL)
    )

    with pytest.raises(
        HansardHandCheckError, match="only localhost:5437/hansard_positions"
    ):
        build_leave_seat_check_packets(_SEED, tmp_path / "packets")

    assert not (tmp_path / "packets").exists()


def test_an_existing_output_directory_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        packets_script, "settings", SimpleNamespace(database_url=_ALLOWED_DATABASE_URL)
    )

    with pytest.raises(HansardHandCheckError, match="already exists"):
        build_leave_seat_check_packets(_SEED, tmp_path)


def test_the_check_rows_join_the_period_and_the_member(
    scratch_session: Session,
) -> None:
    speaker = Speaker(
        name="Lee Hsien Loong",
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=14,
    )
    scratch_session.add(speaker)
    scratch_session.add(Sitting(id=1, sitting_date="6-3-2020", parlement_no=14))
    leave_period = LeavePeriod(
        period_key="a",
        name="Mr Lee",
        start_date=date(2020, 3, 5),
        end_date=date(2020, 3, 7),
    )
    scratch_session.add(leave_period)
    scratch_session.commit()
    assert speaker.id is not None
    assert leave_period.id is not None
    scratch_session.add_all(
        [
            LeavePeriodPrinting(
                ordinal=1,
                sitting_date=date(2020, 3, 6),
                entry_format=LeaveEntryFormat.STRUCTURED_LIST,
                name_source=LeaveNameSource.PRINTED,
                sitting_id=1,
                leave_period_id=leave_period.id,
                speaker_id=speaker.id,
            ),
            LeavePeriodPrinting(
                ordinal=2,
                sitting_date=date(2020, 3, 6),
                entry_format=LeaveEntryFormat.STRUCTURED_LIST,
                name_source=LeaveNameSource.NONE,
                sitting_id=1,
                leave_period_id=leave_period.id,
            ),
            SeatHolding(
                division_key="ang mo kio",
                location_name="Ang Mo Kio GRC",
                first_sitting_date=date(2020, 3, 6),
                last_sitting_date=date(2020, 3, 6),
                sitting_count=1,
                speaker_id=speaker.id,
            ),
        ]
    )
    scratch_session.commit()

    leave_check_rows = CRUDLeavePeriodPrinting(scratch_session).get_check_rows()
    seat_check_rows = CRUDSeatHolding(scratch_session).get_check_rows()

    assert [
        (
            check_row.ordinal,
            check_row.speaker_name,
            check_row.start_date,
            check_row.end_date,
        )
        for check_row in leave_check_rows
    ] == [
        (1, "Lee Hsien Loong", date(2020, 3, 5), date(2020, 3, 7)),
        (2, None, date(2020, 3, 5), date(2020, 3, 7)),
    ]
    assert [check_row.speaker_name for check_row in seat_check_rows] == [
        "Lee Hsien Loong"
    ]

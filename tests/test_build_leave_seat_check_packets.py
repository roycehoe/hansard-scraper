from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session

import scripts.build_leave_seat_check_packets as packets_script
from crud.attendance import AttendanceSeatRow
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
    GroupDraw,
    build_leave_seat_check_packets,
    draw_groups,
    get_carried_context_rows,
    get_group_to_items,
    get_leave_printing_groups,
    get_leave_source_text,
    get_order_break_sitting_ids,
    get_packet_entries,
    get_plant_count,
    get_seat_holding_group,
    get_seat_source_text,
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
_MISSPELT_PLANT_INDEXES = (1, 3)

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
    speaker_id=None,
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
    speaker_id=1,
    speaker_name="Lee Hsien Loong",
)
_ITEM = CheckItem(
    table_name="seat_holding",
    row_id=1,
    name=None,
    member="Lee Hsien Loong",
    office=None,
    start_date=date(2016, 1, 11),
    end_date=date(2020, 3, 6),
    other_says="division: ang mo kio; sittings: 40",
    division_key="ang mo kio",
)


def _draw_group(seed: int, group: str, items: list[CheckItem]) -> GroupDraw:
    return draw_groups(seed, {group: items})[0]


def _get_item_key_to_source_text(
    items: list[CheckItem],
) -> dict[tuple[str, int], str]:
    return {(item.table_name, item.row_id): f"source {item.row_id}" for item in items}


def _build_items(count: int, **changes: object) -> list[CheckItem]:
    return [replace(_ITEM, row_id=row_id, **changes) for row_id in range(1, count + 1)]


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
    prose_rows = [
        replace(
            _LEAVE_ROW,
            id=row_id,
            ordinal=row_id % 2 + 1,
            sitting_id=(row_id + 1) // 2,
            entry_format=LeaveEntryFormat.PROSE_RANGE,
            printed_line=f"L{(row_id + 1) // 2}",
        )
        for row_id in range(1, _LARGE_GROUP_SIZE + 1)
    ]

    group_to_items = get_group_to_items(prose_rows, [])
    group_draw = _draw_group(
        _SEED, "shared_line|2020", group_to_items["shared_line|2020"]
    )

    assert len(group_draw.sample) == _SAMPLE_SIZE
    assert [plant.item.start_date for plant in group_draw.plants] == [
        date(2021, 3, 5)
    ] * len(group_draw.plants)
    assert group_draw.plants


def test_a_29_february_moves_to_28_february_on_either_end() -> None:
    items = _build_items(
        _LARGE_GROUP_SIZE,
        start_date=date(2020, 2, 29),
        end_date=date(2024, 2, 29),
    )

    group_draw = _draw_group(_SEED, "year_gap|1-30", items)

    assert group_draw.plants
    for plant in group_draw.plants:
        assert plant.item.start_date == date(2021, 2, 28)
        assert plant.item.end_date == date(2025, 2, 28)


def test_a_year_plant_moves_both_ends_and_a_seat_moves_first_and_last_sitting() -> None:
    items = _build_items(_LARGE_GROUP_SIZE)

    group_draw = _draw_group(_SEED, "seat|2010", items)

    moved_plants = [
        plant
        for plant in group_draw.plants
        if f"division: {_ITEM.division_key};" in plant.item.other_says
    ]
    assert moved_plants
    for plant in moved_plants:
        assert plant.item.start_date == date(2017, 1, 11)
        assert plant.item.end_date == date(2021, 3, 6)


def test_the_second_and_fourth_seat_plants_misspell_the_division_only() -> None:
    items = _build_items(_LARGE_GROUP_SIZE)

    group_draw = _draw_group(_SEED, "seat|2010", items)

    assert len(group_draw.plants) == _PLANTS_AT_FIFTY
    for plant_index, plant in enumerate(group_draw.plants):
        is_misspelt = f"division: {_ITEM.division_key};" not in plant.item.other_says
        assert is_misspelt == (plant_index in (1, 3))
        if not is_misspelt:
            continue
        misspelt_key = plant.item.other_says.removeprefix("division: ").split(";")[0]
        assert sorted(misspelt_key) == sorted(_ITEM.division_key or "")
        assert misspelt_key != _ITEM.division_key
        assert plant.item.other_says.endswith("; sittings: 40")
        assert plant.item.start_date == _ITEM.start_date
        assert plant.item.end_date == _ITEM.end_date
        assert plant.item.member == _ITEM.member
        assert _ITEM.division_key in plant.note
        assert misspelt_key in plant.note


def test_a_misspelt_division_plant_keeps_the_source_text_of_its_base_row() -> None:
    items = _build_items(_LARGE_GROUP_SIZE)
    group_draw = _draw_group(_SEED, "seat|2010", items)

    packet_entries = get_packet_entries(
        _SEED, [group_draw], _get_item_key_to_source_text(items)
    )

    misspelt_entries = [
        entry
        for entry in packet_entries
        if entry.key_entry.is_plant
        and f"division: {_ITEM.division_key};" not in entry.packet.data_says
    ]
    assert len(misspelt_entries) == len(_MISSPELT_PLANT_INDEXES)
    for entry in misspelt_entries:
        assert entry.packet.source_text == f"source {entry.key_entry.row_id}"
        assert entry.packet.data_says.startswith("member: Lee Hsien Loong;")
        assert entry.packet.rule.startswith(
            "The division is the folded form of the labels shown."
        )


def test_a_swap_equal_to_a_stored_division_is_not_used() -> None:
    items = [
        *_build_items(_LARGE_GROUP_SIZE, division_key="ab", other_says="division: ab;"),
        replace(
            _ITEM,
            row_id=_LARGE_GROUP_SIZE + 1,
            division_key="ba",
            other_says="division: ba;",
        ),
    ]

    group_draw = _draw_group(_SEED, "seat|2010", items)

    assert len(group_draw.plants) == _PLANTS_AT_FIFTY - len(_MISSPELT_PLANT_INDEXES)
    assert group_draw.skipped_plant_count == len(_MISSPELT_PLANT_INDEXES)
    for plant in group_draw.plants:
        assert plant.item.start_date == date(2017, 1, 11)


def test_a_division_key_with_no_usable_pair_is_skipped_and_counted() -> None:
    items = _build_items(
        _LARGE_GROUP_SIZE, division_key="aa", other_says="division: aa;"
    )

    group_draw = _draw_group(_SEED, "seat|2010", items)

    assert len(group_draw.plants) == _PLANTS_AT_FIFTY - len(_MISSPELT_PLANT_INDEXES)
    assert group_draw.skipped_plant_count == len(_MISSPELT_PLANT_INDEXES)


def test_letters_apart_by_a_space_are_not_an_adjacent_pair() -> None:
    items = _build_items(
        _LARGE_GROUP_SIZE,
        division_key="a b",
        other_says="division: a b; sittings: 40",
    )

    group_draw = _draw_group(_SEED, "seat|2010", items)

    misspelt_plants = [
        plant
        for plant in group_draw.plants
        if "division: a b;" not in plant.item.other_says
    ]
    assert not misspelt_plants
    assert group_draw.skipped_plant_count == len(_MISSPELT_PLANT_INDEXES)


def test_an_open_period_moves_its_start_only() -> None:
    items = _build_items(
        _LARGE_GROUP_SIZE,
        table_name="leave_period_printing",
        end_date=None,
    )

    group_draw = _draw_group(_SEED, "year_gap|1-30", items)

    assert group_draw.plants
    for plant in group_draw.plants:
        assert plant.item.start_date == date(2017, 1, 11)
        assert plant.item.end_date is None


def test_a_plant_keeps_the_source_text_of_its_base_row() -> None:
    items = _build_items(_LARGE_GROUP_SIZE)
    group_draw = _draw_group(_SEED, "seat|2010", items)

    packet_entries = get_packet_entries(
        _SEED, [group_draw], _get_item_key_to_source_text(items)
    )

    plant_entries = [entry for entry in packet_entries if entry.key_entry.is_plant]
    assert plant_entries
    for entry in plant_entries:
        assert entry.packet.source_text == f"source {entry.key_entry.row_id}"


def test_a_carried_plant_takes_name_member_and_office_from_one_donor() -> None:
    items = [
        replace(
            _ITEM,
            row_id=row_id,
            name=f"name {row_id}",
            member=f"member {row_id}",
            office=f"office {row_id}",
        )
        for row_id in range(1, _LARGE_GROUP_SIZE + 1)
    ]

    group_draw = _draw_group(_SEED, "carried|STRUCTURED_LIST|2020", items)

    assert group_draw.plants
    for plant in group_draw.plants:
        donor_id = plant.item.name.removeprefix("name ")  # type: ignore[union-attr]
        assert plant.item.member == f"member {donor_id}"
        assert plant.item.office == f"office {donor_id}"
        assert plant.item.row_id != int(donor_id)


def test_no_plant_sits_on_a_sampled_row_and_no_row_is_planted_twice() -> None:
    leave_rows = _build_leave_rows(_LARGE_GROUP_SIZE * 2)
    group_to_items = get_group_to_items(leave_rows, [])
    assert len(group_to_items) > 1

    group_draws = draw_groups(_SEED, group_to_items)

    sampled_keys = {
        (item.table_name, item.row_id)
        for group_draw in group_draws
        for item in group_draw.sample
    }
    planted_keys = [
        (plant.item.table_name, plant.item.row_id)
        for group_draw in group_draws
        for plant in group_draw.plants
    ]
    assert planted_keys
    assert not sampled_keys & set(planted_keys)
    assert len(planted_keys) == len(set(planted_keys))


def test_a_plant_shortfall_is_counted_as_skipped() -> None:
    group_draw = _draw_group(_SEED, "seat|2010", _build_items(_SAMPLE_SIZE))

    assert group_draw.plants == []
    assert group_draw.skipped_plant_count == _PLANTS_AT_FIFTY


def test_a_group_with_no_other_name_skips_its_plant_and_counts_it() -> None:
    only_item = replace(_ITEM, name="Mr Lee Hsien Loong")

    group_draw = _draw_group(_SEED, "carried|STRUCTURED_LIST|2020", [only_item])

    assert group_draw.plants == []
    assert group_draw.skipped_plant_count == 1


def test_a_link_plant_takes_another_rows_member() -> None:
    items = [
        replace(_ITEM, row_id=row_id, member=f"member {row_id % 2}")
        for row_id in range(1, _LARGE_GROUP_SIZE + 1)
    ]

    group_draw = _draw_group(_SEED, "link|ROSTER_NAME|2020", items)

    assert group_draw.plants
    for plant in group_draw.plants:
        base = next(item for item in items if item.row_id == plant.item.row_id)
        assert plant.item.member != base.member


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
    group_draw = _draw_group(
        _SEED, "year_order_break", group_to_items["year_order_break"]
    )

    assert [item.row_id for item in group_draw.sample] == [1, 2]
    assert group_draw.plants == []


def test_two_draws_with_one_seed_are_equal() -> None:
    group_to_items = get_group_to_items(_build_leave_rows(_LARGE_GROUP_SIZE), [])
    items = group_to_items[_FORMAT_GROUP]

    assert len(_draw_group(_SEED, _FORMAT_GROUP, items).sample) == _SAMPLE_SIZE
    assert _draw_group(_SEED, _FORMAT_GROUP, items) == _draw_group(
        _SEED, _FORMAT_GROUP, items
    )
    assert _draw_group(_SEED, _FORMAT_GROUP, items) != _draw_group(
        _OTHER_SEED, _FORMAT_GROUP, items
    )


def test_adding_a_group_leaves_another_groups_sample_equal() -> None:
    leave_rows = _build_leave_rows(_LARGE_GROUP_SIZE)
    before = get_group_to_items(leave_rows, [])
    after = get_group_to_items(leave_rows, [_SEAT_ROW])

    assert "seat|2010" in after
    assert "seat|2010" not in before
    assert (
        _draw_group(_SEED, _FORMAT_GROUP, before[_FORMAT_GROUP]).sample
        == next(
            group_draw
            for group_draw in draw_groups(_SEED, after)
            if group_draw.group == _FORMAT_GROUP
        ).sample
    )


def test_the_packets_hold_no_row_id_group_or_plant_flag() -> None:
    group_to_items = get_group_to_items(
        _build_leave_rows(_LARGE_GROUP_SIZE), [_SEAT_ROW]
    )
    group_draws = draw_groups(_SEED, group_to_items)

    item_key_to_source_text = _get_item_key_to_source_text(
        [item for items in group_to_items.values() for item in items]
    )

    packet_entries = get_packet_entries(_SEED, group_draws, item_key_to_source_text)

    packet_text = "\n".join(entry.packet.model_dump_json() for entry in packet_entries)
    assert '"row_id"' not in packet_text
    assert '"group"' not in packet_text
    assert '"is_plant"' not in packet_text
    assert _FORMAT_GROUP not in packet_text
    assert sum(entry.key_entry.is_plant for entry in packet_entries) > 0
    assert len({entry.packet.packet_id for entry in packet_entries}) == len(
        packet_entries
    )
    assert packet_entries == get_packet_entries(
        _SEED, group_draws, item_key_to_source_text
    )


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


def test_a_plain_row_shows_the_sitting_the_printed_row_and_both_headings() -> None:
    check_row = replace(
        _LEAVE_ROW, printed_heading_from="2019", printed_heading_to=None
    )

    assert get_leave_source_text(check_row, [check_row], {}).split("\n") == [
        "sitting: 2020-03-06",
        "printed: Mr Lee Hsien Loong | 5 Mar | 7 Mar",
        "heading from: 2019",
        "heading to: (none)",
    ]


def test_a_printed_line_and_an_end_text_replace_the_printed_row() -> None:
    check_row = replace(
        _LEAVE_ROW, printed_line="Mr Lee on leave", end_text="Till further notice"
    )

    lines = get_leave_source_text(check_row, [check_row], {}).split("\n")

    assert lines[1:3] == [
        "printed line: Mr Lee on leave",
        "end text: Till further notice",
    ]


def test_a_carried_row_shows_the_rows_from_the_nearest_named_row_down_to_it() -> None:
    sitting_rows = [
        replace(_LEAVE_ROW, id=1, ordinal=1, printed_name="Mr A"),
        replace(_LEAVE_ROW, id=2, ordinal=2, printed_name="Mr B"),
        replace(_LEAVE_ROW, id=3, ordinal=3, printed_name=None),
        replace(_LEAVE_ROW, id=4, ordinal=4, printed_name=None),
        replace(_LEAVE_ROW, id=5, ordinal=5, printed_name="Mr C"),
    ]
    check_row = replace(
        sitting_rows[3], name_source=LeaveNameSource.CARRIED_FROM_ROW_ABOVE
    )

    context_rows = get_carried_context_rows(check_row, sitting_rows)
    lines = get_leave_source_text(check_row, sitting_rows, {}).split("\n")

    assert [context_row.ordinal for context_row in context_rows] == [2, 3, 4]
    assert lines[-3:] == [
        "2. Mr B | 5 Mar | 7 Mar",
        "3. (blank) | 5 Mar | 7 Mar",
        "4. (blank) | 5 Mar | 7 Mar",
    ]


def test_a_linked_row_shows_the_members_whole_attendance_entry() -> None:
    check_row = replace(
        _LEAVE_ROW,
        speaker_id=7,
        speaker_link_source=LeaveSpeakerLinkSource.ROSTER_NAME,
    )

    lines = get_leave_source_text(check_row, [check_row], {7: "Mr Lee (Ang Mo Kio)."})

    assert lines.endswith("attendance entry: Mr Lee (Ang Mo Kio).")


def test_a_linked_row_with_no_entry_says_so() -> None:
    check_row = replace(
        _LEAVE_ROW,
        speaker_id=7,
        speaker_link_source=LeaveSpeakerLinkSource.ROSTER_NAME,
    )

    lines = get_leave_source_text(check_row, [check_row], {8: "Mr Tan"})

    assert lines.endswith("no attendance entry for this member at this sitting")


def test_an_unlinked_row_shows_no_attendance_line() -> None:
    assert "attendance" not in get_leave_source_text(_LEAVE_ROW, [_LEAVE_ROW], {})


def test_a_seat_row_shows_its_labels_with_counts_and_the_neighbours() -> None:
    seat_rows = [
        AttendanceSeatRow(1, "Bishan GRC", "1-9-2015"),
        AttendanceSeatRow(1, "Ang Mo Kio GRC", "11-1-2016"),
        AttendanceSeatRow(1, "Ang Mo Kio", "12-1-2016"),
        AttendanceSeatRow(1, "Ang Mo Kio GRC", "6-3-2020"),
        AttendanceSeatRow(1, "Ang Mo Kio GRC", "6-3-2020"),
        AttendanceSeatRow(1, "Nominated Member", "1-6-2021"),
    ]

    assert get_seat_source_text(_SEAT_ROW, seat_rows).split("\n") == [
        "labels of this member naming this division:",
        "Ang Mo Kio | 1 sittings | first 2016-01-12 | last 2016-01-12",
        "Ang Mo Kio GRC | 2 sittings | first 2016-01-11 | last 2020-03-06",
        "label before the first: Bishan GRC on 2015-09-01",
        "label after the last: Nominated Member on 2021-06-01",
    ]


def test_a_seat_row_with_no_neighbours_says_none() -> None:
    seat_rows = [AttendanceSeatRow(1, "Ang Mo Kio GRC", "11-1-2016")]

    lines = get_seat_source_text(_SEAT_ROW, seat_rows).split("\n")

    assert lines[-2:] == [
        "label before the first: (none)",
        "label after the last: (none)",
    ]


def test_the_office_rule_depends_on_the_office_source() -> None:
    attendance_list_packet = _office_packet_rule("office|ATTENDANCE_LIST|2020")
    printed_packet = _office_packet_rule("office|PRINTED_ON_ENTRY|2020")

    assert "attendance entry" in attendance_list_packet
    assert "own printed line" in printed_packet
    assert attendance_list_packet.endswith("Judge only this rule.")
    assert printed_packet.endswith("Judge only this rule.")


def _office_packet_rule(group: str) -> str:
    group_draw = GroupDraw(group, 1, [_ITEM], [], 0)
    return get_packet_entries(
        _SEED, [group_draw], _get_item_key_to_source_text([_ITEM])
    )[0].packet.rule

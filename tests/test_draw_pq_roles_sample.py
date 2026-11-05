from datetime import datetime
from fractions import Fraction
from typing import Optional

import pytest

import scripts.draw_pq_roles_sample as draw_pq_roles_sample_script
from crud.report import ReportFrameRow
from exceptions import HansardHandCheckError
from schemas.pq_roles_round_one_row import PqRolesRoundOneRow

_FIRST_GROUP = "Parliaments 0 to 11"
_SECOND_GROUP = "Parliament 12"
_FIRST_SEED = 20_261_201
_LAST_SEED = 20_261_214
_BASE_SIZE = 200
_FIRST_RAISED_SIZE = 201
_ABSENT_FILER_FRAME_COUNT = 555


def _build_row(
    row_id: int,
    report_id: int,
    parliament_number: int = 12,
    sprs_report_id: str = "a",
    first_ordinal: Optional[int] = 1,
    speaker_id: Optional[int] = None,
) -> ReportFrameRow:
    return ReportFrameRow(
        id=row_id,
        report_id=report_id,
        parliament_number=parliament_number,
        report_version="sprs3",
        report_type="oral-answer",
        sitting_date=datetime(2020, 1, 1),
        sprs_report_id=sprs_report_id,
        first_ordinal=first_ordinal,
        speaker_id=speaker_id,
        printed_name="Mr A",
    )


def test_the_seed_is_the_first_seed_plus_the_frame_index() -> None:
    assert draw_pq_roles_sample_script.get_frame_seed("ASKER") == _FIRST_SEED
    assert draw_pq_roles_sample_script.get_frame_seed("NO_ANSWER") == _LAST_SEED


def test_a_frame_in_order_passes_the_order_check() -> None:
    rows = [
        _build_row(1, 10, parliament_number=0),
        _build_row(2, 10, first_ordinal=3),
        _build_row(3, 11, sprs_report_id="b"),
    ]

    draw_pq_roles_sample_script.validate_can_draw_frame_order("ASKER", rows)


def test_the_order_check_refuses_a_row_that_sorts_before_the_one_above() -> None:
    rows = [_build_row(1, 10, parliament_number=13), _build_row(2, 11)]

    with pytest.raises(HansardHandCheckError, match="out of order"):
        draw_pq_roles_sample_script.validate_can_draw_frame_order("ASKER", rows)


def test_the_order_check_compares_report_ids_by_byte_order() -> None:
    rows = [
        _build_row(1, 10, sprs_report_id="a"),
        _build_row(2, 11, sprs_report_id="B"),
    ]

    with pytest.raises(HansardHandCheckError):
        draw_pq_roles_sample_script.validate_can_draw_frame_order("ASKER", rows)


def test_the_order_check_refuses_a_repeated_row() -> None:
    rows = [_build_row(1, 10), _build_row(1, 10)]

    with pytest.raises(HansardHandCheckError):
        draw_pq_roles_sample_script.validate_can_draw_frame_order("ASKER", rows)


def test_a_frame_of_200_or_fewer_is_taken_whole_with_no_raise() -> None:
    assert draw_pq_roles_sample_script.get_sample_size(
        {_FIRST_GROUP: 150, "g": 50}
    ) == (
        200,
        None,
    )
    assert draw_pq_roles_sample_script.get_sample_size({_FIRST_GROUP: 39}) == (39, None)


def test_a_large_frame_with_an_even_spread_keeps_200() -> None:
    sample_size, reason = draw_pq_roles_sample_script.get_sample_size(
        {_FIRST_GROUP: 10_000, _SECOND_GROUP: 10_000}
    )

    assert (sample_size, reason) == (200, None)


def test_a_frame_whose_weights_spread_too_far_at_200_raises_n_until_they_do_not() -> (
    None
):
    group_to_frame_count = {
        _FIRST_GROUP: 358,
        _SECOND_GROUP: 56,
        "Parliament 13": 51,
        "Parliament 14": 77,
        "Parliament 15": 13,
    }

    sample_size, reason = draw_pq_roles_sample_script.get_sample_size(
        group_to_frame_count
    )

    group_to_allocation = draw_pq_roles_sample_script.get_allocation(
        group_to_frame_count, sample_size
    )
    assert _BASE_SIZE < sample_size <= _ABSENT_FILER_FRAME_COUNT
    assert reason is not None and f"to {sample_size}" in reason
    assert draw_pq_roles_sample_script.get_weight_spread(
        group_to_frame_count, group_to_allocation
    ) <= Fraction(3, 100)
    previous_allocation = draw_pq_roles_sample_script.get_allocation(
        group_to_frame_count, sample_size - 1
    )
    assert (
        sample_size == _FIRST_RAISED_SIZE
        or min(previous_allocation.values()) == 0
        or draw_pq_roles_sample_script.get_weight_spread(
            group_to_frame_count, previous_allocation
        )
        > Fraction(3, 100)
    )


def test_one_row_per_report_steps_forward_past_a_report_already_drawn() -> None:
    group_rows = [
        _build_row(1, 10),
        _build_row(2, 10, first_ordinal=2),
        _build_row(3, 11),
        _build_row(4, 12),
    ]

    positions, move_count, repeat_count = (
        draw_pq_roles_sample_script.get_distinct_report_picks(group_rows, [0, 1])
    )

    assert positions == [0, 2]
    assert (move_count, repeat_count) == (1, 0)


def test_one_row_per_report_wraps_round_the_end_of_the_group() -> None:
    group_rows = [_build_row(1, 10), _build_row(2, 11), _build_row(3, 11)]

    positions, move_count, repeat_count = (
        draw_pq_roles_sample_script.get_distinct_report_picks(group_rows, [1, 2])
    )

    assert positions == [0, 1]
    assert (move_count, repeat_count) == (1, 0)


def test_one_row_per_report_counts_a_repeat_when_every_report_is_drawn() -> None:
    group_rows = [_build_row(1, 10), _build_row(2, 10), _build_row(3, 11)]

    positions, move_count, repeat_count = (
        draw_pq_roles_sample_script.get_distinct_report_picks(group_rows, [0, 1, 2])
    )

    assert positions == [0, 1, 2]
    assert (move_count, repeat_count) == (1, 1)


def test_a_small_frame_is_taken_whole_even_when_it_repeats_a_report() -> None:
    rows = [
        _build_row(1, 10),
        _build_row(2, 10, first_ordinal=2),
        _build_row(3, 11, sprs_report_id="b"),
    ]
    frame = draw_pq_roles_sample_script.build_frame("UNLABELLED", rows)

    frame_draw = draw_pq_roles_sample_script.draw_frame(frame)

    assert frame_draw.is_whole
    assert [pick.row.id for pick in frame_draw.picks] == [1, 2, 3]
    assert (frame_draw.move_count, frame_draw.repeat_count) == (0, 0)


def test_a_large_frame_draws_the_allocation_in_distinct_reports() -> None:
    rows = [
        _build_row(index, 1000 + index, sprs_report_id=f"r{index:04d}")
        for index in range(1, 1001)
    ]
    frame = draw_pq_roles_sample_script.build_frame("ASKER", rows)

    frame_draw = draw_pq_roles_sample_script.draw_frame(frame)

    assert len(frame_draw.picks) == _BASE_SIZE
    assert len({pick.row.report_id for pick in frame_draw.picks}) == _BASE_SIZE
    assert not frame_draw.is_whole


def test_the_script_refuses_any_database_but_the_asked_by_copy() -> None:
    draw_pq_roles_sample_script.validate_can_draw_from(
        "localhost:5435/hansard_asked_by"
    )
    with pytest.raises(HansardHandCheckError):
        draw_pq_roles_sample_script.validate_can_draw_from("db.example:5432/hansard")


def test_round_one_matches_count_on_report_role_and_person() -> None:
    round_one_rows = [
        PqRolesRoundOneRow(
            kind="participant", report_id=10, role="ASKER", speaker_id=5
        ),
        PqRolesRoundOneRow(
            kind="participant", report_id=10, role="READER", speaker_id=6
        ),
    ]
    picks = [
        draw_pq_roles_sample_script.Pick(
            group=_SECOND_GROUP, position=0, row=_build_row(1, 10, speaker_id=5)
        ),
        draw_pq_roles_sample_script.Pick(
            group=_SECOND_GROUP, position=1, row=_build_row(2, 10, speaker_id=6)
        ),
    ]

    assert (
        draw_pq_roles_sample_script.count_round_one_matches(
            "ASKER", picks, round_one_rows
        )
        == 1
    )


def test_round_one_state_matches_count_on_report_and_state() -> None:
    round_one_rows = [
        PqRolesRoundOneRow(kind="state", report_id=10, state="CORRECTION"),
        PqRolesRoundOneRow(kind="state", report_id=11, state="URGENT"),
    ]
    picks = [
        draw_pq_roles_sample_script.Pick(
            group=_SECOND_GROUP, position=0, row=_build_row(10, 10, first_ordinal=None)
        )
    ]

    assert (
        draw_pq_roles_sample_script.count_round_one_matches(
            "CORRECTION", picks, round_one_rows
        )
        == 1
    )
    assert (
        draw_pq_roles_sample_script.count_round_one_matches(
            "URGENT", picks, round_one_rows
        )
        == 0
    )

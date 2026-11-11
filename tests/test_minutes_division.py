from pathlib import Path

import pytest

from enums import DivisionListStatus, DivisionVoteChoice
from services.minutes_division import (
    MinutesTextDivisions,
    ParsedMinutesDivision,
    get_minutes_divisions,
)
from services.minutes_text import get_minutes_word_text

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures"
_WORD_FIXTURE = _FIXTURE_DIRECTORY / "minutes" / "vp0592008_7.doc"
_OPENING = "On Question put, a division was taken: Ayes 2, Noes 1, Abstentions 0."
_TWO_COLUMN_OPENING = "On Question put, a division was taken: Ayes 2, Noes 1."
_HEADER = "     Ayes          Noes          Abstentions"
_TWO_COLUMN_HEADER = "     Ayes          Noes"
_DIVISION_COUNT = 2
_NAME_COUNT_75_11_2 = 88
_NAME_COUNT_2013_NOES = 13


def _read_fixture(name: str) -> str:
    return (_FIXTURE_DIRECTORY / name).read_text(encoding="utf-8")


def _get_names(
    division: ParsedMinutesDivision, vote_choice: DivisionVoteChoice
) -> list[str]:
    return [
        name.printed_name for name in division.names if name.vote_choice == vote_choice
    ]


def _get_counts_by_side(division: ParsedMinutesDivision) -> tuple[int, int, int]:
    return (
        len(_get_names(division, DivisionVoteChoice.AYE)),
        len(_get_names(division, DivisionVoteChoice.NO)),
        len(_get_names(division, DivisionVoteChoice.ABSTAIN)),
    )


def _get_single_division(text: str) -> ParsedMinutesDivision:
    minutes_text_divisions = get_minutes_divisions(text)
    assert len(minutes_text_divisions.divisions) == 1
    return minutes_text_divisions.divisions[0]


def test_2021_10_04_reads_two_divisions_of_75_11_2() -> None:
    minutes_text_divisions = get_minutes_divisions(
        _read_fixture("minutes_2021_10_04.txt")
    )

    assert len(minutes_text_divisions.divisions) == _DIVISION_COUNT
    for division in minutes_text_divisions.divisions:
        assert division.list_status == DivisionListStatus.STORED
        assert (division.ayes, division.noes, division.abstentions) == (75, 11, 2)
        assert _get_counts_by_side(division) == (75, 11, 2)
        assert "Abdul Samad" in _get_names(division, DivisionVoteChoice.AYE)
        assert "Chua Kheng Wee, Louis" in _get_names(division, DivisionVoteChoice.NO)
        assert "Shahira Abdullah" in _get_names(division, DivisionVoteChoice.ABSTAIN)
    assert "Zhulkarnain Abdul Rahim" in _get_names(
        minutes_text_divisions.divisions[0], DivisionVoteChoice.AYE
    )


def test_2013_02_08_joins_the_broken_noes_number_and_follows_the_continued_heading() -> (
    None
):
    division = _get_single_division(_read_fixture("minutes_2013_02_08.txt"))

    assert (division.ayes, division.noes, division.abstentions) == (77, 13, 1)
    assert division.list_status == DivisionListStatus.STORED
    assert _get_counts_by_side(division) == (77, _NAME_COUNT_2013_NOES, 1)
    assert (
        division.printed_counts == "the House divided: Ayes 77, Noes 1 3, Abstention 1."
    )


def test_2018_01_10_reads_no_nil_and_splits_the_glued_name() -> None:
    division = _get_single_division(_read_fixture("minutes_2018_01_10.txt"))

    assert (division.ayes, division.noes, division.abstentions) == (80, 0, 0)
    assert division.list_status == DivisionListStatus.STORED
    assert _get_counts_by_side(division) == (80, 0, 0)
    assert "Chen Show Mao" in _get_names(division, DivisionVoteChoice.AYE)
    assert "Low Thia Khiang" in _get_names(division, DivisionVoteChoice.AYE)
    assert all(name.printed_name.lower() != "nil" for name in division.names)


def test_2024_08_07_follows_the_noes_continued_heading() -> None:
    division = _get_single_division(_read_fixture("minutes_2024_08_07.txt"))

    assert (division.ayes, division.noes, division.abstentions) == (10, 76, 0)
    assert division.list_status == DivisionListStatus.STORED
    assert _get_counts_by_side(division) == (10, 76, 0)


def test_the_word_file_reads_both_lists_as_one_ayes_column() -> None:
    minutes_text_divisions = get_minutes_divisions(
        get_minutes_word_text(_WORD_FIXTURE.read_bytes())
    )

    assert len(minutes_text_divisions.divisions) == _DIVISION_COUNT
    for division in minutes_text_divisions.divisions:
        assert division.list_status == DivisionListStatus.STORED
        assert (division.ayes, division.noes, division.abstentions) == (75, 0, 0)
        assert _get_counts_by_side(division) == (75, 0, 0)


def test_a_name_moved_across_a_column_gives_no_vote_rows() -> None:
    moved_divisions = get_minutes_divisions(
        _read_fixture("minutes_2021_10_04_name_moved.txt")
    ).divisions

    assert moved_divisions[0].list_status == DivisionListStatus.COUNTS_DISAGREE
    assert moved_divisions[0].names == []
    assert moved_divisions[0].printed_list is not None
    assert moved_divisions[1].list_status == DivisionListStatus.STORED
    assert len(moved_divisions[1].names) == _NAME_COUNT_75_11_2


@pytest.mark.parametrize(
    "printed_counts",
    [
        "Ayes 3, Noes 2, Abstentions 2",
        "Ayes 2, Noes 3, Abstentions 2",
        "Ayes 2, Noes 2, Abstentions 3",
    ],
)
def test_one_side_short_of_a_name_gives_counts_disagree_and_no_names(
    printed_counts: str,
) -> None:
    text = "\n".join(
        [
            f"On Question put, a division was taken: {printed_counts}.",
            "",
            _HEADER,
            "",
            "     Aa Bb          Cc Dd          Ee Ff",
            "     Gg Hh          Ii Jj          Kk Ll",
        ]
    )

    division = _get_single_division(text)

    assert division.list_status == DivisionListStatus.COUNTS_DISAGREE
    assert division.names == []
    assert division.printed_list is not None


def test_a_division_opening_with_no_readable_counts_is_flagged() -> None:
    minutes_text_divisions = get_minutes_divisions("the House divided")

    assert minutes_text_divisions == MinutesTextDivisions([], True)


def test_text_without_a_division_is_not_flagged() -> None:
    minutes_text_divisions = get_minutes_divisions("Motion agreed to.\n\nAdjourned.")

    assert minutes_text_divisions == MinutesTextDivisions([], False)


def test_a_first_row_with_fewer_tokens_than_labels_is_layout_unreadable() -> None:
    two_tokens = "\n".join(
        [_OPENING, "", _HEADER, "", "     Aa Bb          Cc Dd", "     Ee Ff"]
    )
    one_token_two_positive_counts = "\n".join(
        [_OPENING, "", _HEADER, "", "     Aa Bb", "     Ee Ff"]
    )

    for text in (two_tokens, one_token_two_positive_counts):
        division = _get_single_division(text)

        assert division.list_status == DivisionListStatus.LAYOUT_UNREADABLE
        assert division.names == []
        assert division.printed_list is not None


def test_a_first_row_with_more_tokens_than_labels_is_layout_unreadable() -> None:
    text = "\n".join(
        [
            _TWO_COLUMN_OPENING,
            "",
            _TWO_COLUMN_HEADER,
            "",
            "     Aa Bb          Cc Dd          Ee Ff",
        ]
    )

    division = _get_single_division(text)

    assert division.list_status == DivisionListStatus.LAYOUT_UNREADABLE
    assert division.names == []


def test_a_continued_heading_with_no_row_after_it_is_layout_unreadable_and_raises_nothing() -> (
    None
):
    text = "\n".join(
        [
            _OPENING,
            "",
            _HEADER,
            "",
            "     Aa Bb          Cc Dd",
            "     Ee Ff",
            "                    Noes – continued",
            "",
            "On Question put, a division was taken: Ayes 1, Noes 0, Abstentions 0.",
        ]
    )

    minutes_text_divisions = get_minutes_divisions(text)

    first_division, second_division = minutes_text_divisions.divisions
    assert first_division.list_status == DivisionListStatus.LAYOUT_UNREADABLE
    assert first_division.names == []
    assert first_division.printed_list is not None
    assert second_division.list_status == DivisionListStatus.NOT_PRINTED
    assert minutes_text_divisions.is_division_mentioned_without_division is False


def test_a_name_equally_near_two_columns_is_layout_unreadable() -> None:
    text = "\n".join(
        [
            _TWO_COLUMN_OPENING,
            "",
            _TWO_COLUMN_HEADER,
            "",
            "     Aa Bb               Cc Dd",
            "               Ee Ff",
        ]
    )

    division = _get_single_division(text)

    assert division.list_status == DivisionListStatus.LAYOUT_UNREADABLE
    assert division.names == []


def test_a_division_without_a_list_is_not_printed() -> None:
    text = "\n".join([_OPENING, "", "Motion accordingly negatived."])

    division = _get_single_division(text)

    assert division.list_status == DivisionListStatus.NOT_PRINTED
    assert division.printed_list is None
    assert division.names == []
    assert (division.ayes, division.noes, division.abstentions) == (2, 1, 0)

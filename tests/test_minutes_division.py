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
_TWO_SIDED_WORD_FIXTURE = _FIXTURE_DIRECTORY / "minutes" / "vp-26-26apr10_0.doc"
_OPENING = "On Question put, a division was taken: Ayes 2, Noes 1, Abstentions 0."
_TWO_COLUMN_OPENING = "On Question put, a division was taken: Ayes 2, Noes 1."
_HEADER = "     Ayes          Noes          Abstentions"
_TWO_COLUMN_HEADER = "     Ayes          Noes"
_SHORT_OF_POSITIVE_SIDES_OPENING = (
    "On Question put, a division was taken: Ayes 2, Noes 0, Abstentions 1."
)
_TWO_TOKEN_ROWS = ("     Aa Bb          Cc Dd", "     Ee Ff")
_ONE_TOKEN_ROWS = ("     Aa Bb", "     Ee Ff")
_WORD_ROW_WITH_TWO_NAMES = "Magad\tLow Thia Khiang"
_WORD_AYES_INDENT = 17
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


def test_2014_11_04_drops_the_spaced_page_header_and_reads_both_lists() -> None:
    minutes_text_divisions = get_minutes_divisions(
        _read_fixture("minutes_2014_11_04.txt")
    )

    assert len(minutes_text_divisions.divisions) == _DIVISION_COUNT
    first_division, second_division = minutes_text_divisions.divisions
    for division in minutes_text_divisions.divisions:
        assert division.list_status == DivisionListStatus.STORED
        assert _get_names(division, DivisionVoteChoice.NO) == [
            "Chen Show Mao",
            "Lee Li Lian",
            "Lim, Sylvia",
            "Low Thia Khiang",
            "Muhamad Faisal Abdul Manap",
            "Png Eng Huat",
            "Pritam Singh",
        ]
        assert "Ang Wei Neng" in _get_names(division, DivisionVoteChoice.AYE)
        assert "Zaqy Mohamad" in _get_names(division, DivisionVoteChoice.AYE)
        assert division.printed_list is not None
        assert "N o. 17" not in division.printed_list
    assert (
        first_division.ayes,
        first_division.noes,
        first_division.abstentions,
    ) == (68, 7, 0)
    assert _get_counts_by_side(first_division) == (68, 7, 0)
    assert all(
        name.printed_name != "De Souza, Christopher" for name in first_division.names
    )
    assert (
        second_division.ayes,
        second_division.noes,
        second_division.abstentions,
    ) == (69, 7, 0)
    assert _get_counts_by_side(second_division) == (69, 7, 0)
    assert "De Souza, Christopher" in _get_names(
        second_division, DivisionVoteChoice.AYE
    )


def test_the_word_file_reads_both_lists_as_one_ayes_column() -> None:
    minutes_text_divisions = get_minutes_divisions(
        get_minutes_word_text(_WORD_FIXTURE.read_bytes())
    )

    assert len(minutes_text_divisions.divisions) == _DIVISION_COUNT
    for division in minutes_text_divisions.divisions:
        assert division.list_status == DivisionListStatus.STORED
        assert (division.ayes, division.noes, division.abstentions) == (75, 0, 0)
        assert _get_counts_by_side(division) == (75, 0, 0)


def test_the_2010_word_file_reads_two_sided_lists_by_the_leftmost_labels() -> None:
    minutes_text_divisions = get_minutes_divisions(
        get_minutes_word_text(_TWO_SIDED_WORD_FIXTURE.read_bytes())
    )

    assert len(minutes_text_divisions.divisions) == _DIVISION_COUNT
    first_division, second_division = minutes_text_divisions.divisions
    for division in minutes_text_divisions.divisions:
        assert division.list_status == DivisionListStatus.STORED
        assert "Abdullah Tarmugi" in _get_names(division, DivisionVoteChoice.AYE)
        assert "Zaqy Mohamad" in _get_names(division, DivisionVoteChoice.AYE)
    assert (
        first_division.ayes,
        first_division.noes,
        first_division.abstentions,
    ) == (73, 2, 0)
    assert _get_counts_by_side(first_division) == (73, 2, 0)
    assert _get_names(first_division, DivisionVoteChoice.NO) == [
        "Chiam See Tong",
        "Low Thia Khiang",
    ]
    assert (
        second_division.ayes,
        second_division.noes,
        second_division.abstentions,
    ) == (74, 1, 0)
    assert _get_counts_by_side(second_division) == (74, 1, 0)
    assert _get_names(second_division, DivisionVoteChoice.NO) == ["Low Thia Khiang"]


def test_a_name_moved_across_the_2010_word_list_gives_no_vote_rows() -> None:
    text = get_minutes_word_text(_TWO_SIDED_WORD_FIXTURE.read_bytes())
    assert text.count(_WORD_ROW_WITH_TWO_NAMES) == 1

    moved_divisions = get_minutes_divisions(
        text.replace(
            _WORD_ROW_WITH_TWO_NAMES,
            "Magad\n" + " " * _WORD_AYES_INDENT + "Low Thia Khiang",
        )
    ).divisions

    assert moved_divisions[0].list_status == DivisionListStatus.COUNTS_DISAGREE
    assert moved_divisions[0].names == []
    assert moved_divisions[0].printed_list is not None
    assert moved_divisions[1].list_status == DivisionListStatus.STORED


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


def test_a_two_token_first_row_takes_the_two_leftmost_labels() -> None:
    division = _get_single_division(
        "\n".join([_OPENING, "", _HEADER, "", *_TWO_TOKEN_ROWS])
    )

    assert division.list_status == DivisionListStatus.STORED
    assert _get_names(division, DivisionVoteChoice.AYE) == ["Aa Bb", "Ee Ff"]
    assert _get_names(division, DivisionVoteChoice.NO) == ["Cc Dd"]


@pytest.mark.parametrize(
    ("opening", "rows"),
    [
        (_OPENING, _ONE_TOKEN_ROWS),
        (_SHORT_OF_POSITIVE_SIDES_OPENING, _TWO_TOKEN_ROWS),
    ],
)
def test_a_first_row_short_of_the_positive_sides_is_layout_unreadable(
    opening: str, rows: tuple[str, ...]
) -> None:
    division = _get_single_division("\n".join([opening, "", _HEADER, "", *rows]))

    assert division.list_status == DivisionListStatus.LAYOUT_UNREADABLE
    assert division.names == []
    assert division.printed_list is not None


def test_a_one_token_first_row_whose_only_count_is_not_the_leftmost_label_is_layout_unreadable() -> (
    None
):
    text = "\n".join(
        [
            "On Question put, a division was taken: Ayes 0, Noes 3, Abstentions 0.",
            "",
            _HEADER,
            "",
            "     Aa Bb",
            "     Cc Dd",
            "     Ee Ff",
        ]
    )

    division = _get_single_division(text)

    assert (division.ayes, division.noes, division.abstentions) == (0, 3, 0)
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

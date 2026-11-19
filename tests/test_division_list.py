import json
from pathlib import Path
from typing import Optional

import pytest

from enums import DivisionListStatus, DivisionVoteChoice
from services.division_list import (
    ParsedDivisionList,
    get_division_list,
)

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures"
_OPENING = "The House divided: Ayes, 2; Noes, 1."
_WRAPPED_NAME_LINE = "   Buang bin          Bani, S.T."
_MOVED_NAME_LINES = "   Buang bin\r\n   Bani, S.T."
_BARE_HEADING_COUNTS = (15, 30, 1, 4, None)


def _read_fixture(name: str) -> tuple[str, dict]:
    html = (_FIXTURE_DIRECTORY / f"{name}.html").read_text(encoding="utf-8")
    expected = json.loads((_FIXTURE_DIRECTORY / f"{name}.json").read_text())
    return html, expected


def _get_list(
    html: Optional[str],
    ayes: Optional[int] = 2,
    noes: Optional[int] = 1,
    abstentions: Optional[int] = None,
    absent: Optional[int] = None,
    paired: Optional[int] = None,
    division_index: int = 0,
    division_count: int = 1,
) -> ParsedDivisionList:
    return get_division_list(
        html, division_index, division_count, ayes, noes, abstentions, absent, paired
    )


def _get_fixture_list(html: str, expected: dict) -> ParsedDivisionList:
    return get_division_list(
        html,
        expected["division_index"],
        expected["division_count"],
        expected["ayes"],
        expected["noes"],
        expected["abstentions"],
        expected["absent"],
        expected["paired"],
    )


def _get_pre_html(*lines: str) -> str:
    return "<pre>\n" + "\n".join(lines) + "\n</pre>"


def _get_names(
    parsed_list: ParsedDivisionList,
) -> list[tuple[DivisionVoteChoice, str]]:
    return [(name.vote_choice, name.printed_name) for name in parsed_list.names]


def _assert_fixture_is_stored(name: str) -> None:
    html, expected = _read_fixture(name)

    parsed_list = _get_fixture_list(html, expected)

    assert parsed_list.list_status == DivisionListStatus.STORED
    assert parsed_list.printed_list is not None
    assert _get_names(parsed_list) == [
        (DivisionVoteChoice(vote_choice), printed_name)
        for vote_choice, printed_name in expected["expected_names"]
    ]


def test_7_june_1963_reads_two_pre_blocks_with_wrapped_names_and_titles() -> None:
    _assert_fixture_is_stored("hansard_list_1963_06_07")


def test_16_may_1955_reads_a_right_column_of_three_rows_against_twenty_seven() -> None:
    _assert_fixture_is_stored("hansard_list_1955_05_16_sparse_right_column")


def test_24_april_1957_reads_rows_of_one_cell_and_rows_of_two_equally_common() -> None:
    _assert_fixture_is_stored("hansard_list_1957_04_24_row_shapes_tie")


def test_30_july_1957_reads_names_after_a_tab_and_a_wrap_under_four_tabs() -> None:
    _assert_fixture_is_stored("hansard_list_1957_07_30_tab_wrap")


def test_12_july_1962_splits_names_printed_one_space_apart() -> None:
    _assert_fixture_is_stored("hansard_list_1962_07_12_one_space_gutter")


def test_25_july_1984_gives_both_columns_the_one_heading_printed_above_them() -> None:
    _assert_fixture_is_stored("hansard_list_1984_07_25_one_heading_two_columns")


def test_18_july_1957_gives_a_name_beside_the_ayes_heading_the_ayes_side() -> None:
    _assert_fixture_is_stored("hansard_list_1957_07_18_name_beside_the_ayes_heading")


def test_18_april_1962_reads_the_list_of_the_opening_that_prints_its_counts() -> None:
    _assert_fixture_is_stored("hansard_list_1962_04_18_two_counts_on_one_opening")


def test_18_december_1963_reads_the_list_when_a_later_line_also_opens_a_division() -> (
    None
):
    _assert_fixture_is_stored("hansard_list_1963_12_18_opening_before_a_count_line")


def test_17_august_1966_joins_a_one_word_line_to_the_name_above_it() -> None:
    _assert_fixture_is_stored("hansard_list_1966_08_17_wrap_at_the_same_offset")


def test_29_december_1969_joins_a_one_word_line_to_the_name_above_it() -> None:
    _assert_fixture_is_stored("hansard_list_1969_12_29_wrap_at_the_same_offset")


def test_10_january_1986_joins_a_one_word_line_to_the_name_above_it() -> None:
    _assert_fixture_is_stored("hansard_list_1986_01_10_wrap_at_the_same_offset")


def test_12_january_2001_joins_a_one_word_line_to_a_name_that_ends_in_a_comma() -> None:
    _assert_fixture_is_stored("hansard_list_2001_01_12_wrap_after_a_comma")


def test_5_september_1962_gives_a_heading_between_two_blocks_to_the_second() -> None:
    _assert_fixture_is_stored("hansard_list_1962_09_05_heading_between_two_blocks")


def test_24_may_1967_gives_a_heading_printed_between_the_columns_to_both() -> None:
    html = _get_pre_html(
        "The House divided: Ayes, 3; Noes, 2; Absent, 6.",
        "",
        "                            Ayes                  Noes",
        "                       Ang Nam Piau          Ng Kah Ting",
        "                       Chan Chee Seng        Rodrigues, Bernard",
        "                       Chow Chiok Hock",
        "                                    Absent",
        "                       A. Rahim Ishak        Nair, Mrs Devan",
        "                       Barker, E. W.         Ng Yeow Chong",
        "                       Chan Sun Wing         Ong Pang Boon",
    )

    parsed_list = _get_list(html, 3, 2, absent=6)

    assert parsed_list.list_status == DivisionListStatus.STORED
    assert _get_names(parsed_list)[-6:] == [
        (DivisionVoteChoice.ABSENT, "A. Rahim Ishak"),
        (DivisionVoteChoice.ABSENT, "Nair, Mrs Devan"),
        (DivisionVoteChoice.ABSENT, "Barker, E. W."),
        (DivisionVoteChoice.ABSENT, "Ng Yeow Chong"),
        (DivisionVoteChoice.ABSENT, "Chan Sun Wing"),
        (DivisionVoteChoice.ABSENT, "Ong Pang Boon"),
    ]


def test_3_december_1982_reads_no_list_where_prose_follows_the_count_line() -> None:
    html, expected = _read_fixture("hansard_list_1982_12_03_prose_after_the_count_line")

    parsed_list = _get_fixture_list(html, expected)

    assert parsed_list.list_status == DivisionListStatus.NOT_PRINTED
    assert parsed_list.printed_list is None
    assert parsed_list.names == []


def test_two_openings_that_print_the_same_counts_fall_back_to_the_order_rule() -> None:
    html = _get_pre_html(
        _OPENING,
        "",
        "  Ayes               Noes",
        "",
        "  Aa Bb              Cc Dd",
        "  Ee Ff              Gg Hh",
        "",
    ) + _get_pre_html(
        _OPENING,
        "",
        "  Ayes               Noes",
        "",
        "  Ii Jj              Kk Ll",
        "  Mm Nn              Oo Pp",
    )

    parsed_list = _get_list(html, 2, 1, division_index=1, division_count=2)

    assert parsed_list.list_status == DivisionListStatus.COUNTS_DISAGREE


def test_21_september_1960_reads_a_nose_heading_as_the_noes_heading() -> None:
    _assert_fixture_is_stored("hansard_list_1960_09_21_nose_heading")


def test_4_july_1962_reads_an_absentions_heading_as_the_abstentions_heading() -> None:
    _assert_fixture_is_stored("hansard_list_1962_07_04_absentions_heading")


def test_30_january_1962_reads_an_absentions_heading_as_the_abstentions_heading() -> (
    None
):
    _assert_fixture_is_stored("hansard_list_1962_01_30_absentions_heading")


def test_9_february_1956_reads_the_cell_nils_as_a_nil_cell() -> None:
    _assert_fixture_is_stored("hansard_list_1956_02_09_nils_heading_beside_absentions")


def test_23_november_1955_reads_three_headings_over_columns_too_short_for_gaps() -> (
    None
):
    _assert_fixture_is_stored("hansard_list_1955_11_23_three_headings_sparse_columns")


def test_22_december_1965_reads_two_headings_over_two_columns() -> None:
    _assert_fixture_is_stored("hansard_list_1965_12_22_two_headings_ayes_and_absent")


def test_30_august_1985_joins_a_name_continued_on_an_indented_line() -> None:
    _assert_fixture_is_stored("hansard_list_1985_08_30_indented_wraps")


def test_18_december_1963_joins_a_cell_printed_left_of_its_column_to_the_name_before() -> (
    None
):
    _assert_fixture_is_stored("hansard_list_1963_12_18_gutter_cell")


def test_24_april_1958_reads_an_initial_b_after_a_comma_as_an_initial_not_bin() -> None:
    _assert_fixture_is_stored("hansard_list_1958_04_24_initial_b")


def test_13_march_1984_reads_the_singular_aye_heading() -> None:
    _assert_fixture_is_stored("hansard_list_1984_03_13_singular_aye")


def test_10_january_1957_stores_absent_names_under_a_line_with_no_absent_count() -> (
    None
):
    _assert_fixture_is_stored("hansard_list_1957_01_10_no_absent_count")


def test_a_name_moved_into_the_absent_block_is_counts_disagree_with_no_absent_count() -> (
    None
):
    html, expected = _read_fixture("hansard_list_1957_01_10_no_absent_count")
    moved_html = (
        html.replace("Lim Cher Kheng ", "Lim Cher Kheng", 1)
        .replace(
            "Ong Piah Teng\r\n\r\n</pre>",
            "Ong Piah Teng\r\n\r\n                                               Goh Tong Liang\r\n\r\n</pre>",
        )
        .replace(
            "Goh Tong Liang              Abdul", "                            Abdul", 1
        )
    )

    parsed_list = _get_fixture_list(moved_html, expected)

    assert parsed_list.list_status == DivisionListStatus.COUNTS_DISAGREE
    assert parsed_list.names == []


def test_a_name_under_abstentions_with_no_abstentions_count_is_counts_disagree() -> (
    None
):
    html = _get_pre_html(
        _OPENING,
        "",
        "  Ayes                Noes",
        "",
        "  Aa Bb               Cc Dd",
        "  Ee Ff               Gg Hh",
        "",
        "  Abstentions",
        "",
        "  Ii Jj",
    )

    parsed_list = _get_list(html, ayes=2, noes=2)

    assert parsed_list.list_status == DivisionListStatus.COUNTS_DISAGREE
    assert parsed_list.names == []


def test_13_december_1957_reads_five_sides() -> None:
    _assert_fixture_is_stored("hansard_list_1957_12_13")


def test_3_november_1994_reads_three_sides() -> None:
    _assert_fixture_is_stored("hansard_list_1994_11_03")


def test_27_august_2008_reads_a_table() -> None:
    _assert_fixture_is_stored("hansard_list_2008_08_27")


def test_5_april_2002_reads_one_name_per_paragraph() -> None:
    _assert_fixture_is_stored("hansard_list_2002_04_05")


def test_the_printed_counts_of_each_stored_fixture_equal_the_names_read() -> None:
    expected_counts = {
        "hansard_list_1994_11_03": {
            DivisionVoteChoice.AYE: 61,
            DivisionVoteChoice.NO: 6,
            DivisionVoteChoice.ABSTAIN: 1,
        },
        "hansard_list_1957_12_13": {
            DivisionVoteChoice.AYE: 3,
            DivisionVoteChoice.NO: 17,
            DivisionVoteChoice.ABSTAIN: 8,
            DivisionVoteChoice.ABSENT: 2,
            DivisionVoteChoice.PAIRED: 2,
        },
        "hansard_list_1963_06_07": {
            DivisionVoteChoice.AYE: 23,
            DivisionVoteChoice.NO: 20,
            DivisionVoteChoice.ABSENT: 3,
            DivisionVoteChoice.PAIRED: 4,
        },
        "hansard_list_2008_08_27": {
            DivisionVoteChoice.AYE: 5,
            DivisionVoteChoice.NO: 62,
        },
        "hansard_list_2002_04_05": {
            DivisionVoteChoice.AYE: 58,
            DivisionVoteChoice.NO: 5,
        },
    }
    for name, vote_choice_to_count in expected_counts.items():
        html, expected = _read_fixture(name)

        parsed_list = _get_fixture_list(html, expected)

        assert {
            vote_choice: sum(
                1 for name_ in parsed_list.names if name_.vote_choice == vote_choice
            )
            for vote_choice in vote_choice_to_count
        } == vote_choice_to_count
        assert len(parsed_list.names) == sum(vote_choice_to_count.values())


def test_15_may_1985_counts_disagree_and_stores_no_names() -> None:
    html, expected = _read_fixture("hansard_list_1985_05_15")

    parsed_list = _get_fixture_list(html, expected)

    assert parsed_list.list_status == DivisionListStatus.COUNTS_DISAGREE
    assert parsed_list.printed_list is not None
    assert parsed_list.names == []


def test_27_august_2002_reads_the_no_heading_as_a_heading_not_a_name() -> None:
    html, expected = _read_fixture("hansard_list_2002_08_27_no_heading")

    parsed_list = _get_fixture_list(html, expected)

    assert parsed_list.list_status == DivisionListStatus.COUNTS_DISAGREE
    assert parsed_list.printed_list is not None
    assert parsed_list.names == []


def test_a_name_glued_to_a_nil_that_no_column_separates_makes_the_list_unreadable() -> (
    None
):
    html = _get_pre_html(_OPENING, "", "  Ayes", "", "  Aa Bb. Nil.", "  Cc Dd")

    parsed_list = _get_list(html)

    assert parsed_list.list_status == DivisionListStatus.LAYOUT_UNREADABLE
    assert parsed_list.printed_list is not None
    assert parsed_list.names == []


def test_6_september_1956_reads_a_sparse_right_column_from_its_headings() -> None:
    _assert_fixture_is_stored("hansard_list_1956_09_06_glued_column")


def test_a_nil_with_a_full_stop_and_a_misspelt_abstentions_heading_are_not_names() -> (
    None
):
    html = _get_pre_html(
        _OPENING,
        "",
        "  Ayes",
        "",
        "  Aa Bb",
        "  Cc Dd",
        "",
        "  Noes",
        "",
        "  Nil.",
        "",
        "  Abstentations.",
        "",
        "  Ee Ff",
    )

    parsed_list = _get_list(html, 2, 0, abstentions=1)

    assert parsed_list.list_status == DivisionListStatus.STORED
    assert _get_names(parsed_list) == [
        (DivisionVoteChoice.AYE, "Aa Bb"),
        (DivisionVoteChoice.AYE, "Cc Dd"),
        (DivisionVoteChoice.ABSTAIN, "Ee Ff"),
    ]


def test_the_abstentation_heading_opens_the_abstentions_section() -> None:
    html = _get_pre_html(
        _OPENING,
        "",
        "  Ayes",
        "",
        "  Aa Bb",
        "  Cc Dd",
        "",
        "  Noes",
        "",
        "  Gg Hh",
        "",
        "  Abstentation.",
        "",
        "  Ee Ff",
    )

    parsed_list = _get_list(html, 2, 1, abstentions=1)

    assert parsed_list.list_status == DivisionListStatus.STORED
    assert _get_names(parsed_list) == [
        (DivisionVoteChoice.AYE, "Aa Bb"),
        (DivisionVoteChoice.AYE, "Cc Dd"),
        (DivisionVoteChoice.NO, "Gg Hh"),
        (DivisionVoteChoice.ABSTAIN, "Ee Ff"),
    ]


@pytest.mark.parametrize(
    "side_with_a_name_dropped", ["ayes", "abstentions", "absent", "paired"]
)
def test_one_side_short_of_a_name_gives_counts_disagree_and_no_names(
    side_with_a_name_dropped: str,
) -> None:
    html, expected = _read_fixture("hansard_list_1957_12_13")
    expected[side_with_a_name_dropped] += 1

    parsed_list = _get_fixture_list(html, expected)

    assert parsed_list.list_status == DivisionListStatus.COUNTS_DISAGREE
    assert parsed_list.printed_list is not None
    assert parsed_list.names == []


def test_a_name_moved_across_a_column_gives_no_names() -> None:
    html, expected = _read_fixture("hansard_list_1963_06_07")
    moved_html = html.replace(_WRAPPED_NAME_LINE, _MOVED_NAME_LINES)
    assert moved_html != html

    parsed_list = get_division_list(
        moved_html,
        0,
        1,
        expected["ayes"],
        expected["noes"],
        expected["abstentions"],
        expected["absent"],
        expected["paired"],
    )

    assert parsed_list.list_status == DivisionListStatus.COUNTS_DISAGREE
    assert parsed_list.names == []
    assert parsed_list.printed_list is not None


def test_a_list_in_the_same_pre_as_its_opening_line_is_read() -> None:
    html = _get_pre_html(
        _OPENING,
        "",
        "  Ayes          Noes",
        "",
        "  Aa Bb         Cc Dd",
        "  Ee Ff         Gg Hh",
    )

    parsed_list = _get_list(html, 2, 2)

    assert parsed_list.list_status == DivisionListStatus.STORED
    assert _get_names(parsed_list) == [
        (DivisionVoteChoice.AYE, "Aa Bb"),
        (DivisionVoteChoice.NO, "Cc Dd"),
        (DivisionVoteChoice.AYE, "Ee Ff"),
        (DivisionVoteChoice.NO, "Gg Hh"),
    ]


def test_a_bare_heading_with_no_names_is_not_printed() -> None:
    html = (_FIXTURE_DIRECTORY / "hansard_list_1963_04_09_bare_heading.html").read_text(
        encoding="utf-8"
    )
    ayes, noes, abstentions, absent, paired = _BARE_HEADING_COUNTS

    parsed_list = _get_list(html, ayes, noes, abstentions, absent, paired)

    assert parsed_list.list_status == DivisionListStatus.NOT_PRINTED
    assert parsed_list.printed_list is None
    assert parsed_list.names == []


def test_an_image_in_place_of_the_list_is_layout_unreadable() -> None:
    html = (_FIXTURE_DIRECTORY / "hansard_list_image.html").read_text(encoding="utf-8")

    parsed_list = _get_list(html, 80, 0)

    assert parsed_list.list_status == DivisionListStatus.LAYOUT_UNREADABLE
    assert parsed_list.printed_list is None
    assert parsed_list.names == []


def test_a_different_number_of_openings_is_layout_unreadable() -> None:
    html, expected = _read_fixture("hansard_list_1963_06_07")

    parsed_list = _get_list(
        html,
        expected["ayes"] + 1,
        expected["noes"],
        expected["abstentions"],
        expected["absent"],
        expected["paired"],
        division_count=2,
    )

    assert parsed_list.list_status == DivisionListStatus.LAYOUT_UNREADABLE
    assert parsed_list.names == []


def test_no_content_is_layout_unreadable() -> None:
    for content in (None, ""):
        parsed_list = _get_list(content)

        assert parsed_list.list_status == DivisionListStatus.LAYOUT_UNREADABLE
        assert parsed_list.printed_list is None
        assert parsed_list.names == []


def test_a_wrapped_name_and_a_title_cell_are_joined() -> None:
    html = _get_pre_html(
        _OPENING,
        "",
        "  Ayes               Noes",
        "",
        "  Aa bin             Cc Dd",
        "  Bb                 Madam",
        "  Ee Ff              Gg Hh",
        "  Ii Jj              Kk Ll",
    )

    parsed_list = _get_list(html, 3, 3)

    assert parsed_list.list_status == DivisionListStatus.STORED
    assert _get_names(parsed_list) == [
        (DivisionVoteChoice.AYE, "Aa bin Bb"),
        (DivisionVoteChoice.NO, "Cc Dd Madam"),
        (DivisionVoteChoice.AYE, "Ee Ff"),
        (DivisionVoteChoice.NO, "Gg Hh"),
        (DivisionVoteChoice.AYE, "Ii Jj"),
        (DivisionVoteChoice.NO, "Kk Ll"),
    ]


def test_a_sentence_ends_the_list() -> None:
    html = _get_pre_html(
        _OPENING,
        "",
        "  Ayes               Noes",
        "",
        "  Aa Bb              Cc Dd",
        "  Ee Ff              Gg Hh",
    ) + _get_pre_html(
        "The Bill was accordingly passed by the House.",
        "  Ii Jj              Kk Ll",
        "  Mm Nn              Oo Pp",
    )

    parsed_list = _get_list(html, 2, 2)

    assert parsed_list.list_status == DivisionListStatus.STORED
    assert [name.printed_name for name in parsed_list.names] == [
        "Aa Bb",
        "Cc Dd",
        "Ee Ff",
        "Gg Hh",
    ]
    assert parsed_list.printed_list is not None
    assert "accordingly" not in parsed_list.printed_list


def test_12_january_1988_keeps_a_heading_printed_left_of_its_column_out_of_the_name() -> (
    None
):
    _assert_fixture_is_stored("hansard_list_1988_01_12_heading_left_of_its_column")


def test_4_october_1956_keeps_two_absent_names_one_offset_apart_as_two_names() -> None:
    _assert_fixture_is_stored(
        "hansard_list_1956_10_04_absent_names_one_column_offset_apart"
    )


def test_a_name_equally_near_two_heading_columns_makes_the_list_unreadable() -> None:
    html = "<p>The House divided: Ayes, 2; Noes, 2.</p>" + _get_pre_html(
        "      Ayes              Noes              Absent",
        "Lim Ah Kow        Tan Bee Lian      Goh Chok Tong",
        "Lee Kuan Yew      Ng Eng Hen Long Name Here",
        "                             Ong Pang Boon",
    )

    parsed_list = _get_list(html, 2, 2)

    assert parsed_list.list_status == DivisionListStatus.LAYOUT_UNREADABLE
    assert parsed_list.names == []

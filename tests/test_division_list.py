import json
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from enums import DivisionListStatus, DivisionVoteChoice
from services.division_list import (
    ParsedDivisionList,
    get_division_list,
    get_pre_column_starts,
)

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures"
_OPENING = "The House divided: Ayes, 2; Noes, 1."
_WRAPPED_NAME_LINE = "   Buang bin          Bani, S.T."
_MOVED_NAME_LINES = "   Buang bin\r\n   Bani, S.T."
_COLUMN_STARTS_1985_FIRST = [1, 27]
_COLUMN_STARTS_1985_SECOND = [1, 28]
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
        expected["ayes"],
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


def test_a_pre_block_with_no_data_row_has_no_column_starts() -> None:
    assert get_pre_column_starts(["  Ayes          Noes", ""]) is None
    assert get_pre_column_starts([]) is None


def test_a_tie_between_cell_counts_has_no_column_starts() -> None:
    assert get_pre_column_starts(["  Aa Bb         Cc Dd", "  Ee Ff"]) is None


def test_a_pre_block_with_no_column_starts_is_layout_unreadable() -> None:
    html = _get_pre_html(_OPENING, "", "  Ayes          Noes", "", "  Aa Bb         Cc Dd", "  Ee Ff", "  Gg Hh         Ii Jj", "  Kk Ll")

    parsed_list = _get_list(html)

    assert parsed_list.list_status == DivisionListStatus.LAYOUT_UNREADABLE
    assert parsed_list.printed_list is not None
    assert parsed_list.names == []


def test_the_1985_column_starts_come_from_each_pre_block() -> None:
    html, _ = _read_fixture("hansard_list_1985_05_15")
    pre_texts = [
        pre.get_text().replace("\r\n", "\n")
        for pre in BeautifulSoup(html, "html.parser").find_all("pre")
    ]

    column_starts = [get_pre_column_starts(text.split("\n")) for text in pre_texts[:2]]

    assert column_starts == [_COLUMN_STARTS_1985_FIRST, _COLUMN_STARTS_1985_SECOND]


def test_the_cell_count_comes_from_data_rows_only() -> None:
    lines = [
        "  Ayes          Noes",
        "",
        "  Aa Bb",
        "  Cc Dd",
        "  Ee Ff         Gg Hh",
        "  Ii Jj         Kk Ll",
        "  Mm Nn         Oo Pp",
    ]

    assert get_pre_column_starts(lines) == [2, 16]


def test_a_name_equally_near_two_columns_is_layout_unreadable() -> None:
    html = _get_pre_html(
        _OPENING,
        "",
        "  Ayes               Noes",
        "",
        "  Aa Bb              Cc Dd",
        "          Ee Ff",
    )

    parsed_list = _get_list(html)

    assert parsed_list.list_status == DivisionListStatus.LAYOUT_UNREADABLE
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
        "",
        "The Bill was accordingly passed by the House.",
        "  Ii Jj              Kk Ll",
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

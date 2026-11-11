import pytest

from services.leave_section import apply_leave_date_misprints, get_leave_sections
from utils.data_files import get_leave_date_misprints

_LEAVE_DATE_MISPRINT_COUNT = 24
_ENTRY_LINE = "Mr Lee (Tanglin) - from 3rd to 10th June, 1977."
_SECOND_ENTRY_LINE = "Mr Tan (Bedok) - from 4th to 11th June, 1977."


def _get_markdown(heading: str, *lines: str) -> str:
    return "\n".join(["Some earlier text.", "", heading, "", *lines])


@pytest.mark.parametrize(
    "heading",
    [
        "Permission to Members to be Absent",
        "**PERMISSION TO MEMBERS TO BE ABSENT**",
        "Permission to Member to be Absent",
        "PERMISSION TO MEMBERS BE ABSENT",
        "pErMiSsIoN tO mEmBeRs To Be AbSeNt",
        "**Permission to Members to be Absent:**",
        "Permission to Members to be Absent:",
        "# Permission to Members be Absent",
    ],
)
def test_every_heading_form_opens_a_section(heading: str) -> None:
    sections = get_leave_sections(_get_markdown(heading, _ENTRY_LINE))

    assert sections == [[_ENTRY_LINE]]


def test_text_before_a_heading_is_not_a_section() -> None:
    markdown_content = "\n".join([_ENTRY_LINE, "Something else."])

    assert get_leave_sections(markdown_content) == []


def test_a_sitting_with_two_sections_gives_two_sections() -> None:
    markdown_content = "\n".join(
        [
            "Permission to Members to be Absent",
            _ENTRY_LINE,
            "# A new heading",
            "Permission to Members to be Absent",
            _SECOND_ENTRY_LINE,
        ]
    )

    assert get_leave_sections(markdown_content) == [
        [_ENTRY_LINE],
        [_SECOND_ENTRY_LINE],
    ]


def test_a_second_heading_closes_the_open_section() -> None:
    markdown_content = "\n".join(
        [
            "Permission to Members to be Absent",
            _ENTRY_LINE,
            "Permission to Members to be Absent",
            _SECOND_ENTRY_LINE,
        ]
    )

    assert get_leave_sections(markdown_content) == [
        [_ENTRY_LINE],
        [_SECOND_ENTRY_LINE],
    ]


@pytest.mark.parametrize(
    "ending_line",
    [
        "# Another heading",
        "[Mr Speaker in the Chair]",
        "Speaker",
        "| Speaker",
        "| _Deputy Speaker",
        "| | THE SPEAKER",
        "(i) Pawnbrokers (Amendment) Bill;",
        "**ORAL ANSWERS**",
    ],
)
def test_each_end_condition_ends_the_section(ending_line: str) -> None:
    markdown_content = _get_markdown(
        "Permission to Members to be Absent",
        _ENTRY_LINE,
        ending_line,
        _SECOND_ENTRY_LINE,
    )

    assert get_leave_sections(markdown_content) == [[_ENTRY_LINE]]


def test_a_bold_line_before_any_entry_does_not_end_the_section() -> None:
    markdown_content = _get_markdown(
        "Permission to Members to be Absent", "**Notice**", _ENTRY_LINE
    )

    assert get_leave_sections(markdown_content) == [["**Notice**", _ENTRY_LINE]]


def test_a_glued_bold_heading_is_cut_and_ends_the_section() -> None:
    markdown_content = _get_markdown(
        "Permission to Members to be Absent",
        "Mr Seah Peng Chuan - for 47 days from 15th April, 1956. **EXEMPTED BUSINESS** **(Motion)**",
        _SECOND_ENTRY_LINE,
    )

    assert get_leave_sections(markdown_content) == [
        ["Mr Seah Peng Chuan - for 47 days from 15th April, 1956."]
    ]


def test_a_table_line_keeps_a_bold_heading() -> None:
    table_line = "Mr Lee| 5 Apr| 11 Apr **A**"
    markdown_content = _get_markdown(
        "Permission to Members to be Absent", table_line, _SECOND_ENTRY_LINE
    )

    assert get_leave_sections(markdown_content) == [[table_line, _SECOND_ENTRY_LINE]]


def test_a_preamble_line_is_skipped() -> None:
    markdown_content = _get_markdown(
        "Permission to Members to be Absent",
        "Under the provision of clause 2(d)",
        "The following Members have asked for leave:",
        _ENTRY_LINE,
    )

    assert get_leave_sections(markdown_content) == [[_ENTRY_LINE]]


def test_blank_lines_are_skipped() -> None:
    markdown_content = _get_markdown(
        "Permission to Members to be Absent", "", _ENTRY_LINE, "   ", _SECOND_ENTRY_LINE
    )

    assert get_leave_sections(markdown_content) == [[_ENTRY_LINE, _SECOND_ENTRY_LINE]]


def test_a_wrapped_line_is_joined_with_one_space() -> None:
    markdown_content = _get_markdown(
        "Permission to Members to be Absent",
        "Mr Lee (Tanglin), Minister for",
        "Trade - from 3rd to 10th June,",
        "1977.",
        _SECOND_ENTRY_LINE,
    )

    assert get_leave_sections(markdown_content) == [
        [
            "Mr Lee (Tanglin), Minister for Trade - from 3rd to 10th June, 1977.",
            _SECOND_ENTRY_LINE,
        ]
    ]


def test_a_line_without_an_open_prose_entry_is_kept_alone() -> None:
    markdown_content = _get_markdown(
        "Permission to Members to be Absent", "from 3rd to 10th June", "and more"
    )

    assert get_leave_sections(markdown_content) == [
        ["from 3rd to 10th June", "and more"]
    ]


def test_a_table_line_closes_the_open_prose_entry() -> None:
    markdown_content = _get_markdown(
        "Permission to Members to be Absent",
        _ENTRY_LINE,
        "Mr Lee| 5 Apr| 11 Apr",
        "left over",
    )

    assert get_leave_sections(markdown_content) == [
        [_ENTRY_LINE, "Mr Lee| 5 Apr| 11 Apr", "left over"]
    ]


def test_a_section_with_no_entry_is_left_out() -> None:
    markdown_content = _get_markdown(
        "Permission to Members to be Absent", "# Next heading"
    )

    assert get_leave_sections(markdown_content) == []


def test_the_misprint_file_holds_the_listed_entries() -> None:
    assert len(get_leave_date_misprints()) == _LEAVE_DATE_MISPRINT_COUNT


def test_a_misprinted_form_is_fixed() -> None:
    date_text = apply_leave_date_misprints(
        "form 3rd to 1Oth June, 1977", get_leave_date_misprints()
    )

    assert date_text == "from 3rd to 10th June, 1977"


def test_a_misprint_is_fixed_only_as_a_whole_token() -> None:
    date_text = "Information on the form"

    assert (
        apply_leave_date_misprints(date_text, get_leave_date_misprints())
        == "Information on the from"
    )


def test_a_split_day_is_joined() -> None:
    date_text = apply_leave_date_misprints(
        "from 2 5th to 1 6th May", get_leave_date_misprints()
    )

    assert date_text == "from 25th to 16th May"

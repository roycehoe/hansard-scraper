from datetime import date

import pytest

from enums import LeaveEntryFormat, LeaveNameSource, LeaveYearSource
from services.leave_section import (
    apply_leave_date_misprints,
    build_leave_entries_from_markdown,
    get_leave_sections,
)
from utils.data_files import get_leave_date_misprints
from utils.leave_entry import LeaveDates, LeaveEntry

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


_HEADING = "Permission to Members to be Absent"
_SITTING_DATE = date(1977, 6, 8)


def _build_entries(*lines: str, sitting_date: date = _SITTING_DATE) -> list[LeaveEntry]:
    return build_leave_entries_from_markdown(
        _get_markdown(_HEADING, *lines), sitting_date, get_leave_date_misprints()
    )


def _get_date_pairs(leave_entries: list[LeaveEntry]) -> list[tuple[date, date]]:
    return [
        (leave_entry.leave_dates.start_date, leave_entry.leave_dates.end_date)
        for leave_entry in leave_entries
        if leave_entry.leave_dates is not None and leave_entry.leave_dates.end_date
    ]


def test_a_range_with_a_printed_year_is_read() -> None:
    leave_entries = _build_entries("Mr X (Tanglin) - from 3rd to 10th June, 1977.")

    assert len(leave_entries) == 1
    leave_entry = leave_entries[0]
    assert leave_entry.ordinal == 1
    assert leave_entry.printed_name == "Mr X"
    assert leave_entry.carried_name is None
    assert leave_entry.printed_line == "Mr X (Tanglin) - from 3rd to 10th June, 1977."
    assert leave_entry.printed_from == "3rd"
    assert leave_entry.printed_to == "10th June, 1977"
    assert leave_entry.leave_dates == LeaveDates(date(1977, 6, 3), date(1977, 6, 10))
    assert leave_entry.entry_format == LeaveEntryFormat.PROSE_RANGE
    assert leave_entry.name_source == LeaveNameSource.PRINTED
    assert leave_entry.year_source == LeaveYearSource.PRINTED_IN_ENTRY
    assert leave_entry.office_printed is None


def test_a_range_across_two_months_with_a_printed_year() -> None:
    leave_entries = _build_entries(
        "Mr X (Tanglin) - from 21st January to 6th February, 1991."
    )

    assert _get_date_pairs(leave_entries) == [(date(1991, 1, 21), date(1991, 2, 6))]


def test_a_range_across_new_year_with_one_printed_year() -> None:
    leave_entries = _build_entries("Mr X - from 28th December to 4th January, 1991.")

    assert _get_date_pairs(leave_entries) == [(date(1990, 12, 28), date(1991, 1, 4))]


def test_ranges_joined_by_and_with_one_year_at_the_end() -> None:
    leave_entries = _build_entries(
        "Mr X - from 3rd to 5th March and from 10th to 12th April, 1990."
    )

    assert _get_date_pairs(leave_entries) == [
        (date(1990, 3, 3), date(1990, 3, 5)),
        (date(1990, 4, 10), date(1990, 4, 12)),
    ]
    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2]


def test_an_earlier_range_before_new_year_takes_the_year_before() -> None:
    leave_entries = _build_entries(
        "Mr X - from 20th to 28th December and from 2nd to 5th January, 1990."
    )

    assert _get_date_pairs(leave_entries) == [
        (date(1989, 12, 20), date(1989, 12, 28)),
        (date(1990, 1, 2), date(1990, 1, 5)),
    ]


def test_ordinals_count_printings_across_lines() -> None:
    leave_entries = _build_entries(
        "Mr X - from 3rd to 5th March and from 10th to 12th April, 1990.",
        "Mr Y - from 3rd to 5th March, 1990.",
    )

    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2, 3]


def test_a_misprinted_word_is_read_and_kept_in_the_printed_line() -> None:
    leave_entries = _build_entries("Mr X (Tanglin) - form 3rd to 10th June, 1977")

    assert _get_date_pairs(leave_entries) == [(date(1977, 6, 3), date(1977, 6, 10))]
    assert (
        leave_entries[0].printed_line == "Mr X (Tanglin) - form 3rd to 10th June, 1977"
    )
    assert leave_entries[0].printed_from == "3rd"
    assert leave_entries[0].printed_to == "10th June, 1977"


def test_a_misprint_inside_a_matched_date_blanks_that_column_only() -> None:
    leave_entries = _build_entries("Mr X (Tanglin) - from 3rd to 1Oth June, 1977")

    assert _get_date_pairs(leave_entries) == [(date(1977, 6, 3), date(1977, 6, 10))]
    assert leave_entries[0].printed_from == "3rd"
    assert leave_entries[0].printed_to is None


def test_a_range_with_no_from_word_is_read() -> None:
    leave_entries = _build_entries("Mr X (Tanglin) - 3rd to 10th June, 1977")

    assert _get_date_pairs(leave_entries) == [(date(1977, 6, 3), date(1977, 6, 10))]


def test_an_office_after_the_bracket_does_not_cut_on_the_word_for() -> None:
    leave_entries = _build_entries(
        "Mr S. Rajaratnam (Kampong Glam), Minister for Culture - from 7th to 29th May, 1960."
    )

    assert leave_entries[0].printed_name == "Mr S. Rajaratnam"
    assert _get_date_pairs(leave_entries) == [(date(1960, 5, 7), date(1960, 5, 29))]


@pytest.mark.parametrize(
    ("line", "printed_name"),
    [
        (
            "BG (NS) Lee Hsien Loong (Teck Ghee), Minister for Trade and Industry - from 3rd to 10th June, 1990.",
            "BG (NS) Lee Hsien Loong",
        ),
        (
            "RAdm (NS) Teo Chee Hean (Pasir Ris), Minister for Education - from 3rd to 10th March, 1998.",
            "RAdm (NS) Teo Chee Hean",
        ),
        ("Mr X - from 3rd to 10th June, 1977.", "Mr X"),
        (
            "Dr Beng Kian Lam, Arthur - from 29th May to 3rd June, 1993.",
            "Dr Beng Kian Lam, Arthur",
        ),
    ],
)
def test_the_printed_name_keeps_the_title_and_stops_at_the_bracket(
    line: str, printed_name: str
) -> None:
    leave_entries = _build_entries(line)

    assert leave_entries[0].printed_name == printed_name
    assert leave_entries[0].entry_format == LeaveEntryFormat.PROSE_RANGE


def test_a_name_loses_its_trailing_marks() -> None:
    leave_entries = _build_entries(
        "Mr Matthias Yao Chih -- from 21st to 28th March, 1992."
    )

    assert leave_entries[0].printed_name == "Mr Matthias Yao Chih"


def test_a_name_with_a_digit_is_not_stored() -> None:
    leave_entries = _build_entries(
        "Mr Seah Peng Chuan - 29th July (afternoon) and 30th July, 1957;"
    )

    assert len(leave_entries) == 1
    leave_entry = leave_entries[0]
    assert leave_entry.entry_format == LeaveEntryFormat.UNREAD
    assert leave_entry.name_source == LeaveNameSource.NONE
    assert leave_entry.printed_name is None
    assert leave_entry.printed_line == (
        "Mr Seah Peng Chuan - 29th July (afternoon) and 30th July, 1957;"
    )
    assert leave_entry.leave_dates is None
    assert leave_entry.printed_from is None
    assert leave_entry.printed_to is None


@pytest.mark.parametrize(
    ("line", "start_date", "end_date"),
    [
        (
            "Mr X - from 4th January, 1959, to 15th January, 1959;",
            date(1959, 1, 4),
            date(1959, 1, 15),
        ),
        (
            "Mr X - from 5th January, to 8th February, 1967.",
            date(1967, 1, 5),
            date(1967, 2, 8),
        ),
        (
            "Mr X - on 10th to 19th October, 1993",
            date(1993, 10, 10),
            date(1993, 10, 19),
        ),
        (
            "Mr Wong Kan Seng - from 9th to 14th May,1993.",
            date(1993, 5, 9),
            date(1993, 5, 14),
        ),
        (
            "Mr X - from 7th Sept. to 9th Sept., 1960",
            date(1960, 9, 7),
            date(1960, 9, 9),
        ),
    ],
)
def test_other_printed_range_forms_are_read(
    line: str, start_date: date, end_date: date
) -> None:
    leave_entries = _build_entries(line)

    assert _get_date_pairs(leave_entries) == [(start_date, end_date)]
    assert leave_entries[0].year_source == LeaveYearSource.PRINTED_IN_ENTRY


def test_a_range_with_no_year_takes_the_nearest_year() -> None:
    leave_entries = _build_entries(
        "Mr X - from 3rd to 10th June", sitting_date=date(1977, 6, 8)
    )

    assert _get_date_pairs(leave_entries) == [(date(1977, 6, 3), date(1977, 6, 10))]
    assert leave_entries[0].year_source == LeaveYearSource.NEAREST_TO_SITTING


@pytest.mark.parametrize(
    "line",
    [
        "Mr X - from 12th to 15th November, from 5th to 8th December, 1994, and from 18th to 22nd December",
        "Mr X - from 3rd to 5th",
        "Mr X (Tanglin) -- from 21st January to 6th",
        "Mr Chan Chee Seng (Jalan Besar) - from 20th December, 1960, to 31st March, 1961. 2.31 p.m.",
        "Mr X - from 30th to 31st February, 1990.",
    ],
)
def test_a_line_no_rule_reads_in_full_is_unread_with_its_printed_line(
    line: str,
) -> None:
    leave_entries = _build_entries(line)

    assert len(leave_entries) == 1
    leave_entry = leave_entries[0]
    assert leave_entry.entry_format == LeaveEntryFormat.UNREAD
    assert leave_entry.printed_line == line
    assert leave_entry.leave_dates is None
    assert leave_entry.year_source is None
    assert leave_entry.printed_from is None
    assert leave_entry.printed_to is None


def test_a_line_read_in_part_keeps_its_name() -> None:
    leave_entries = _build_entries("Mr X - from 3rd to 5th")

    assert leave_entries[0].printed_name == "Mr X"
    assert leave_entries[0].name_source == LeaveNameSource.PRINTED


def test_a_line_with_no_date_part_has_no_name() -> None:
    leave_entries = _build_entries("Mr Lee Kuan Yew (Tanjong Pagar), Prime Minister.")

    assert leave_entries[0].entry_format == LeaveEntryFormat.UNREAD
    assert leave_entries[0].name_source == LeaveNameSource.NONE
    assert leave_entries[0].printed_name is None


def test_a_misprint_before_the_cut_leaves_the_line_unread() -> None:
    leave_entries = _build_entries("Mr X lst (Tanglin) - from 3rd to 10th June, 1977.")

    assert leave_entries[0].entry_format == LeaveEntryFormat.UNREAD
    assert leave_entries[0].name_source == LeaveNameSource.NONE


def test_a_wrapped_entry_is_read_as_one_line() -> None:
    leave_entries = _build_entries(
        "Mr Lee (Tanglin), Minister for Trade -",
        "from 3rd to 10th June,",
        "1977.",
    )

    assert len(leave_entries) == 1
    assert leave_entries[0].printed_line == (
        "Mr Lee (Tanglin), Minister for Trade - from 3rd to 10th June, 1977."
    )
    assert _get_date_pairs(leave_entries) == [(date(1977, 6, 3), date(1977, 6, 10))]


def test_two_members_with_equal_dates_stay_two_entries() -> None:
    leave_entries = _build_entries(
        "BG (NS) Lee Hsien Loong (Teck Ghee) - from 3rd to 10th June, 1990.",
        "BG (NS) Teo Chee Hean (Pasir Ris) - from 3rd to 10th June, 1990.",
    )

    assert [leave_entry.printed_name for leave_entry in leave_entries] == [
        "BG (NS) Lee Hsien Loong",
        "BG (NS) Teo Chee Hean",
    ]
    assert _get_date_pairs(leave_entries) == [
        (date(1990, 6, 3), date(1990, 6, 10)),
        (date(1990, 6, 3), date(1990, 6, 10)),
    ]


def test_ordinals_run_across_sections() -> None:
    markdown_content = "\n".join(
        [
            _HEADING,
            "Mr X - from 3rd to 5th March, 1990.",
            "# Heading",
            _HEADING,
            "Mr Y - from 6th to 8th March, 1990.",
        ]
    )

    leave_entries = build_leave_entries_from_markdown(
        markdown_content, _SITTING_DATE, get_leave_date_misprints()
    )

    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2]

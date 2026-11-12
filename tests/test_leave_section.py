from datetime import date
from typing import Optional

import pytest

from enums import LeaveEntryFormat, LeaveNameSource, LeaveYearSource
from services.leave_section import (
    apply_leave_date_misprints,
    build_leave_entries_from_markdown,
    get_leave_sections,
)
from utils.data_files import (
    get_leave_date_misprints,
    get_leave_heading_years,
    get_leave_line_readings,
)
from utils.leave_entry import LeaveDates, LeaveEntry

_LEAVE_DATE_MISPRINT_COUNT = 44
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


@pytest.mark.parametrize(
    ("line", "reading"),
    [
        ("from 12th tcr 22nd March, 1984", "from 12th to 22nd March, 1984"),
        ("from 7th to 11rh December, 1996", "from 7th to 11th December, 1996"),
        ("from 13th to 16th December, l987", "from 13th to 16th December, 1987"),
        ("16 Jan| l7 Jan", "16 Jan| 17 Jan"),
        ("on 6th ar,d 7th August", "on 6th and 7th August"),
        ("from from 14th to 16th July", "from 14th to 16th July"),
        ("from 21st to 28th March March,1992", "from 21st to 28th March,1992"),
        ("from 30th May to12thJu ne, 1982", "from 30th May to 12th June, 1982"),
        ("one month from 13th, August, 1960", "one month from 13th August, 1960"),
        ("from 17th to 21st ,August, 1984", "from 17th to 21st August, 1984"),
        ("from 22nd to 25th January , 1993", "from 22nd to 25th January, 1993"),
        ("on 22nd May ,1996", "on 22nd May, 1996"),
        ("to 18th December ,1996", "to 18th December, 1996"),
        ("from 8th to 27th, December, 1996", "from 8th to 27th December, 1996"),
        ("from 28th -September to 31st October", "from 28th September to 31st October"),
        ("from '16th to 23rd January, 1979", "from 16th to 23rd January, 1979"),
        ("and from 29th 31st December, 1987", "and from 29th to 31st December, 1987"),
        ("Speaker from - 9th to 12th February", "Speaker from 9th to 12th February"),
    ],
)
def test_a_listed_token_misprint_is_fixed(line: str, reading: str) -> None:
    assert apply_leave_date_misprints(line, get_leave_date_misprints()) == reading


def test_a_split_day_is_joined() -> None:
    date_text = apply_leave_date_misprints(
        "from 2 5th to 1 6th May", get_leave_date_misprints()
    )

    assert date_text == "from 25th to 16th May"


_HEADING = "Permission to Members to be Absent"
_SITTING_DATE = date(1977, 6, 8)


def _build_entries(*lines: str, sitting_date: date = _SITTING_DATE) -> list[LeaveEntry]:
    return build_leave_entries_from_markdown(
        _get_markdown(_HEADING, *lines),
        sitting_date,
        get_leave_date_misprints(),
        get_leave_heading_years(),
        get_leave_line_readings(),
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


@pytest.mark.parametrize(
    ("line", "printed_name", "office_printed"),
    [
        (
            "Mr Lim Koon Teck- extension of leave from 6th June to 14th June, 1957;",
            "Mr Lim Koon Teck",
            None,
        ),
        (
            "Dr Wong Kwei Cheong - fom 26th to 28th January, 1994.",
            "Dr Wong Kwei Cheong",
            None,
        ),
        (
            "Mr Yong Nyuk Lin (Geylang West), Minister for Education - extended from 16th April to 19th May, 1963.",
            "Mr Yong Nyuk Lin",
            "Minister for Education",
        ),
        (
            "Mr Ong Teng Cheong (Kim Keat), Minister for Culture, Ministry of Communications - ftom 16th to 20th November, 1977.",
            "Mr Ong Teng Cheong",
            "Minister for Culture, Ministry of Communications",
        ),
        (
            "Mr S. Rajaratnam (Kampong Glam), Minister for Foreign Affairs - (i) from 3rd to 8th August, 1967.",
            "Mr S. Rajaratnam",
            "Minister for Foreign Affairs",
        ),
        (
            "BG George Yong-Boon Yeo (Aljunied GRC), Minister of State - from 3rd to 8th August, 1967.",
            "BG George Yong-Boon Yeo",
            "Minister of State",
        ),
    ],
)
def test_the_name_and_the_office_end_at_the_last_dash_before_the_dates(
    line: str, printed_name: str, office_printed: Optional[str]
) -> None:
    leave_entries = _build_entries(line)

    assert leave_entries[0].printed_name == printed_name
    assert leave_entries[0].office_printed == office_printed


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


def test_a_range_whose_end_day_is_before_its_start_day_in_one_month_is_unread_alone() -> (
    None
):
    leave_entries = _build_entries(
        "Dr Augustine H.H. Tan (Whampoa) - from 14th to 10th April, from 24th to 29th April and from 9th to 11th June, 1980.",
        sitting_date=date(1980, 6, 25),
    )

    assert [leave_entry.entry_format for leave_entry in leave_entries] == [
        LeaveEntryFormat.UNREAD,
        LeaveEntryFormat.PROSE_RANGE,
        LeaveEntryFormat.PROSE_RANGE,
    ]
    assert leave_entries[0].leave_dates is None
    assert leave_entries[0].year_source is None
    assert leave_entries[0].printed_from is None
    assert leave_entries[0].printed_name == "Dr Augustine H.H. Tan"
    assert _get_date_pairs(leave_entries[1:]) == [
        (date(1980, 4, 24), date(1980, 4, 29)),
        (date(1980, 6, 9), date(1980, 6, 11)),
    ]


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
        "Mr Chan Sun Wing (Nee Soon) - Absent from all future Assembly sittings until such time as he is able to be present.",
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


def test_a_full_stop_and_a_new_title_start_a_new_entry_on_the_same_line() -> None:
    line = "Mr Heng Chiang Meng -- from 25th to 27th June and from 23rd to 31st July, 1996. Radm Teo Chee Hean -- from 27th to 30th June and from 10th to 17th July, 1996."
    leave_entries = _build_entries(line, sitting_date=date(1996, 7, 12))

    assert [leave_entry.printed_name for leave_entry in leave_entries] == [
        "Mr Heng Chiang Meng",
        "Mr Heng Chiang Meng",
        "Radm Teo Chee Hean",
        "Radm Teo Chee Hean",
    ]
    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2, 3, 4]
    assert {leave_entry.printed_line for leave_entry in leave_entries} == {line}
    assert _get_date_pairs(leave_entries) == [
        (date(1996, 6, 25), date(1996, 6, 27)),
        (date(1996, 7, 23), date(1996, 7, 31)),
        (date(1996, 6, 27), date(1996, 6, 30)),
        (date(1996, 7, 10), date(1996, 7, 17)),
    ]


def test_a_full_stop_inside_a_name_does_not_start_a_new_entry() -> None:
    leave_entries = _build_entries(
        "Mr M. P. D. Nair - from 3rd to 10th June, 1977. Mr S. T. Bani - from 4th to 11th June, 1977."
    )

    assert [leave_entry.printed_name for leave_entry in leave_entries] == [
        "Mr M. P. D. Nair",
        "Mr S. T. Bani",
    ]


@pytest.mark.parametrize(
    "line",
    [
        "Inche Yaacob Bin Mohamed (Bukit Timah), Parliamentary Secretary to the Minister for National Development - 1st June, 1960. At 3.58 p.m. the Sergeant at Arms came and brought the Mace.",
        "Mr Chan Chee Seng (Jalan Besar) - from 20th December, 1960, to 31st March, 1961. 2.31 p.m.",
        'Dr Toh Chin Chye (Rochore), Deputy Prime Minister - from 1st to 10th August, 1963. * * * * The "Guillotine" Motion reads as follows: on Thursday, 1st August, 1963 at 8 p.m. * * *',
        "Inche Yaacob Bin Mohamed Al-Haj (Southern Islands) - from 28th to 30th October, 1964 (permission obtained from Mr Speaker Barker)",
    ],
)
def test_text_after_the_last_date_is_dropped(line: str) -> None:
    leave_entries = _build_entries(line)

    assert len(leave_entries) == 1
    assert leave_entries[0].entry_format != LeaveEntryFormat.UNREAD
    assert leave_entries[0].printed_line == line


def test_a_bracket_before_a_later_date_is_not_dropped() -> None:
    leave_entries = _build_entries(
        "Mr S. Rajaratnam (Kampong Glam), Minister for Foreign Affairs - (i) from 3rd to 8th August, 1967 (ii) from 4th to 8th September, 1967."
    )

    assert _get_formats(leave_entries) == [LeaveEntryFormat.UNREAD]


def test_a_line_read_in_part_keeps_its_name() -> None:
    leave_entries = _build_entries("Mr X - from 3rd to 5th")

    assert leave_entries[0].printed_name == "Mr X"
    assert leave_entries[0].name_source == LeaveNameSource.PRINTED


def test_a_line_with_no_date_part_keeps_its_name() -> None:
    leave_entries = _build_entries("Mr Lee Kuan Yew (Tanjong Pagar), Prime Minister.")

    assert leave_entries[0].entry_format == LeaveEntryFormat.UNREAD
    assert leave_entries[0].name_source == LeaveNameSource.PRINTED
    assert leave_entries[0].printed_name == "Mr Lee Kuan Yew"


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
        markdown_content,
        _SITTING_DATE,
        get_leave_date_misprints(),
        get_leave_heading_years(),
        get_leave_line_readings(),
    )

    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2]


def _get_formats(leave_entries: list[LeaveEntry]) -> list[LeaveEntryFormat]:
    return [leave_entry.entry_format for leave_entry in leave_entries]


def _get_start_dates(leave_entries: list[LeaveEntry]) -> list[date]:
    return [
        leave_entry.leave_dates.start_date
        for leave_entry in leave_entries
        if leave_entry.leave_dates is not None
    ]


@pytest.mark.parametrize(
    "line",
    [
        "Mr X (Tanglin) - on 5th March, 1957",
        "Mr X (Tanglin) - 5th March, 1957",
        "Mr X (Tanglin), Minister for Law - 5th March, 1957.",
        "Mr Goh Keng Swee (Kreta Ayer), Minister for Finance - on 5th March, 1957.",
    ],
)
def test_a_single_day_is_read(line: str) -> None:
    leave_entries = _build_entries(line)

    assert len(leave_entries) == 1
    leave_entry = leave_entries[0]
    assert leave_entry.entry_format == LeaveEntryFormat.PROSE_SINGLE_DAY
    assert leave_entry.leave_dates == LeaveDates(date(1957, 3, 5), date(1957, 3, 5))
    assert leave_entry.year_source == LeaveYearSource.PRINTED_IN_ENTRY
    assert leave_entry.printed_from == "5th March, 1957"
    assert leave_entry.printed_to is None


def test_a_day_list_makes_one_printing_per_day() -> None:
    leave_entries = _build_entries("Mr X (Tanglin) - 5th and 6th March, 1957")

    assert _get_formats(leave_entries) == [LeaveEntryFormat.PROSE_DAY_LIST] * 2
    assert _get_start_dates(leave_entries) == [date(1957, 3, 5), date(1957, 3, 6)]
    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2]
    assert [leave_entry.printed_from for leave_entry in leave_entries] == [
        "5th and 6th March, 1957"
    ] * 2
    assert [leave_entry.printed_to for leave_entry in leave_entries] == [None, None]


def test_a_comma_day_list_makes_three_printings() -> None:
    leave_entries = _build_entries("Mr X (Tanglin) - 5th, 6th and 7th March, 1957")

    assert _get_formats(leave_entries) == [LeaveEntryFormat.PROSE_DAY_LIST] * 3
    assert _get_start_dates(leave_entries) == [
        date(1957, 3, 5),
        date(1957, 3, 6),
        date(1957, 3, 7),
    ]
    assert {leave_entry.printed_from for leave_entry in leave_entries} == {
        "5th, 6th and 7th March, 1957"
    }


def test_a_day_list_after_the_word_on_makes_two_printings() -> None:
    leave_entries = _build_entries("Mr X - on 11th and 12th November, 1981")

    assert _get_start_dates(leave_entries) == [date(1981, 11, 11), date(1981, 11, 12)]


def test_a_day_that_does_not_exist_is_its_own_unread_printing() -> None:
    leave_entries = _build_entries("Mr X - 30th and 31st April, 1957")

    assert _get_formats(leave_entries) == [
        LeaveEntryFormat.PROSE_DAY_LIST,
        LeaveEntryFormat.UNREAD,
    ]
    assert leave_entries[1].printed_from is None


def test_a_mixed_line_makes_one_printing_per_date() -> None:
    leave_entries = _build_entries(
        "Mr X - on 24th April, from 15th to 16th May and from 3rd to 5th June, 1993."
    )

    assert _get_formats(leave_entries) == [LeaveEntryFormat.PROSE_MIXED] * 3
    assert _get_start_dates(leave_entries) == [
        date(1993, 4, 24),
        date(1993, 5, 15),
        date(1993, 6, 3),
    ]
    assert leave_entries[0].leave_dates == LeaveDates(
        date(1993, 4, 24), date(1993, 4, 24)
    )
    assert leave_entries[0].printed_from == "24th April"
    assert leave_entries[0].printed_to is None
    assert leave_entries[1].printed_from == "15th"
    assert leave_entries[1].printed_to == "16th May"
    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2, 3]
    assert {leave_entry.year_source for leave_entry in leave_entries} == {
        LeaveYearSource.PRINTED_IN_ENTRY
    }


def test_a_day_list_and_a_range_make_three_printings() -> None:
    leave_entries = _build_entries(
        "Mr X - on 3rd and 4th January and from 8th to 16th January, 1990."
    )

    assert _get_formats(leave_entries) == [LeaveEntryFormat.PROSE_MIXED] * 3
    assert _get_start_dates(leave_entries) == [
        date(1990, 1, 3),
        date(1990, 1, 4),
        date(1990, 1, 8),
    ]
    assert leave_entries[0].printed_from == "3rd and 4th January"
    assert leave_entries[1].printed_from == "3rd and 4th January"


def test_two_single_days_with_the_word_on_make_two_printings() -> None:
    leave_entries = _build_entries("Mr X - on 3rd February and on 27th February, 1995.")

    assert _get_formats(leave_entries) == [LeaveEntryFormat.PROSE_MIXED] * 2
    assert _get_start_dates(leave_entries) == [date(1995, 2, 3), date(1995, 2, 27)]


def test_a_single_day_and_a_range_make_two_printings() -> None:
    leave_entries = _build_entries(
        "Mr X - on 5th March and from 7th to 9th April, 1957."
    )

    assert leave_entries[0].leave_dates == LeaveDates(
        date(1957, 3, 5), date(1957, 3, 5)
    )
    assert leave_entries[1].leave_dates == LeaveDates(
        date(1957, 4, 7), date(1957, 4, 9)
    )


def test_a_mixed_line_across_new_year_dates_the_first_printing_a_year_back() -> None:
    leave_entries = _build_entries(
        "Mr X - on 30th December and from 2nd to 5th January, 1990."
    )

    assert _get_start_dates(leave_entries) == [date(1989, 12, 30), date(1990, 1, 2)]


def test_two_ranges_with_years_printed_make_two_range_printings() -> None:
    leave_entries = _build_entries(
        "Mr X - from 28th December, 1968, to 11th February, 1969; and from 21st March to 3rd April, 1969."
    )

    assert _get_formats(leave_entries) == [LeaveEntryFormat.PROSE_RANGE] * 2
    assert _get_date_pairs(leave_entries) == [
        (date(1968, 12, 28), date(1969, 2, 11)),
        (date(1969, 3, 21), date(1969, 4, 3)),
    ]


@pytest.mark.parametrize(
    "line",
    [
        "Mr X - on 5th March and to the end of April, 1957",
        "Mr X - on 6th and 11th December and from 17th to 18th December ,,1996.",
        "Mr X - on 5th March and on 7th April",
    ],
)
def test_a_mixed_shaped_line_the_rule_cannot_read_is_unread(line: str) -> None:
    leave_entries = _build_entries(line)

    assert _get_formats(leave_entries) == [LeaveEntryFormat.UNREAD]
    assert leave_entries[0].printed_line == line
    assert leave_entries[0].printed_name == "Mr X"


@pytest.mark.parametrize(
    ("line", "start_date", "end_date"),
    [
        (
            "Mr X (Tanglin) - for 8 weeks from 7th April, 1956",
            date(1956, 4, 7),
            date(1956, 6, 1),
        ),
        ("Mr X - two weeks, from 3rd May, 1960", date(1960, 5, 3), date(1960, 5, 16)),
        ("Mr X - Two Weeks, from 3rd May, 1960", date(1960, 5, 3), date(1960, 5, 16)),
        (
            "Mr X - for a period of 8 weeks from 7th April, 1956",
            date(1956, 4, 7),
            date(1956, 6, 1),
        ),
        (
            "Mr X - thirteen days from 3rd May, 1960",
            date(1960, 5, 3),
            date(1960, 5, 15),
        ),
        (
            "Mr X - fourteen days from 3rd May, 1960",
            date(1960, 5, 3),
            date(1960, 5, 16),
        ),
        ("Mr X - one month from 3rd May, 1960", date(1960, 5, 3), date(1960, 6, 2)),
        (
            "Mr X - three months from 15th November, 1960",
            date(1960, 11, 15),
            date(1961, 2, 14),
        ),
        ("Mr X - 1 year from 3rd May, 1960", date(1960, 5, 3), date(1961, 5, 2)),
        (
            "Mr X - two years from 1st January, 1960",
            date(1960, 1, 1),
            date(1961, 12, 31),
        ),
    ],
)
def test_a_duration_is_counted_from_its_start_day(
    line: str, start_date: date, end_date: date
) -> None:
    leave_entries = _build_entries(line)

    assert len(leave_entries) == 1
    leave_entry = leave_entries[0]
    assert leave_entry.entry_format == LeaveEntryFormat.PROSE_DURATION
    assert leave_entry.leave_dates == LeaveDates(start_date, end_date)
    assert leave_entry.year_source == LeaveYearSource.PRINTED_IN_ENTRY
    assert leave_entry.office_printed is None
    assert leave_entry.printed_to is None
    assert leave_entry.printed_line == line


@pytest.mark.parametrize(
    ("line", "start_date", "end_date"),
    [
        (
            "Mr M. P. D. Nair - six weeks, commencing from the 29th of November, 1955.",
            date(1955, 11, 29),
            date(1956, 1, 9),
        ),
        (
            "Mr R. Jumabhoy - seven weeks, from the 7th of December, 1955.",
            date(1955, 12, 7),
            date(1956, 1, 24),
        ),
        (
            "Mr Wong Foo Nam - 20 days, from the 19th of December, 1955.",
            date(1955, 12, 19),
            date(1956, 1, 7),
        ),
        (
            "Mr A. R. Lazarous - one month, from the 9th of January, 1956.",
            date(1956, 1, 9),
            date(1956, 2, 8),
        ),
        (
            "Inche Buang Bin Omar Junid (Kallang) - one month from 13th, August, 1960.",
            date(1960, 8, 13),
            date(1960, 9, 12),
        ),
    ],
)
def test_a_duration_in_the_older_wordings_is_counted(
    line: str, start_date: date, end_date: date
) -> None:
    leave_entries = _build_entries(line)

    assert _get_formats(leave_entries) == [LeaveEntryFormat.PROSE_DURATION]
    assert leave_entries[0].leave_dates == LeaveDates(start_date, end_date)


@pytest.mark.parametrize(
    ("line", "expected_dates"),
    [
        (
            "Dr Sheng Nam Chin (Nee Soon) - two weeks from 13th to 27th October, 1960.",
            [(date(1960, 10, 13), date(1960, 10, 27))],
        ),
        (
            "Mr G. Kandasamy (Kampong Kapor), Deputy Speaker, - for seven weeks from 4th June to 23rd July, 1961.",
            [(date(1961, 6, 4), date(1961, 7, 23))],
        ),
        (
            "Mr David S. Marshall - two days, 5th and 6th March, 1957.",
            [
                (date(1957, 3, 5), date(1957, 3, 5)),
                (date(1957, 3, 6), date(1957, 3, 6)),
            ],
        ),
    ],
)
def test_a_count_before_a_printed_range_or_day_list_is_dropped(
    line: str, expected_dates: list[tuple[date, date]]
) -> None:
    leave_entries = _build_entries(line)

    assert _get_date_pairs(leave_entries) == expected_dates
    assert LeaveEntryFormat.UNREAD not in _get_formats(leave_entries)


def test_a_duration_and_a_range_on_one_line_make_two_printings() -> None:
    leave_entries = _build_entries(
        "Tun Lim Yew Hock (Cairnhill) - three weeks from 12th August, 1960; and from 21st to 26th September, 1960."
    )

    assert _get_formats(leave_entries) == [
        LeaveEntryFormat.PROSE_DURATION,
        LeaveEntryFormat.PROSE_RANGE,
    ]
    assert _get_date_pairs(leave_entries) == [
        (date(1960, 8, 12), date(1960, 9, 1)),
        (date(1960, 9, 21), date(1960, 9, 26)),
    ]
    assert leave_entries[1].printed_to == "26th September, 1960"


@pytest.mark.parametrize(
    ("line", "start_date", "end_date"),
    [
        (
            "Mr Ong Piah Teng - for one month from 17th August.",
            date(1955, 8, 17),
            date(1955, 9, 16),
        ),
        (
            "Mr G. A. P. Sutherland - for two months from 26th August.",
            date(1955, 8, 26),
            date(1955, 10, 25),
        ),
        (
            "Inche Ahmad Bin Ibrahim - for three weeks from 28th August.",
            date(1955, 8, 28),
            date(1955, 9, 17),
        ),
    ],
)
def test_a_duration_with_no_year_takes_the_year_nearest_the_sitting(
    line: str, start_date: date, end_date: date
) -> None:
    leave_entries = _build_entries(line, sitting_date=date(1955, 9, 21))

    assert _get_formats(leave_entries) == [LeaveEntryFormat.PROSE_DURATION]
    assert leave_entries[0].leave_dates == LeaveDates(start_date, end_date)
    assert leave_entries[0].year_source == LeaveYearSource.NEAREST_TO_SITTING


def test_a_duration_keeps_the_start_date_text_and_the_words_in_the_line() -> None:
    leave_entries = _build_entries("Mr X - for 8 weeks from 7th April, 1956")

    assert leave_entries[0].printed_from == "7th April, 1956"


def test_a_duration_ending_on_a_day_its_month_lacks_is_unread() -> None:
    leave_entries = _build_entries("Mr X - one month from 31st January, 1961")

    assert _get_formats(leave_entries) == [LeaveEntryFormat.UNREAD]


def test_a_from_only_entry_has_no_end() -> None:
    leave_entries = _build_entries("Mr X (Tanglin) - from 7th April, 1956")

    assert len(leave_entries) == 1
    leave_entry = leave_entries[0]
    assert leave_entry.entry_format == LeaveEntryFormat.PROSE_DURATION
    assert leave_entry.leave_dates == LeaveDates(date(1956, 4, 7), None)
    assert leave_entry.printed_from == "7th April, 1956"
    assert leave_entry.printed_to is None
    assert leave_entry.end_text is None


def test_a_from_only_entry_with_a_day_that_does_not_exist_is_unread() -> None:
    leave_entries = _build_entries("Mr X - from 31st April, 1956")

    assert _get_formats(leave_entries) == [LeaveEntryFormat.UNREAD]
    assert leave_entries[0].printed_name == "Mr X"


def test_a_duration_with_text_left_over_is_unread() -> None:
    leave_entries = _build_entries(
        "Mr X - three weeks from 12th August, 1960; and the first week in October."
    )

    assert _get_formats(leave_entries) == [LeaveEntryFormat.UNREAD]


_TABLE_SITTING_DATE = date(2006, 5, 3)


def _get_names(
    leave_entries: list[LeaveEntry],
) -> list[tuple[Optional[str], Optional[str], LeaveNameSource]]:
    return [
        (leave_entry.printed_name, leave_entry.carried_name, leave_entry.name_source)
        for leave_entry in leave_entries
    ]


def test_a_table_row_reads_its_dates_in_the_heading_year() -> None:
    leave_entries = _build_entries(
        "| (2006) | (2006)",
        "Mr Zulkifli Baharudin| 26 Apr| 28 Apr",
        "| 5 May| 11 May",
        sitting_date=_TABLE_SITTING_DATE,
    )

    assert _get_formats(leave_entries) == [LeaveEntryFormat.TABLE_ROW] * 2
    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2]
    assert _get_date_pairs(leave_entries) == [
        (date(2006, 4, 26), date(2006, 4, 28)),
        (date(2006, 5, 5), date(2006, 5, 11)),
    ]
    assert _get_names(leave_entries) == [
        ("Mr Zulkifli Baharudin", None, LeaveNameSource.PRINTED),
        (None, "Mr Zulkifli Baharudin", LeaveNameSource.CARRIED_FROM_ROW_ABOVE),
    ]
    first_entry = leave_entries[0]
    assert first_entry.year_source == LeaveYearSource.PRINTED_COLUMN_HEADING
    assert first_entry.printed_from == "26 Apr"
    assert first_entry.printed_to == "28 Apr"
    assert first_entry.printed_line == "Mr Zulkifli Baharudin| 26 Apr| 28 Apr"
    assert first_entry.printed_heading_from == "(2006)"
    assert first_entry.printed_heading_to == "(2006)"
    assert first_entry.office_printed is None
    assert first_entry.end_text is None


def test_a_row_with_no_name_carries_the_name_above() -> None:
    leave_entries = _build_entries(
        "Mr Alvin Yeo | 11 Apr | 14 Apr",
        "30 Apr | 06 May",
        sitting_date=_TABLE_SITTING_DATE,
    )

    assert _get_names(leave_entries) == [
        ("Mr Alvin Yeo", None, LeaveNameSource.PRINTED),
        (None, "Mr Alvin Yeo", LeaveNameSource.CARRIED_FROM_ROW_ABOVE),
    ]
    assert _get_date_pairs(leave_entries)[1] == (date(2006, 4, 30), date(2006, 5, 6))


def test_a_row_with_an_empty_first_cell_reads_the_name_after_it() -> None:
    leave_entries = _build_entries(
        "|  | Mr Goh Chok Tong| 30 Jan| 05 Feb", sitting_date=date(1998, 2, 2)
    )

    assert _get_names(leave_entries) == [
        ("Mr Goh Chok Tong", None, LeaveNameSource.PRINTED)
    ]
    assert _get_date_pairs(leave_entries) == [(date(1998, 1, 30), date(1998, 2, 5))]
    assert leave_entries[0].year_source == LeaveYearSource.NEAREST_TO_SITTING
    assert leave_entries[0].printed_heading_from is None
    assert leave_entries[0].printed_heading_to is None


def test_a_row_with_no_name_above_has_no_name() -> None:
    leave_entries = _build_entries("| 5 May| 11 May", sitting_date=_TABLE_SITTING_DATE)

    assert _get_names(leave_entries) == [(None, None, LeaveNameSource.NONE)]
    assert _get_formats(leave_entries) == [LeaveEntryFormat.TABLE_ROW]


def test_a_spacer_line_leaves_the_heading_and_the_carried_name() -> None:
    leave_entries = _build_entries(
        "| (2006) | (2006)",
        "Mr A| 5 Jan| 9 Jan",
        "|  |",
        "| 12 Jan| 15 Jan",
        sitting_date=date(2006, 1, 10),
    )

    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2]
    second_entry = leave_entries[1]
    assert second_entry.carried_name == "Mr A"
    assert second_entry.year_source == LeaveYearSource.PRINTED_COLUMN_HEADING
    assert second_entry.printed_heading_from == "(2006)"
    assert second_entry.leave_dates == LeaveDates(date(2006, 1, 12), date(2006, 1, 15))


def test_a_heading_split_over_three_lines_gives_its_years() -> None:
    leave_entries = _build_entries(
        "| **Name** | **From",
        "(2006)** | **To",
        "(2006) **",
        "Mr A| 5 Jan| 9 Jan",
        sitting_date=date(2006, 1, 10),
    )

    assert len(leave_entries) == 1
    assert leave_entries[0].printed_heading_from == "(2006)"
    assert leave_entries[0].printed_heading_to == "(2006)"
    assert leave_entries[0].leave_dates == LeaveDates(
        date(2006, 1, 5), date(2006, 1, 9)
    )


def test_a_pair_heading_split_over_two_lines_gives_both_years() -> None:
    leave_entries = _build_entries(
        "| **Name** | **From (2006/",
        "2007)** | **To**",
        "Mr A| 5 Jan| 9 Jan",
        sitting_date=date(2007, 1, 8),
    )

    assert len(leave_entries) == 1
    assert leave_entries[0].printed_heading_from == "(2006/2007)"
    assert leave_entries[0].printed_heading_to is None
    assert leave_entries[0].leave_dates == LeaveDates(
        date(2007, 1, 5), date(2007, 1, 9)
    )


def test_a_bare_heading_year_is_read() -> None:
    leave_entries = _build_entries(
        "| 1998| 1998", "Mr A| 5 Jan| 9 Jan", sitting_date=date(1998, 1, 14)
    )

    assert leave_entries[0].printed_heading_from == "1998"
    assert leave_entries[0].printed_heading_to == "1998"
    assert leave_entries[0].leave_dates == LeaveDates(
        date(1998, 1, 5), date(1998, 1, 9)
    )


def test_a_two_digit_second_heading_year_takes_the_century() -> None:
    leave_entries = _build_entries(
        "| 1997/98| 1997/98", "Mr A| 5 Jan| 9 Jan", sitting_date=date(1998, 1, 14)
    )

    assert leave_entries[0].printed_heading_from == "1997/98"
    assert leave_entries[0].printed_heading_to == "1997/98"
    assert leave_entries[0].leave_dates == LeaveDates(
        date(1998, 1, 5), date(1998, 1, 9)
    )


def test_a_pair_heading_across_a_century_reads_the_next_century() -> None:
    leave_entries = _build_entries(
        "| 1999/00| 1999/00", "Mr A| 5 Jan| 9 Jan", sitting_date=date(2000, 1, 14)
    )

    assert leave_entries[0].leave_dates == LeaveDates(
        date(2000, 1, 5), date(2000, 1, 9)
    )


def test_a_new_year_row_under_a_pair_heading_ends_in_the_next_year() -> None:
    leave_entries = _build_entries(
        "| 1997/98| 1997/98", "Mr A| 30 Dec| 3 Jan", sitting_date=date(1998, 1, 1)
    )

    assert leave_entries[0].leave_dates == LeaveDates(
        date(1997, 12, 30), date(1998, 1, 3)
    )


def test_a_dash_in_the_to_column_is_one_day() -> None:
    leave_entries = _build_entries(
        "| 2006| 2006", "Mr A| 5 Jan| -", sitting_date=date(2006, 1, 5)
    )

    assert leave_entries[0].leave_dates == LeaveDates(
        date(2006, 1, 5), date(2006, 1, 5)
    )
    assert leave_entries[0].printed_to == "-"


def test_a_repeated_heading_after_a_page_break_replaces_the_old_one() -> None:
    leave_entries = _build_entries(
        "| 2006| 2006",
        "Mr A| 5 Jan| 9 Jan",
        "| 2007| 2007",
        "| 12 Jan| 15 Jan",
        sitting_date=date(2007, 1, 10),
    )

    second_entry = leave_entries[1]
    assert second_entry.carried_name == "Mr A"
    assert second_entry.printed_heading_from == "2007"
    assert second_entry.leave_dates == LeaveDates(date(2007, 1, 12), date(2007, 1, 15))


def test_a_cell_that_prints_its_year_is_read_with_that_year() -> None:
    leave_entries = _build_entries(
        "| 1990| 1990",
        "Mr A| 5 Jan 1998| 9 Jan 1998",
        "Mr B| 28 Dec 1997| 2 Jan",
        "Mr C| 28 Dec| 2 Jan 1998",
        sitting_date=date(1998, 1, 1),
    )

    assert _get_date_pairs(leave_entries) == [
        (date(1998, 1, 5), date(1998, 1, 9)),
        (date(1997, 12, 28), date(1998, 1, 2)),
        (date(1997, 12, 28), date(1998, 1, 2)),
    ]
    assert {leave_entry.year_source for leave_entry in leave_entries} == {
        LeaveYearSource.PRINTED_IN_ENTRY
    }


def test_a_row_with_a_day_its_month_lacks_is_unread_with_its_name() -> None:
    leave_entries = _build_entries(
        "| 2006| 2006", "Mr X| 31 Apr| 31 Apr", sitting_date=_TABLE_SITTING_DATE
    )

    assert len(leave_entries) == 1
    leave_entry = leave_entries[0]
    assert leave_entry.entry_format == LeaveEntryFormat.UNREAD
    assert leave_entry.printed_name == "Mr X"
    assert leave_entry.leave_dates is None
    assert leave_entry.year_source is None
    assert leave_entry.printed_from is None
    assert leave_entry.printed_to is None
    assert leave_entry.printed_line == "Mr X| 31 Apr| 31 Apr"


def test_a_row_with_one_date_is_unread_and_the_next_row_keeps_the_heading() -> None:
    leave_entries = _build_entries(
        "| 2006| 2006",
        "Mr C| 12 May|",
        "| 15 May| 17 May",
        sitting_date=_TABLE_SITTING_DATE,
    )

    assert _get_formats(leave_entries) == [
        LeaveEntryFormat.UNREAD,
        LeaveEntryFormat.TABLE_ROW,
    ]
    assert _get_names(leave_entries) == [
        ("Mr C", None, LeaveNameSource.PRINTED),
        (None, "Mr C", LeaveNameSource.CARRIED_FROM_ROW_ABOVE),
    ]
    assert leave_entries[1].year_source == LeaveYearSource.PRINTED_COLUMN_HEADING
    assert leave_entries[0].printed_heading_from == "2006"


def test_a_single_cell_row_with_a_digit_and_no_dates_is_unread_with_no_name() -> None:
    leave_entries = _build_entries(
        "| 2002| 2002",
        "Mr A| 5 Oct| 6 Oct",
        "| _Mr Seng Han Thong 29 Sep_",
        "| 10 Oct| 11 Oct",
        sitting_date=date(2002, 10, 1),
    )

    assert _get_formats(leave_entries) == [
        LeaveEntryFormat.TABLE_ROW,
        LeaveEntryFormat.UNREAD,
        LeaveEntryFormat.TABLE_ROW,
    ]
    assert _get_names(leave_entries)[1] == (None, None, LeaveNameSource.NONE)
    assert leave_entries[1].printed_line == "| _Mr Seng Han Thong 29 Sep_"
    assert leave_entries[2].carried_name == "Mr A"


def test_an_italic_one_cell_row_is_read_as_a_table_row() -> None:
    leave_entries = _build_entries(
        "| (2002)| (2002)",
        "| _Mr Seng Han Thong 29 Sep 9 Oct_",
        "| _15 Oct 19 Oct_",
        sitting_date=date(2002, 10, 1),
    )

    assert _get_formats(leave_entries) == [
        LeaveEntryFormat.TABLE_ROW,
        LeaveEntryFormat.TABLE_ROW,
    ]
    assert _get_names(leave_entries) == [
        ("Mr Seng Han Thong", None, LeaveNameSource.PRINTED),
        (None, "Mr Seng Han Thong", LeaveNameSource.CARRIED_FROM_ROW_ABOVE),
    ]
    assert _get_date_pairs(leave_entries) == [
        (date(2002, 9, 29), date(2002, 10, 9)),
        (date(2002, 10, 15), date(2002, 10, 19)),
    ]
    assert leave_entries[0].printed_line == "| _Mr Seng Han Thong 29 Sep 9 Oct_"
    assert leave_entries[0].year_source == LeaveYearSource.PRINTED_COLUMN_HEADING


@pytest.mark.parametrize(
    ("line", "sitting_date", "expected_dates"),
    [
        (
            "| 15 Dec| 1 Jan 01",
            date(2000, 11, 22),
            (date(2000, 12, 15), date(2001, 1, 1)),
        ),
        (
            "Dr Lee Boon Yang| 22 Dec| 2 Jan 99",
            date(1998, 11, 23),
            (date(1998, 12, 22), date(1999, 1, 2)),
        ),
        (
            "| 23 December| 1 January 98",
            date(1997, 11, 19),
            (date(1997, 12, 23), date(1998, 1, 1)),
        ),
    ],
)
def test_a_table_cell_with_a_two_digit_year_uses_that_year(
    line: str, sitting_date: date, expected_dates: tuple[date, date]
) -> None:
    leave_entries = _build_entries(line, sitting_date=sitting_date)

    assert _get_date_pairs(leave_entries) == [expected_dates]
    assert leave_entries[0].year_source == LeaveYearSource.PRINTED_IN_ENTRY


def test_a_glued_day_and_month_in_a_table_cell_is_read() -> None:
    leave_entries = _build_entries(
        "| 2001| 2001",
        "Mr David Lim T E| 8 Apr| 9Apr",
        sitting_date=date(2001, 4, 19),
    )

    assert _get_date_pairs(leave_entries) == [(date(2001, 4, 8), date(2001, 4, 9))]
    assert leave_entries[0].printed_to == "9Apr"


def test_a_table_row_with_two_ranges_gives_a_row_per_range() -> None:
    leave_entries = _build_entries(
        "| 2009| 2009",
        "Mr A| 09 May| 12 May | 17 May| 18 May",
        "| 24 May| 26 May",
        sitting_date=date(2009, 5, 18),
    )

    assert _get_date_pairs(leave_entries) == [
        (date(2009, 5, 9), date(2009, 5, 12)),
        (date(2009, 5, 17), date(2009, 5, 18)),
        (date(2009, 5, 24), date(2009, 5, 26)),
    ]
    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2, 3]
    assert (
        _get_names(leave_entries)[:2] == [("Mr A", None, LeaveNameSource.PRINTED)] * 2
    )
    assert leave_entries[1].printed_from == "17 May"
    assert leave_entries[1].printed_line == "Mr A| 09 May| 12 May | 17 May| 18 May"


@pytest.mark.parametrize(
    "line", ["Dr Ow Chin Hock| | 4 13", "Mr Ong Kian Min| 24 Apr |"]
)
def test_a_table_row_without_a_month_or_a_to_cell_stays_unread(line: str) -> None:
    leave_entries = _build_entries(line, sitting_date=date(2003, 4, 24))

    assert _get_formats(leave_entries) == [LeaveEntryFormat.UNREAD]


def test_an_italic_one_cell_entry_is_read_as_prose_and_the_rows_around_it_are_unchanged() -> (
    None
):
    line = "| _Mr Lee Kuan Yew (Tanjong Pagar), Prime Minister - on 8th April, 1969._"
    leave_entries = _build_entries(
        "| 1969| 1969",
        "Mr A| 5 Apr| 9 Apr",
        line,
        "| 10 Apr| 12 Apr",
        sitting_date=date(1969, 4, 8),
    )

    assert _get_formats(leave_entries) == [
        LeaveEntryFormat.TABLE_ROW,
        LeaveEntryFormat.PROSE_SINGLE_DAY,
        LeaveEntryFormat.TABLE_ROW,
    ]
    prose_entry = leave_entries[1]
    assert prose_entry.printed_line == line
    assert prose_entry.printed_name == "Mr Lee Kuan Yew"
    assert prose_entry.name_source == LeaveNameSource.PRINTED
    assert prose_entry.office_printed == "Prime Minister"
    assert prose_entry.leave_dates == LeaveDates(date(1969, 4, 8), date(1969, 4, 8))
    assert leave_entries[2].carried_name == "Mr A"
    assert leave_entries[2].printed_heading_from == "1969"
    assert leave_entries[2].leave_dates == LeaveDates(
        date(1969, 4, 10), date(1969, 4, 12)
    )


def test_an_italic_one_cell_range_is_read_as_prose() -> None:
    leave_entries = _build_entries(
        "| _Mr Yeoh Ghim Seng (Joo Chiat), Deputy Speaker - from 21st to 31st March, 1969._"
    )

    assert _get_formats(leave_entries) == [LeaveEntryFormat.PROSE_RANGE]
    assert leave_entries[0].printed_from == "21st"
    assert leave_entries[0].printed_to == "31st March, 1969"


def test_unread_rows_with_a_name_cell_give_that_name_to_the_next_blank_row() -> None:
    leave_entries = _build_entries(
        "| 2006| 2006",
        "Mr G| |",
        "Mr H| 26 Apr|",
        "| 5 May| 11 May",
        sitting_date=_TABLE_SITTING_DATE,
    )

    assert _get_formats(leave_entries) == [
        LeaveEntryFormat.UNREAD,
        LeaveEntryFormat.UNREAD,
        LeaveEntryFormat.TABLE_ROW,
    ]
    assert _get_names(leave_entries) == [
        ("Mr G", None, LeaveNameSource.PRINTED),
        ("Mr H", None, LeaveNameSource.PRINTED),
        (None, "Mr H", LeaveNameSource.CARRIED_FROM_ROW_ABOVE),
    ]
    assert leave_entries[2].year_source == LeaveYearSource.PRINTED_COLUMN_HEADING


def test_a_table_row_is_read_after_the_misprint_list_and_keeps_the_print() -> None:
    line = "Mr B| 7 Septmber| 9 September"
    leave_entries = _build_entries("| 1977| 1977", line, sitting_date=date(1977, 9, 8))

    assert leave_entries[0].leave_dates == LeaveDates(
        date(1977, 9, 7), date(1977, 9, 9)
    )
    assert leave_entries[0].printed_line == line
    assert leave_entries[0].printed_from is None
    assert leave_entries[0].printed_to is None


def test_a_table_name_keeps_its_title_and_bracketed_words() -> None:
    leave_entries = _build_entries(
        "RAdm (NS) Lui Tuck Yew| 05 Dec| 14 Dec", sitting_date=date(2006, 12, 6)
    )

    assert leave_entries[0].printed_name == "RAdm (NS) Lui Tuck Yew"
    assert leave_entries[0].leave_dates == LeaveDates(
        date(2006, 12, 5), date(2006, 12, 14)
    )


def test_table_rows_and_prose_lines_share_one_run_of_ordinals() -> None:
    leave_entries = _build_entries(
        "Mr X - from 3rd to 5th March, 1990.",
        "|  |",
        "Mr A| 5 Mar| 9 Mar",
        "| 12 Mar| 15 Mar",
        sitting_date=date(1990, 3, 8),
    )

    assert _get_formats(leave_entries) == [
        LeaveEntryFormat.PROSE_RANGE,
        LeaveEntryFormat.TABLE_ROW,
        LeaveEntryFormat.TABLE_ROW,
    ]
    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2, 3]


@pytest.mark.parametrize(
    ("line", "office_printed"),
    [
        (
            "Mr S. Rajaratnam (Kampong Glam), Minister for Culture - from 7th to 29th May, 1960.",
            "Minister for Culture",
        ),
        (
            "Mr Goh Keng Swee (Kreta Ayer), Minister for Finance - on 5th March, 1967.",
            "Minister for Finance",
        ),
        (
            "Mr X (Tanglin), Minister of State for Law - 5th March, 1967.",
            "Minister of State for Law",
        ),
        (
            "BG (NS) Lee Hsien Loong (Teck Ghee), Minister for Trade and Industry - from 3rd to 10th June, 1990.",
            "Minister for Trade and Industry",
        ),
        (
            "RAdm (NS) Teo Chee Hean (Pasir Ris), Minister for Education - on 5th March, 1998.",
            "Minister for Education",
        ),
        (
            "Mr X (Tanglin), Deputy Speaker, - from 3rd to 5th June, 1977.",
            "Deputy Speaker",
        ),
        (
            "Mr Lee Khoon Choy (Bukit Panjang) Parliamentary Secretary to the Minister for Culture - from 16th February to 10th March, 1960.",
            "Parliamentary Secretary to the Minister for Culture",
        ),
        (
            "Mr S. Rajaratnam (Kampong Glam). Minister for Foreign Affairs - from 3rd to 30th October, 1972.",
            "Minister for Foreign Affairs",
        ),
        (
            "Dr Yeo Ning Hong (Kim Seng) - Minister for Communications - from 3rd to 30th October, 1988.",
            "Minister for Communications",
        ),
    ],
)
def test_the_office_after_the_constituency_bracket_is_stored(
    line: str, office_printed: str
) -> None:
    leave_entries = _build_entries(line)

    assert leave_entries[0].office_printed == office_printed
    assert leave_entries[0].entry_format != LeaveEntryFormat.UNREAD


@pytest.mark.parametrize(
    "line",
    [
        "Mr X (Tanglin) - form 3rd to 10th June, 1977",
        "Mr X - from 3rd to 10th June, 1977.",
        "Dr Beng Kian Lam, Arthur - from 29th May to 3rd June, 1993.",
        "Mr X (Tanglin) - with effect from 3rd June, 1977",
        "Mr X (Tanglin), - from 3rd to 5th June, 1977.",
    ],
)
def test_a_line_with_no_office_after_the_bracket_stores_none(line: str) -> None:
    leave_entries = _build_entries(line)

    assert leave_entries[0].office_printed is None


def test_text_after_the_bracket_with_no_comma_is_no_office_on_an_unread_line() -> None:
    leave_entries = _build_entries(
        "Mr Lee Tee Tong (Bukit Timah) - Pursuant to Mr Speaker's letter dated 31st January, 1964, to be absent"
    )

    assert leave_entries[0].entry_format == LeaveEntryFormat.UNREAD
    assert leave_entries[0].office_printed is None


def test_every_printing_of_a_line_carries_its_office() -> None:
    leave_entries = _build_entries(
        "Mr X (Tanglin), Minister for Law - on 5th and 6th March, 1967."
    )

    assert [leave_entry.office_printed for leave_entry in leave_entries] == [
        "Minister for Law",
        "Minister for Law",
    ]


def test_a_one_year_heading_offers_that_year_and_the_year_before() -> None:
    leave_entries = _build_entries(
        "| (2004)| (2004)",
        "Mr A| 20 Dec| 31 Dec",
        "| 2 Jan| 4 Jan",
        sitting_date=date(2004, 1, 5),
    )

    assert _get_date_pairs(leave_entries) == [
        (date(2003, 12, 20), date(2003, 12, 31)),
        (date(2004, 1, 2), date(2004, 1, 4)),
    ]
    assert leave_entries[0].year_source == LeaveYearSource.PRINTED_COLUMN_HEADING


def test_a_two_year_heading_offers_only_its_own_years() -> None:
    leave_entries = _build_entries(
        "| (2003)| (2004)",
        "Mr A| 20 Dec| 31 Dec",
        sitting_date=date(2005, 1, 5),
    )

    assert _get_date_pairs(leave_entries) == [(date(2004, 12, 20), date(2004, 12, 31))]


def test_a_hand_kept_heading_year_is_the_only_year_offered() -> None:
    leave_entries = _build_entries(
        "| (2006)| (2006)",
        "Mr A| 20 Oct| 31 Oct",
        sitting_date=date(2005, 11, 21),
    )

    assert _get_date_pairs(leave_entries) == [(date(2005, 10, 20), date(2005, 10, 31))]
    assert leave_entries[0].printed_heading_from == "(2006)"


def _get_reading_markdown(sitting_date: date, *lines: str) -> list[LeaveEntry]:
    return build_leave_entries_from_markdown(
        _get_markdown(_HEADING, *lines),
        sitting_date,
        get_leave_date_misprints(),
        get_leave_heading_years(),
        get_leave_line_readings(),
    )


def test_a_hand_kept_reading_replaces_the_line_and_keeps_the_print() -> None:
    printed_line = "Inche Yaacob Bin Mohamed A1-Haj (Southern Islands), Minister of State for the Prime Minister's Department - from 12th November to 15th December, 1965."

    leave_entries = _get_reading_markdown(date(1965, 12, 8), printed_line)

    assert leave_entries[0].printed_name == "Inche Yaacob Bin Mohamed Al-Haj"
    assert leave_entries[0].printed_line == printed_line
    assert leave_entries[0].entry_format == LeaveEntryFormat.PROSE_RANGE
    assert leave_entries[0].printed_from == "12th November"


def test_a_hand_kept_reading_with_two_lines_gives_a_row_for_each() -> None:
    printed_line = "| 24 Oct| 30 Oct Mr Wee Siew Kim| 03 Nov| 05 Nov"

    leave_entries = _get_reading_markdown(
        date(2010, 10, 18), "Mr A| 20 Oct| 22 Oct", printed_line
    )

    assert [leave_entry.ordinal for leave_entry in leave_entries] == [1, 2, 3]
    assert _get_names(leave_entries)[1:] == [
        (None, "Mr A", LeaveNameSource.CARRIED_FROM_ROW_ABOVE),
        ("Mr Wee Siew Kim", None, LeaveNameSource.PRINTED),
    ]
    assert leave_entries[1].printed_line == printed_line
    assert leave_entries[2].printed_line == printed_line
    assert leave_entries[2].printed_from == "03 Nov"


def test_a_hand_kept_reading_applies_only_on_its_sitting_date() -> None:
    printed_line = "| | 7Oct 15 Oct"

    leave_entries = _get_reading_markdown(date(2000, 10, 10), printed_line)

    assert _get_formats(leave_entries) == [LeaveEntryFormat.UNREAD]


def test_an_unread_line_with_no_date_part_keeps_its_name_and_office() -> None:
    leave_entries = _build_entries(
        "Mr S. Dhanabalan (Kallang), Minister for National Development",
        "Mr Peter Sung (Buona Vista), Minister of State, Ministry of",
        sitting_date=date(1990, 3, 29),
    )

    assert [leave_entry.entry_format for leave_entry in leave_entries] == [
        LeaveEntryFormat.UNREAD,
        LeaveEntryFormat.UNREAD,
    ]
    assert [leave_entry.printed_name for leave_entry in leave_entries] == [
        "Mr S. Dhanabalan",
        "Mr Peter Sung",
    ]
    assert [leave_entry.office_printed for leave_entry in leave_entries] == [
        "Minister for National Development",
        "Minister of State, Ministry of",
    ]
    assert leave_entries[0].name_source == LeaveNameSource.PRINTED


def test_a_line_with_no_name_and_no_date_part_stays_nameless() -> None:
    leave_entries = _build_entries("23rd August, 1966")

    assert leave_entries[0].entry_format == LeaveEntryFormat.UNREAD
    assert leave_entries[0].name_source == LeaveNameSource.NONE
    assert leave_entries[0].printed_name is None


def test_during_starts_the_date_part_of_an_unread_line() -> None:
    leave_entries = _build_entries(
        "Dr Fong Kim Heng (Joo Chiat), Deputy Speaker - during December 1965 and January 1966.",
        sitting_date=date(1965, 12, 8),
    )

    assert leave_entries[0].entry_format == LeaveEntryFormat.UNREAD
    assert leave_entries[0].printed_name == "Dr Fong Kim Heng"
    assert leave_entries[0].office_printed == "Deputy Speaker"


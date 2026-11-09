from datetime import date
from typing import Optional

from crud.speech import SpeechCitationRow
from services.report_citation import get_printed_citations, get_resumption_heading
from utils.printed_citation import PrintedCitation, ResumptionHeading

_REPORT_ID = 7
_ORDINAL = 3
_TAIL_A = "Official Report, 3 March 2020, Volume 94, Issue No 12"
_TAIL_B = "Official Report, 4 March 2020, Volume 94, Issue No 13"


def _build_row(transcript: str) -> SpeechCitationRow:
    return SpeechCitationRow(
        report_id=_REPORT_ID, ordinal=_ORDINAL, transcript=transcript
    )


def _build_citation(
    transcript: str,
    printed_citation: str,
    printed_title: Optional[str],
    printed_date: Optional[date],
) -> PrintedCitation:
    return PrintedCitation(
        report_id=_REPORT_ID,
        ordinal=_ORDINAL,
        printed_citation=printed_citation,
        printed_title=printed_title,
        printed_date=printed_date,
        paragraph=transcript,
    )


def _build_heading(
    transcript: str, printed_citation: str, printed_date: date
) -> ResumptionHeading:
    return ResumptionHeading(
        report_id=_REPORT_ID,
        ordinal=_ORDINAL,
        printed_citation=printed_citation,
        printed_date=printed_date,
        paragraph=transcript,
    )


def test_plain_form_keeps_its_section() -> None:
    transcript = (
        f'[Please refer to "Title A", {_TAIL_A}, Written Answers section]'
    )

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(
            transcript,
            f'"Title A", {_TAIL_A}, Written Answers section',
            "Title A",
            date(2020, 3, 3),
        )
    ]


def test_volume_and_issue_no_forms_both_read() -> None:
    transcript = '[Please refer to "Title A", Official Report, 3rd March, 2020, Vol. 94, No. 12]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(
            transcript,
            '"Title A", Official Report, 3rd March, 2020, Vol. 94, No. 12',
            "Title A",
            date(2020, 3, 3),
        )
    ]


def test_plain_vol_and_issue_forms_read() -> None:
    tail = "Official Report, 3 February 2026, Vol 96, Issue 27"
    transcript = f'[Please refer to "Title A", {tail}]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(transcript, f'"Title A", {tail}', "Title A", date(2026, 2, 3))
    ]


def test_no_section_stops_at_the_tail() -> None:
    transcript = f'[Please refer to "Title A", {_TAIL_A}.]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(
            transcript, f'"Title A", {_TAIL_A}', "Title A", date(2020, 3, 3)
        )
    ]


def test_curly_quotes_stay_in_the_printed_citation() -> None:
    transcript = f"[Please refer to “Title A”, {_TAIL_A}]"

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(
            transcript,
            f"“Title A”, {_TAIL_A}",
            "Title A",
            date(2020, 3, 3),
        )
    ]


def test_parser_marks_are_removed_and_leave_no_stray_spaces_beside_quotes() -> None:
    transcript = (
        f'[Please refer to "__Title_ _", {_TAIL_A}​]'
    )

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(
            transcript, f'"Title", {_TAIL_A}', "Title", date(2020, 3, 3)
        )
    ]


def test_and_chain_gives_two_rows_with_their_own_tails() -> None:
    transcript = f'[Please refer to "A", {_TAIL_A}; and "B", {_TAIL_B}]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(transcript, f'"A", {_TAIL_A}', "A", date(2020, 3, 3)),
        _build_citation(transcript, f'"B", {_TAIL_B}', "B", date(2020, 3, 4)),
    ]


def test_lettered_chain_gives_two_rows_with_their_own_tails() -> None:
    transcript = f'[Please refer to (a) "A", {_TAIL_A}; and (b) "B", {_TAIL_B}]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(transcript, f'"A", {_TAIL_A}', "A", date(2020, 3, 3)),
        _build_citation(transcript, f'"B", {_TAIL_B}', "B", date(2020, 3, 4)),
    ]


def test_two_titles_sharing_one_tail_each_hold_the_whole_group() -> None:
    transcript = f'[Please refer to "A"; and "B", {_TAIL_A}]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(transcript, f'"A"; and "B", {_TAIL_A}', "A", date(2020, 3, 3)),
        _build_citation(transcript, f'"A"; and "B", {_TAIL_A}', "B", date(2020, 3, 3)),
    ]


def test_two_titles_joined_by_and_share_one_tail() -> None:
    transcript = f'[Please refer to "A" and "B", {_TAIL_A}]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(transcript, f'"A" and "B", {_TAIL_A}', "A", date(2020, 3, 3)),
        _build_citation(transcript, f'"A" and "B", {_TAIL_A}', "B", date(2020, 3, 3)),
    ]


def test_a_title_with_inner_quotes_stays_whole() -> None:
    transcript = f'[Please refer to "Re "Gold" Standard", {_TAIL_A}]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(
            transcript,
            f'"Re "Gold" Standard", {_TAIL_A}',
            'Re "Gold" Standard',
            date(2020, 3, 3),
        )
    ]


def test_a_missing_opening_quote_before_the_second_title_gives_each_its_own_tail() -> (
    None
):
    transcript = f'[Please refer to "A", {_TAIL_A}; and B", {_TAIL_B}]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(transcript, f'"A", {_TAIL_A}', "A", date(2020, 3, 3)),
        _build_citation(transcript, f'B", {_TAIL_B}', "B", date(2020, 3, 4)),
    ]


def test_a_note_with_no_official_report_gives_nothing() -> None:
    assert get_printed_citations(_build_row("[Please refer to the Annex.]")) == []


def test_a_month_only_date_gives_one_citation_with_no_title_and_no_date() -> None:
    transcript = '[Please refer to "A", Official Report, March 2020, Volume 94, Issue No 12]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(
            transcript,
            '"A", Official Report, March 2020, Volume 94, Issue No 12',
            None,
            None,
        )
    ]


def test_a_tail_with_no_volume_gives_one_citation_with_no_title_and_no_date() -> None:
    transcript = '[Please refer to "A", Official Report, 3 March 2020]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(
            transcript, '"A", Official Report, 3 March 2020', None, None
        )
    ]


def test_a_readable_tail_followed_by_an_unreadable_one_gives_one_citation_each() -> None:
    transcript = (
        f'[Please refer to "A", {_TAIL_A}; and "B", Official Report, March 2020]'
    )

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(transcript, f'"A", {_TAIL_A}', "A", date(2020, 3, 3)),
        _build_citation(transcript, '"B", Official Report, March 2020', None, None),
    ]


def test_the_older_form_outside_a_note_gives_nothing() -> None:
    transcript = "(Official Report, 3rd August, 1960, Volume 13, No. 2, Column 42)"

    assert get_printed_citations(_build_row(transcript)) == []


def test_a_bad_date_gives_no_printed_date() -> None:
    transcript = '[Please refer to "A", Official Report, 31 February 2020, Volume 94, Issue No 12]'

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(
            transcript,
            '"A", Official Report, 31 February 2020, Volume 94, Issue No 12',
            "A",
            None,
        )
    ]


def test_a_tail_with_no_title_gives_no_printed_title() -> None:
    transcript = f"[Please refer to {_TAIL_A}]"

    assert get_printed_citations(_build_row(transcript)) == [
        _build_citation(transcript, _TAIL_A, None, date(2020, 3, 3))
    ]


def test_a_repeat_call_gives_equal_output() -> None:
    row = _build_row(f'[Please refer to "A", {_TAIL_A}]')

    assert get_printed_citations(row) == get_printed_citations(row)


def test_heading_with_order_read_for() -> None:
    transcript = "Order read for Resumption of Debate on Question [6 October 2026]"

    assert get_resumption_heading(_build_row(transcript)) == _build_heading(
        transcript, transcript, date(2026, 10, 6)
    )


def test_heading_with_parenthesised_date() -> None:
    transcript = "Resumption of Debate on Question (25th February, 2000)"

    assert get_resumption_heading(_build_row(transcript)) == _build_heading(
        transcript, transcript, date(2000, 2, 25)
    )


def test_heading_with_two_dates_reads_the_first() -> None:
    transcript = (
        "Resumption of Debate on Amendments [28th March, 1979] to Question [27th March, 1979]"
    )

    assert get_resumption_heading(_build_row(transcript)) == _build_heading(
        transcript,
        "Resumption of Debate on Amendments [28th March, 1979]",
        date(1979, 3, 28),
    )


def test_heading_on_the_prime_ministers_statement() -> None:
    transcript = "Resumption of Debate on the Prime Minister's Statement [3 March 2020]"

    assert get_resumption_heading(_build_row(transcript)) == _build_heading(
        transcript, transcript, date(2020, 3, 3)
    )


def test_a_resumption_line_with_no_date_gives_none() -> None:
    assert (
        get_resumption_heading(_build_row("Resumption of debate, what day?")) is None
    )


def test_a_date_beyond_the_longest_gap_gives_none() -> None:
    transcript = f"Resumption of Debate on {'x' * 121}[3 March 2020]"

    assert get_resumption_heading(_build_row(transcript)) is None


def test_a_repeat_heading_call_gives_equal_output() -> None:
    row = _build_row("Resumption of Debate on Question [6 October 2026]")

    assert get_resumption_heading(row) == get_resumption_heading(row)

import json
from typing import Optional

from crud.sitting import SittingCopyRow
from enums import PrintedPlaceRule
from services.printed_place import (
    PlaceableReport,
    PrintedPlace,
    get_newer_printed_places,
    get_older_printed_places,
    get_printed_places,
)

_FRAIL_ELDERLY_TITLE = "Support for Frail Elderly and their Care-givers"
_MINISTRY_TITLE = "Plans of New Ministry of Social and Family Development"
_BILL_TITLE = "Employment of Foreign Manpower (Amendment) Bill"


def _section(
    title: str, content: str, sub_title: Optional[str] = None
) -> dict[str, Optional[str]]:
    return {"title": title, "subTitle": sub_title, "content": content}


def _sections_json(*sections: dict[str, Optional[str]]) -> str:
    return json.dumps(list(sections))


_THREE_SECTIONS = _sections_json(
    _section(
        _FRAIL_ELDERLY_TITLE,
        "<p>Frail elderly answer</p>",
        "Update on plan to build Integrated Day Facilities",
    ),
    _section(_MINISTRY_TITLE, "<p>Ministry answer</p>"),
    _section(_BILL_TITLE, "<p>Bill debate</p>"),
)


def _report(
    report_id: str,
    speech_number: int,
    original_title: str,
    content: Optional[str],
    report_type: str = "oral-answer",
    subtitle: Optional[str] = None,
) -> PlaceableReport:
    return PlaceableReport(
        report_id, report_type, speech_number, original_title, subtitle, content
    )


def test_a_report_whose_text_equals_one_section_takes_its_position() -> None:
    bill_report = _report("bill", 19879, _BILL_TITLE, "<p>Bill debate</p>")
    frail_report = _report(
        "frail", 19899, _FRAIL_ELDERLY_TITLE, "<p>Frail elderly answer</p>"
    )

    report_id_to_printed_place = get_newer_printed_places(
        _THREE_SECTIONS, [bill_report, frail_report]
    )

    assert report_id_to_printed_place["bill"] == PrintedPlace(
        3, PrintedPlaceRule.SECTION_TEXT
    )
    assert report_id_to_printed_place["frail"] == PrintedPlace(
        1, PrintedPlaceRule.SECTION_TEXT
    )
    ordered_report_ids = sorted(
        report_id_to_printed_place,
        key=lambda report_id: report_id_to_printed_place[report_id].printed_place or 0,
    )
    assert ordered_report_ids == ["frail", "bill"]


def test_a_report_with_other_text_matches_an_unused_section_by_title() -> None:
    report = _report("ministry", 1, _MINISTRY_TITLE, "<p>Different text</p>")

    assert get_newer_printed_places(_THREE_SECTIONS, [report]) == {
        "ministry": PrintedPlace(2, PrintedPlaceRule.SECTION_TITLE)
    }


def test_a_title_two_unused_sections_share_is_decided_by_subtitle() -> None:
    sections = _sections_json(
        _section("Oral answers", "<p>One</p>", "Roads"),
        _section("Oral answers", "<p>Two</p>", "Schools"),
    )
    report = _report("schools", 1, "Oral answers", "<p>Other</p>", subtitle="Schools")

    assert get_newer_printed_places(sections, [report]) == {
        "schools": PrintedPlace(2, PrintedPlaceRule.SECTION_TITLE_AND_SUBTITLE)
    }


def test_a_title_two_sections_share_with_no_deciding_subtitle_is_not_placed() -> None:
    sections = _sections_json(
        _section("Oral answers", "<p>One</p>", "Roads"),
        _section("Oral answers", "<p>Two</p>", "Roads"),
    )
    report = _report("roads", 1, "Oral answers", "<p>Other</p>", subtitle="Roads")

    assert get_newer_printed_places(sections, [report]) == {
        "roads": PrintedPlace(None, PrintedPlaceRule.NOT_PLACED)
    }


def test_an_assent_report_with_no_text_takes_place_zero() -> None:
    report = _report("assent", 1, "Assent to Bills", None, report_type="atbp")

    assert get_newer_printed_places(_THREE_SECTIONS, [report]) == {
        "assent": PrintedPlace(0, PrintedPlaceRule.ASSENT_FIRST)
    }


def test_an_assent_report_with_empty_or_whitespace_text_takes_place_zero() -> None:
    empty_report = _report("empty", 1, "Assent to Bills", "", report_type="atbp")
    blank_report = _report("blank", 2, "Assent to Bills", " \n\t ", report_type="atbp")

    assert get_newer_printed_places(_THREE_SECTIONS, [empty_report, blank_report]) == {
        "empty": PrintedPlace(0, PrintedPlaceRule.ASSENT_FIRST),
        "blank": PrintedPlace(0, PrintedPlaceRule.ASSENT_FIRST),
    }


def test_a_report_matching_no_section_is_not_placed() -> None:
    report = _report("lost", 1, "Not in the list", "<p>Nowhere</p>")

    assert get_newer_printed_places(_THREE_SECTIONS, [report]) == {
        "lost": PrintedPlace(None, PrintedPlaceRule.NOT_PLACED)
    }


def test_a_section_already_taken_by_text_is_not_taken_again() -> None:
    first_report = _report("first", 1, _BILL_TITLE, "<p>Bill debate</p>")
    second_report = _report("second", 2, _BILL_TITLE, "<p>Bill debate</p>")

    assert get_newer_printed_places(_THREE_SECTIONS, [second_report, first_report]) == {
        "first": PrintedPlace(3, PrintedPlaceRule.SECTION_TEXT),
        "second": PrintedPlace(None, PrintedPlaceRule.NOT_PLACED),
    }


def test_a_title_match_skips_a_section_used_by_text() -> None:
    text_report = _report("text", 1, _MINISTRY_TITLE, "<p>Ministry answer</p>")
    title_report = _report("title", 2, _MINISTRY_TITLE, "<p>Different text</p>")

    assert get_newer_printed_places(_THREE_SECTIONS, [text_report, title_report]) == {
        "text": PrintedPlace(2, PrintedPlaceRule.SECTION_TEXT),
        "title": PrintedPlace(None, PrintedPlaceRule.NOT_PLACED),
    }


_PARAGRAPH_ONE = "the minister rose to explain why the new housing grant scheme would help young families"
_PARAGRAPH_TWO = "members asked whether the proposed levy on foreign workers could be lowered during the coming budget season"
_PARAGRAPH_THREE = "the speaker then called the next item concerning rail reliability and the operators performance targets for the year"
_PARAGRAPH_FOUR = "a final motion on the adjournment was moved and carried without any division after short remarks from several members"
_SHORT_PARAGRAPH = "motion carried unanimously"
_OLDER_DAY = (
    "<table><tr><td>Header row here</td></tr></table>"
    f"<p>{_PARAGRAPH_ONE}</p><p>{_PARAGRAPH_TWO}</p><p>{_PARAGRAPH_THREE}</p>"
    f"<p>{_PARAGRAPH_FOUR}</p><p>{_SHORT_PARAGRAPH}</p>"
)


def _paragraph_word_count(*paragraphs: str) -> int:
    return sum(len(paragraph.split()) for paragraph in paragraphs)


def test_an_older_report_takes_the_word_offset_of_its_first_unique_run() -> None:
    second_report = _report("second", 1, "Title", f"<p>{_PARAGRAPH_TWO}</p>")
    fourth_report = _report("fourth", 2, "Title", f"<p>{_PARAGRAPH_FOUR}</p>")

    assert get_older_printed_places(_OLDER_DAY, [second_report, fourth_report]) == {
        "second": PrintedPlace(
            _paragraph_word_count(_PARAGRAPH_ONE), PrintedPlaceRule.FULL_TEXT_RUN
        ),
        "fourth": PrintedPlace(
            _paragraph_word_count(_PARAGRAPH_ONE, _PARAGRAPH_TWO, _PARAGRAPH_THREE),
            PrintedPlaceRule.FULL_TEXT_RUN,
        ),
    }


def test_a_report_whose_runs_all_repeat_is_not_placed() -> None:
    report = _report("repeated", 1, "Title", f"<p>{_PARAGRAPH_TWO}</p>")

    assert get_older_printed_places(
        _OLDER_DAY + f"<p>{_PARAGRAPH_TWO}</p>", [report]
    ) == {"repeated": PrintedPlace(None, PrintedPlaceRule.NOT_PLACED)}


def test_a_report_printed_in_two_pieces_takes_its_first_piece() -> None:
    split_report = _report(
        "split", 1, "Title", f"<p>{_PARAGRAPH_TWO}</p><p>{_PARAGRAPH_FOUR}</p>"
    )
    between_report = _report("between", 2, "Title", f"<p>{_PARAGRAPH_THREE}</p>")

    assert get_older_printed_places(_OLDER_DAY, [split_report, between_report]) == {
        "split": PrintedPlace(
            _paragraph_word_count(_PARAGRAPH_ONE), PrintedPlaceRule.FULL_TEXT_RUN
        ),
        "between": PrintedPlace(
            _paragraph_word_count(_PARAGRAPH_ONE, _PARAGRAPH_TWO),
            PrintedPlaceRule.FULL_TEXT_RUN,
        ),
    }


def test_a_run_another_report_also_holds_does_not_place_a_report() -> None:
    outer_report = _report(
        "outer", 1, "Title", f"<p>{_PARAGRAPH_TWO} {_PARAGRAPH_THREE}</p>"
    )
    inner_report = _report("inner", 2, "Title", f"<p>{_PARAGRAPH_TWO}</p>")

    # The outer report's first run that the inner report does not hold starts
    # 11 words before paragraph three, so it ends on paragraph three's first word.
    assert get_older_printed_places(_OLDER_DAY, [outer_report, inner_report]) == {
        "outer": PrintedPlace(
            _paragraph_word_count(_PARAGRAPH_ONE, _PARAGRAPH_TWO) - 11,
            PrintedPlaceRule.FULL_TEXT_RUN,
        ),
        "inner": PrintedPlace(None, PrintedPlaceRule.NOT_PLACED),
    }


def test_a_report_with_no_text_is_not_placed() -> None:
    report = _report("empty", 1, "Title", None)

    assert get_older_printed_places(_OLDER_DAY, [report]) == {
        "empty": PrintedPlace(None, PrintedPlaceRule.NOT_PLACED)
    }


def test_an_older_assent_with_no_text_takes_place_zero() -> None:
    report = _report("assent", 1, "Assent to Bills", None, report_type="atbp")

    assert get_older_printed_places(_OLDER_DAY, [report]) == {
        "assent": PrintedPlace(0, PrintedPlaceRule.ASSENT_FIRST)
    }


def test_a_report_shorter_than_a_run_is_placed_by_its_whole_text() -> None:
    report = _report("short", 1, "Title", f"<p>{_SHORT_PARAGRAPH}</p>")

    assert get_older_printed_places(_OLDER_DAY, [report]) == {
        "short": PrintedPlace(
            _paragraph_word_count(
                _PARAGRAPH_ONE, _PARAGRAPH_TWO, _PARAGRAPH_THREE, _PARAGRAPH_FOUR
            ),
            PrintedPlaceRule.FULL_TEXT_RUN,
        )
    }


def test_a_sitting_with_no_copy_places_nothing() -> None:
    reports = [
        _report("assent", 1, "Assent to Bills", None, report_type="atbp"),
        _report("answer", 2, "Title", f"<p>{_PARAGRAPH_TWO}</p>"),
    ]
    not_placed = PrintedPlace(None, PrintedPlaceRule.NOT_PLACED)

    assert get_printed_places(None, reports) == {
        "assent": not_placed,
        "answer": not_placed,
    }
    assert get_printed_places(SittingCopyRow(None, None), reports) == {
        "assent": not_placed,
        "answer": not_placed,
    }


def test_a_sitting_with_sections_is_placed_from_them() -> None:
    reports = [_report("bill", 1, _BILL_TITLE, "<p>Bill debate</p>")]

    assert get_printed_places(
        SittingCopyRow(_THREE_SECTIONS, None), reports
    ) == get_newer_printed_places(_THREE_SECTIONS, reports)


def test_a_sitting_with_a_full_html_copy_is_placed_from_it() -> None:
    reports = [_report("second", 1, "Title", f"<p>{_PARAGRAPH_TWO}</p>")]

    assert get_printed_places(
        SittingCopyRow(None, _OLDER_DAY), reports
    ) == get_older_printed_places(_OLDER_DAY, reports)

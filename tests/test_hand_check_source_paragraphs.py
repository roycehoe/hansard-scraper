from typing import Optional

import pytest

import scripts.build_hand_check_packets as build_hand_check_packets_script
from enums import HandCheckMatchStatus
from schemas.hand_check_packet import HandCheckGapCheck
from tests.hand_check_source_html import (
    SPRS2_APPENDIX_HTML,
    SPRS2_COMMITTEE_HTML,
    SPRS3_ORAL_ANSWER_HTML,
)
from utils.hand_check_text import normalize_hand_check_text

_QUESTION_ROW = (
    "7 asked the Prime Minister whether the Total Debt Servicing Ratio (TDSR) restrictions"
    " can be relaxed to allow borrowers to obtain credit facilities if they are able to offer"
    " unencumbered private property as collateral to financial institutions, even if they have"
    " breached the TDSR limits, so as to enable them to manage their overall loan commitments."
)
_ANSWER_ROW = (
    "Under the Total Debt Servicing Ratio (TDSR) framework, a borrower's monthly loan"
    " instalments should not exceed 60% of his monthly income."
)
_JOINED_ROW = (
    "Therefore, it is more prudent to have our current rules as the default position."
    " However, financial institutions may approve property loan applications where the"
    " borrowers' TDSR exceed 60% in exceptional cases. Such exceptions must be approved by"
    " the financial institutions' credit committees, in line with the policies set by their"
    " board of directors."
)
_NEXT_ROW = "Madam, a supplementary question for the Minister."
_APPENDIX_ROW = (
    "In accordance with the provisions of paragraph (5) of Standing Order 88 and paragraph"
    " (7) of Standing Order 87, I have for the Development Estimates of Singapore, fixed the"
    " times on the allotted days, if not previously disposed of, be concluded. These times"
    " have been notified to hon. Members and will appear in the Official Report*.(*"
    " Appendix, cols. 1053-4.)"
)
_APPENDIX_CAPTION = (
    "DEVELOPMENT ESTIMATES OF SINGAPORE FOR THE FINANCIAL YEAR 1ST APRIL, 1972, TO 31ST"
    " MARCH, 1973 IN COMMITTEE OF SUPPLY(Cols. 1053-1054)"
)
_SKIPPING_HTML = (
    "<p><b>Mr A:</b> First words.</p><p>Second words.</p><p>Third words.</p>"
    "<p>2.41 pm</p><h4>[Mr Speaker in the Chair]</h4>"
    "<p><b>Mr B:</b> Next words of the row.</p>"
)
# NOTE: trimmed from report 014_19710325_S0003_T0026, a written answer that prints its table in a preformatted block
_PREFORMATTED_TABLE_HTML = (
    "<br><br><!-- Mr E. W. Barker -->&nbsp;&nbsp;&nbsp;&nbsp;<b>Mr E. W. Barker:</b> Sir,"
    " the number of shop-houses\r\n\r\naffected    by   urban   renewal   and   Government"
    "\r\n\r\ndevelopment projects and cleared in 1969  and  1970\r\n\r\nis as follows:"
    "\r\n\r\n\r\n\r\n<pre>\r\n\r\n                           1969    1970\r\n\r\n"
    "        Urban renewal       212      97\r\n\r\n"
    "        Other projects      172     174\r\n\r\n</pre>\r\n\r\n\r\n\r\n"
    "The number of shopkeepers so affected, who have\r\n\r\nvacated Housing and"
    " Development Board premises"
)
_ORAL_ANSWER_PARAGRAPH_COUNT = 5
_JOINED_ROW_CONTEXT_PARAGRAPH_COUNT = 3
_ORAL_ANSWER_LABEL = (
    "The Minister for Education (Higher Education and Skills) and Second Minister for"
    " Defence (Mr Ong Ye Kung) (for the Prime Minister)"
)


def _get_source_match(
    report_html: str,
    speaker: Optional[str],
    transcript: str,
    next_transcript: Optional[str] = None,
) -> build_hand_check_packets_script.SourceMatch:
    return build_hand_check_packets_script.get_source_match(
        build_hand_check_packets_script.split_source_paragraphs(report_html),
        speaker,
        transcript,
        next_transcript,
    )


def _build_source_match(
    status: HandCheckMatchStatus, first_index: int, last_index: int
) -> build_hand_check_packets_script.SourceMatch:
    return build_hand_check_packets_script.SourceMatch(
        status, build_hand_check_packets_script.SourceRun(first_index, last_index)
    )


def test_the_older_system_header_rows_and_labelled_turns_split_into_paragraphs() -> (
    None
):
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS2_COMMITTEE_HTML
    )

    assert [paragraph.label for paragraph in paragraphs] == [
        None,
        None,
        "The Chairman",
        None,
        "Dr Tony Tan Keng Yam",
    ]
    assert normalize_hand_check_text(paragraphs[1].full_html).startswith(
        "MPs Speaking:"
    )


def test_a_column_marker_a_page_marker_and_a_comment_make_no_paragraph() -> None:
    committee_texts = [
        normalize_hand_check_text(paragraph.full_html)
        for paragraph in build_hand_check_packets_script.split_source_paragraphs(
            SPRS2_COMMITTEE_HTML
        )
    ]
    oral_answer_texts = [
        normalize_hand_check_text(paragraph.full_html)
        for paragraph in build_hand_check_packets_script.split_source_paragraphs(
            SPRS3_ORAL_ANSWER_HTML
        )
    ]

    assert not any(text.startswith("Column") for text in committee_texts)
    assert not any(
        "Chew Heng Ching (Mr Deputy Speaker) Order" in text for text in committee_texts
    )
    assert len(oral_answer_texts) == _ORAL_ANSWER_PARAGRAPH_COUNT
    assert not any(text.startswith("Page") for text in oral_answer_texts)


def test_a_newer_system_label_with_a_question_number_and_no_colon_is_a_label() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS3_ORAL_ANSWER_HTML
    )

    assert [paragraph.label for paragraph in paragraphs] == [
        "Ms Sylvia Lim",
        _ORAL_ANSWER_LABEL,
        None,
        None,
        "Ms Sylvia Lim (Aljunied)",
    ]
    assert normalize_hand_check_text(paragraphs[0].body_html).startswith(
        "7 asked the Prime Minister"
    )


def test_a_bold_centred_heading_without_a_colon_is_not_a_label() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS2_APPENDIX_HTML
    )

    assert [
        paragraph.label for paragraph in paragraphs if paragraph.label is not None
    ] == ["Mr Speaker"]
    assert (
        normalize_hand_check_text(paragraphs[6].full_html)
        == "(Announcement by Mr Speaker)"
    )


def test_an_unbolded_chair_label_is_a_label() -> None:
    [paragraph] = build_hand_check_packets_script.split_source_paragraphs(
        "<p>Mr Speaker: Mr Louis Chua.</p>"
    )

    assert paragraph.label == "Mr Speaker"
    assert normalize_hand_check_text(paragraph.body_html) == "Mr Louis Chua."


def test_only_a_heading_tag_makes_a_heading() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS2_APPENDIX_HTML
    )

    assert [
        index for index, paragraph in enumerate(paragraphs) if paragraph.is_heading
    ] == [3]
    assert normalize_hand_check_text(paragraphs[3].full_html) == (
        "[Mr Speaker in the Chair]"
    )


def test_a_row_equal_to_one_paragraph_matches_exactly_without_its_label() -> None:
    assert _get_source_match(
        SPRS2_COMMITTEE_HTML, "The Chairman", "Order. It is 6.30 pm."
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 2, 2)


def test_a_question_number_before_the_label_stays_in_the_compared_text() -> None:
    assert _get_source_match(
        SPRS3_ORAL_ANSWER_HTML, "Ms Sylvia Lim", _QUESTION_ROW
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 0, 0)
    assert _get_source_match(
        SPRS3_ORAL_ANSWER_HTML, "Ms Sylvia Lim", _QUESTION_ROW.removeprefix("7 ")
    ) == _build_source_match(HandCheckMatchStatus.INEXACT, 0, 0)


def test_a_row_joined_across_a_page_marker_matches_two_paragraphs() -> None:
    assert _get_source_match(
        SPRS3_ORAL_ANSWER_HTML, _ORAL_ANSWER_LABEL, _JOINED_ROW
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 2, 3)


def test_a_row_joined_across_a_column_marker_matches_two_paragraphs() -> None:
    assert _get_source_match(
        SPRS2_APPENDIX_HTML, "Mr Speaker", _APPENDIX_ROW
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 7, 8)


def test_each_line_of_a_preformatted_table_is_a_paragraph() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        _PREFORMATTED_TABLE_HTML
    )

    assert [
        normalize_hand_check_text(paragraph.body_html) for paragraph in paragraphs
    ] == [
        "Sir, the number of shop-houses affected by urban renewal and Government"
        " development projects and cleared in 1969 and 1970 is as follows:",
        "1969 1970",
        "Urban renewal 212 97",
        "Other projects 172 174",
        "The number of shopkeepers so affected, who have vacated Housing and"
        " Development Board premises",
    ]


def test_a_row_of_preformatted_lines_matches_those_lines() -> None:
    assert _get_source_match(
        _PREFORMATTED_TABLE_HTML,
        "Mr E. W. Barker",
        "Urban renewal       212      97",
        "Other projects      172     174",
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 2, 2)
    assert _get_source_match(
        _PREFORMATTED_TABLE_HTML,
        "Mr E. W. Barker",
        "Urban renewal 212 97 Other projects 172 174",
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 2, 3)


def test_an_appendix_caption_row_matches_the_paragraph_that_has_no_label() -> None:
    assert _get_source_match(
        SPRS2_APPENDIX_HTML, None, _APPENDIX_CAPTION
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 9, 9)


def test_markup_and_spacing_do_not_stop_an_exact_match() -> None:
    transcript = (
        "Mr Deputy Speaker,  Sir, I would like to report that the **Committee** of"
        "  Supply has made progress"
    )

    assert _get_source_match(
        SPRS2_COMMITTEE_HTML, "Dr Tony Tan Keng Yam", transcript
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 4, 4)


def test_a_row_with_a_dropped_word_is_inexact_and_spans_every_paragraph_it_touches() -> (
    None
):
    transcript = _JOINED_ROW.replace("as the default position", "as default position")

    assert _get_source_match(
        SPRS3_ORAL_ANSWER_HTML, _ORAL_ANSWER_LABEL, transcript
    ) == _build_source_match(HandCheckMatchStatus.INEXACT, 2, 3)


def test_a_row_whose_ending_was_cut_is_inexact_and_the_run_still_reaches_the_last_words() -> (
    None
):
    transcript = (
        "Therefore, it is more prudent to have our current rules as the default position."
        " However, financial institutions may approve property loan applications where"
        " the borrowers' TDSR exceed 60% in exceptional cases."
    )

    assert _get_source_match(
        SPRS3_ORAL_ANSWER_HTML, _ORAL_ANSWER_LABEL, transcript
    ) == _build_source_match(HandCheckMatchStatus.INEXACT, 2, 3)


def test_a_row_found_nowhere_is_not_found_with_no_run() -> None:
    assert _get_source_match(
        SPRS3_ORAL_ANSWER_HTML, None, "Words printed nowhere in this report at all."
    ) == build_hand_check_packets_script.SourceMatch(
        HandCheckMatchStatus.NOT_FOUND, None
    )


def test_a_repeated_reply_takes_the_run_whose_next_paragraph_starts_the_next_row() -> (
    None
):
    report_html = (
        "<p><b>Mr A:</b> Yes.</p><p><b>Mr B:</b> Yes.</p><p><b>Mr C:</b> Go ahead.</p>"
    )

    assert _get_source_match(
        report_html, "Mr A", "Yes.", "Go ahead."
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 1, 1)


def test_a_repeated_reply_with_no_next_row_takes_the_run_under_its_own_label() -> None:
    report_html = "<p><b>Mr A:</b> Order.</p><p><b>Mr X:</b> Thank you.</p><p><b>Mr B:</b> Order.</p>"

    assert _get_source_match(report_html, "Mr A", "Order.") == _build_source_match(
        HandCheckMatchStatus.EXACT, 0, 0
    )
    assert _get_source_match(report_html, "Mr B", "Order.") == _build_source_match(
        HandCheckMatchStatus.EXACT, 2, 2
    )


def test_a_repeated_reply_with_no_label_tie_takes_the_first_run_in_the_report() -> None:
    assert _get_source_match(
        "<p>Order.</p><p>Thank you.</p><p>Order.</p>", "Mr Z", "Order."
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 0, 0)


# NOTE: trimmed from report 12665 (bill-366, 8 May 2019), which prints "Yes, please." under the Speaker with a slide note, and later under the Deputy Speaker
_REPEATED_REPLY_HTML = (
    "<p><strong>Mr Speaker</strong>: Yes, please. [<em>A slide was shown to hon Members.</em>]</p>"
    "<p><strong>Assoc Prof Walter Theseira</strong>: Thank you, Sir.</p>"
    "<p><strong>Mr Deputy Speaker</strong>: Yes, please.</p>"
    "<p><strong>Mr Saktiandi Supaat</strong>: (<em>In Malay</em>): Thank you.</p>"
)


def test_a_reply_whose_own_paragraph_holds_a_cut_line_takes_its_own_paragraph_over_an_exact_copy_under_another_label() -> (
    None
):
    assert _get_source_match(
        _REPEATED_REPLY_HTML,
        "Mr Speaker",
        "Yes, please.",
        "[_A slide was shown to hon Members._]",
    ) == _build_source_match(HandCheckMatchStatus.INEXACT, 0, 0)


def test_the_exact_copy_of_a_repeated_reply_still_matches_under_its_own_label() -> None:
    assert _get_source_match(
        _REPEATED_REPLY_HTML,
        "Mr Deputy Speaker",
        "Yes, please.",
        "(In Malay): Thank you.",
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 2, 2)


# NOTE: trimmed from report 22117 (5 February 2009), where two members' vernacular pointers open with the same words and only the first prints "Appendix A *." with a space
_TWO_POINTERS_HTML = (
    "<p><b>Mr Hawazi Daipi:</b> Mr Speaker, Sir, I speak in support of the Budget.</p>"
    "<p>(<i>In Malay</i>): [<i>For vernacular speech, please refer to </i><i>Appendix A</i> <i>*.</i>] Sir, I feel that all Singaporeans must draw lessons.</p>"
    "<p><b>Dr Lam Pin Min (Ang Mo Kio):</b> Mr Speaker, in Mandarin, please.</p>"
    "<p>(<i>In Mandarin</i>): [<i>For vernacular speech, please refer to </i><i>Appendix A</i><i>*.</i> ] Singapore's social policies espouse strong Asian values and family structures.</p>"
)


def test_a_run_that_crosses_into_another_turn_gives_way_to_a_run_inside_the_rows_turn() -> (
    None
):
    assert _get_source_match(
        _TWO_POINTERS_HTML,
        "Dr Lam Pin Min (Ang Mo Kio)",
        "[_For vernacular speech, please refer to_ _Appendix A_ _*._ ] Singapore's social"
        " policies espouse strong Asian values and family structures.",
    ) == _build_source_match(HandCheckMatchStatus.INEXACT, 3, 3)


def test_the_matched_source_drops_the_first_label_and_keeps_later_paragraphs_whole() -> (
    None
):
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS3_ORAL_ANSWER_HTML
    )
    joined_html = build_hand_check_packets_script.get_matched_source_html(
        paragraphs,
        build_hand_check_packets_script.get_source_match(
            paragraphs, _ORAL_ANSWER_LABEL, _JOINED_ROW, _NEXT_ROW
        ),
    )
    answer_html = build_hand_check_packets_script.get_matched_source_html(
        paragraphs,
        build_hand_check_packets_script.get_source_match(
            paragraphs, _ORAL_ANSWER_LABEL, _ANSWER_ROW, _JOINED_ROW
        ),
    )

    assert normalize_hand_check_text(joined_html) == _JOINED_ROW
    assert normalize_hand_check_text(answer_html) == _ANSWER_ROW
    assert "Minister for Education" not in answer_html


def test_there_is_no_matched_source_for_a_row_found_nowhere() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS3_ORAL_ANSWER_HTML
    )

    assert (
        build_hand_check_packets_script.get_matched_source_html(
            paragraphs,
            build_hand_check_packets_script.SourceMatch(
                HandCheckMatchStatus.NOT_FOUND, None
            ),
        )
        == ""
    )


def test_the_context_starts_at_the_nearest_label_and_ends_at_the_run() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS3_ORAL_ANSWER_HTML
    )

    context_paragraphs = build_hand_check_packets_script.get_context_paragraphs(
        paragraphs,
        build_hand_check_packets_script.get_source_match(
            paragraphs, _ORAL_ANSWER_LABEL, _JOINED_ROW, _NEXT_ROW
        ),
    )

    assert len(context_paragraphs) == _JOINED_ROW_CONTEXT_PARAGRAPH_COUNT
    assert context_paragraphs[0].startswith("<B>")
    assert context_paragraphs[0].endswith("of his monthly income.")
    assert context_paragraphs[2].startswith("60% in exceptional cases.")


def test_the_context_starts_at_the_top_of_the_report_when_no_label_sits_above() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        "<p>First line.</p><p>Second line.</p><p>Third line.</p>"
    )

    assert build_hand_check_packets_script.get_context_paragraphs(
        paragraphs,
        build_hand_check_packets_script.get_source_match(
            paragraphs, None, "Third line.", None
        ),
    ) == ["First line.", "Second line.", "Third line."]


def test_the_context_of_a_report_with_a_header_table_includes_its_rows() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS2_APPENDIX_HTML
    )

    context_paragraphs = build_hand_check_packets_script.get_context_paragraphs(
        paragraphs,
        build_hand_check_packets_script.get_source_match(
            paragraphs, None, "Development Estimates", None
        ),
    )

    assert context_paragraphs[:3] == [
        "Sitting Date: 22-03-1972",
        "Title: COMMITTEE OF SUPPLY (Development Estimates)",
        "MPs Speaking: Dr Yeoh Ghim Seng (Mr Speaker);",
    ]
    assert context_paragraphs[-1] == "Development Estimates"


def test_the_context_is_empty_when_there_is_no_run() -> None:
    assert (
        build_hand_check_packets_script.get_context_paragraphs(
            build_hand_check_packets_script.split_source_paragraphs(
                SPRS3_ORAL_ANSWER_HTML
            ),
            build_hand_check_packets_script.SourceMatch(
                HandCheckMatchStatus.NOT_FOUND, None
            ),
        )
        == []
    )


def test_the_after_paragraph_is_the_one_paragraph_following_the_run() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS3_ORAL_ANSWER_HTML
    )

    assert build_hand_check_packets_script.get_after_paragraph(
        paragraphs,
        build_hand_check_packets_script.get_source_match(
            paragraphs, _ORAL_ANSWER_LABEL, _JOINED_ROW, _NEXT_ROW
        ),
    ) == (
        "<B> Ms Sylvia Lim (Aljunied)</B>: Madam, a supplementary question for the"
        " Minister."
    )


def test_there_is_no_after_paragraph_at_the_end_of_the_report_or_without_a_run() -> (
    None
):
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS2_APPENDIX_HTML
    )

    assert (
        build_hand_check_packets_script.get_after_paragraph(
            paragraphs,
            build_hand_check_packets_script.get_source_match(
                paragraphs, None, _APPENDIX_CAPTION, None
            ),
        )
        is None
    )
    assert (
        build_hand_check_packets_script.get_after_paragraph(
            paragraphs,
            build_hand_check_packets_script.SourceMatch(
                HandCheckMatchStatus.NOT_FOUND, None
            ),
        )
        is None
    )


def test_the_display_text_marks_bold_italic_superscript_and_subscript() -> None:
    assert (
        build_hand_check_packets_script.render_source_html(
            "<p>248<sup>1</sup>&nbsp;psychiatrists <strong>and</strong> <em>x</em>"
            " H<sub>2</sub>O</p>"
        )
        == "248<SUP>1</SUP> psychiatrists <B>and</B> <I>x</I> H<SUB>2</SUB>O"
    )


def test_the_display_text_drops_other_tags_decodes_references_and_folds_spaces() -> (
    None
):
    assert (
        build_hand_check_packets_script.render_source_html(
            '<a href="x">link</a>  R&amp;D\r\n\r\n  here '
        )
        == "link R&D here"
    )


@pytest.mark.parametrize("text", ["a rate of <5% and >3%", "x < y > z"])
def test_the_display_text_keeps_a_less_than_sign_that_opens_no_tag(text: str) -> None:
    assert build_hand_check_packets_script.render_source_html(text) == text


def test_a_table_cell_end_becomes_a_space_in_the_display_text() -> None:
    assert (
        build_hand_check_packets_script.render_source_html(
            "<td>Title:</td><td>BUDGET</td>"
        )
        == "Title: BUDGET"
    )


def test_the_gap_check_is_the_next_row_when_the_next_paragraph_starts_it() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS3_ORAL_ANSWER_HTML
    )

    assert build_hand_check_packets_script.get_gap_check(
        paragraphs, 0, _ANSWER_ROW
    ) == HandCheckGapCheck(
        is_next_row=True, skipped_paragraphs=[], next_source_text=_ANSWER_ROW
    )


def test_the_gap_check_skips_time_stamps_and_chair_notes_and_lists_them() -> None:
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(_SKIPPING_HTML)

    assert build_hand_check_packets_script.get_gap_check(
        paragraphs, 2, "Next words of the row."
    ) == HandCheckGapCheck(
        is_next_row=True,
        skipped_paragraphs=["2.41 pm", "[Mr Speaker in the Chair]"],
        next_source_text="Next words of the row.",
    )


def test_the_gap_check_is_not_the_next_row_when_the_next_paragraph_starts_other_words() -> (
    None
):
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS3_ORAL_ANSWER_HTML
    )

    assert build_hand_check_packets_script.get_gap_check(
        paragraphs, 0, "Some other words that the next row holds."
    ) == HandCheckGapCheck(
        is_next_row=False, skipped_paragraphs=[], next_source_text=_ANSWER_ROW
    )


def test_the_gap_check_at_the_end_of_the_report_holds_only_when_no_row_follows() -> (
    None
):
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS2_APPENDIX_HTML
    )
    last_index = len(paragraphs) - 1

    assert build_hand_check_packets_script.get_gap_check(
        paragraphs, last_index, None
    ) == HandCheckGapCheck(
        is_next_row=True, skipped_paragraphs=[], next_source_text=None
    )
    assert build_hand_check_packets_script.get_gap_check(
        paragraphs, last_index, "A row that follows."
    ) == HandCheckGapCheck(
        is_next_row=False, skipped_paragraphs=[], next_source_text=None
    )


def test_the_gap_check_is_not_the_next_row_when_a_paragraph_remains_and_no_row_follows() -> (
    None
):
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS2_APPENDIX_HTML
    )

    assert build_hand_check_packets_script.get_gap_check(
        paragraphs, 8, None
    ) == HandCheckGapCheck(
        is_next_row=False, skipped_paragraphs=[], next_source_text=_APPENDIX_CAPTION
    )


# NOTE: report 34920 (22 March 1976) prints this motion twice, the first time with a language note between the bold name and the colon
_LANGUAGE_NOTE_LABEL_HTML = (
    "<br><br><!-- Mr Chin Harn Tong -->&nbsp;&nbsp;&nbsp;&nbsp;<b>Mr Chin Harn Tong (Aljunied)</b>(<i>In Mandarin</i>): Sir, I beg\r\n\r\nto move,"
    "\r\n\r\n<br><br>&nbsp;&nbsp;&nbsp;&nbsp;That the sum to be allocated for Head U be reduced by $10 in respect of subhead BAA 1105*."
    "\r\n\r\n<br><br><!-- Mr Hwang Soo Jin -->&nbsp;&nbsp;&nbsp;&nbsp;<b>Mr Hwang Soo Jin:</b> Sir, I beg to move,"
    "\r\n\r\n<br><br>&nbsp;&nbsp;&nbsp;&nbsp;That the sum to be allocated for Head U be reduced by $10 in respect of subhead DAA 1109*."
)


def test_a_language_note_before_the_colon_belongs_to_the_label() -> None:
    [first_paragraph, *_] = build_hand_check_packets_script.split_source_paragraphs(
        _LANGUAGE_NOTE_LABEL_HTML
    )

    assert first_paragraph.label == "Mr Chin Harn Tong (Aljunied)"
    assert normalize_hand_check_text(first_paragraph.body_html) == (
        "Sir, I beg to move,"
    )


def test_a_repeated_motion_takes_the_paragraph_under_the_label_with_a_language_note() -> (
    None
):
    assert _get_source_match(
        _LANGUAGE_NOTE_LABEL_HTML,
        "Mr Chin Harn Tong (Aljunied)",
        "Sir, I beg to move,",
        "That the sum to be allocated for Head U be reduced by $10 in respect of subhead BAA 1105*.",
    ) == _build_source_match(HandCheckMatchStatus.EXACT, 0, 0)


def test_a_language_note_after_the_colon_stays_in_the_compared_text() -> None:
    [paragraph] = build_hand_check_packets_script.split_source_paragraphs(
        "<p><b>Mr Chin Harn Tong (Aljunied):</b> (<i>In Mandarin</i>): Sir, I beg to move,</p>"
    )

    assert paragraph.label == "Mr Chin Harn Tong (Aljunied)"
    assert normalize_hand_check_text(paragraph.body_html) == (
        "(In Mandarin): Sir, I beg to move,"
    )

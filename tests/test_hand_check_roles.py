from datetime import date
from typing import Optional

import pytest

import scripts.build_hand_check_packets as build_hand_check_packets_script
from enums import HandCheckFormOfAddress, ReportVersion
from schemas.hand_check_office_holder import HandCheckOfficeHolder
from schemas.hand_check_packet import HandCheckRoleSection
from tests.hand_check_source_html import SPRS2_APPENDIX_HTML, SPRS2_COMMITTEE_HTML

_TITLE = "A Sample Title"
_TITLE_SUFFIX = " (report: A Sample Title)"
_DAY = date(2010, 5, 5)
_TAG_LINE = "MPs Speaking: Dr Tony Tan Keng Yam (Minister for Defence); Mr Chew Heng Ching (Mr Deputy Speaker);"
_THEREUPON_LINE = "Thereupon, Mr Deputy Speaker left the Chair of the Committee and took the Chair of the House."
_WRAPPED_THEREUPON_LINE = (
    "[(proc text) Thereupon Mdm Speaker left the Chair of the Committee and took the"
    " Chair of the House. (proc text)]"
)
_CHAIR_CHANGE_HTML = (
    "<p><b>Mr Speaker:</b> Order.</p><p>Sitting suspended at 4.00 pm.</p><p>Sitting resumed at 4.30 pm.</p>"
    "<h4>[Mr Deputy Speaker in the Chair]</h4><p><b>The Chairman:</b> Yes.</p>"
    "<p>Thereupon, Mdm Speaker resumed the Chair.</p><p><b>Mdm Speaker:</b> Thank you.</p>"
)
_DEPUTY_SPEAKER_NOTE_HTML = (
    "<h4>[Mr Deputy Speaker (Mr Charles Chong) in the Chair]</h4>"
    "<p><b>Mr Deputy Speaker:</b> Order.</p>"
)
_DEPUTY_SPEAKER_NOTE = "[Mr Deputy Speaker (Mr Charles Chong) in the Chair]"


def _build_holder(
    office: str,
    holder: str,
    form_of_address: HandCheckFormOfAddress,
    first_day: date = date(2000, 1, 1),
    last_day: Optional[date] = None,
) -> HandCheckOfficeHolder:
    return HandCheckOfficeHolder(
        office=office,
        holder=holder,
        form_of_address=form_of_address,
        first_day=first_day,
        last_day=last_day,
        source_url="https://example.org/source",
    )


def _build_two_male_deputy_speakers() -> list[HandCheckOfficeHolder]:
    return [
        _build_holder("Deputy Speaker", "Charles Chong", HandCheckFormOfAddress.MR),
        _build_holder("Deputy Speaker", "Lim Biow Chuan", HandCheckFormOfAddress.MR),
    ]


def _get_chair_lines(
    report_html: str, office_holders: Optional[list[HandCheckOfficeHolder]] = None
) -> list[build_hand_check_packets_script.ChairLine]:
    return build_hand_check_packets_script.get_chair_lines(
        build_hand_check_packets_script.split_source_paragraphs(report_html),
        _TITLE,
        _DAY,
        [] if office_holders is None else office_holders,
    )


@pytest.mark.parametrize(
    "label", ["The Chairman", "Mr Chairman", "Mdm Chairman", "the chairman"]
)
def test_a_chairman_label_is_a_chair_label_that_names_no_office(label: str) -> None:
    assert build_hand_check_packets_script.is_chair_label(label, _DAY, []) is True
    assert build_hand_check_packets_script.get_label_office(label) is None


@pytest.mark.parametrize(
    ("label", "office"),
    [
        ("Mr Speaker", "Speaker"),
        ("Mdm Speaker", "Speaker"),
        ("The Speaker", "Speaker"),
        ("Mr Deputy Speaker", "Deputy Speaker"),
        ("Mdm Deputy Speaker", "Deputy Speaker"),
        ("The Deputy Speaker", "Deputy Speaker"),
        ("The Prime Minister", "Prime Minister"),
        ("The Minister for Finance", "Minister for Finance"),
        ("His Excellency the Governor", "Governor"),
    ],
)
def test_a_label_that_names_a_title_names_that_office(label: str, office: str) -> None:
    assert build_hand_check_packets_script.get_label_office(label) == office


@pytest.mark.parametrize(
    "label",
    [
        "Mr Lee Hsien Loong",
        "Ms Sylvia Lim (Aljunied)",
        "The Minister for Health (Mr Khaw Boon Wan)",
        "Dr Yeoh Ghim Seng (Mr Speaker)",
        "Mr Deputy Speaker (Mr Charles Chong)",
    ],
)
def test_a_label_that_names_a_person_names_no_office_and_is_not_a_chair_label(
    label: str,
) -> None:
    office_holders = _build_two_male_deputy_speakers()

    assert build_hand_check_packets_script.get_label_office(label) is None
    assert (
        build_hand_check_packets_script.is_chair_label(label, _DAY, office_holders)
        is False
    )
    assert (
        build_hand_check_packets_script.get_role_section(label, _DAY, office_holders)
        is None
    )


def test_a_bare_deputy_speaker_label_is_the_chair_on_a_day_with_two_holders() -> None:
    office_holders = _build_two_male_deputy_speakers()

    assert (
        build_hand_check_packets_script.is_chair_label(
            "Mr Deputy Speaker", _DAY, office_holders
        )
        is True
    )
    assert (
        build_hand_check_packets_script.is_chair_label(
            "The Deputy Speaker", _DAY, office_holders
        )
        is True
    )


def test_the_printed_form_of_address_can_pick_one_of_two_deputy_speakers() -> None:
    office_holders = [
        _build_holder("Deputy Speaker", "Charles Chong", HandCheckFormOfAddress.MR),
        _build_holder("Deputy Speaker", "Jessica Tan", HandCheckFormOfAddress.MDM),
    ]

    assert [
        build_hand_check_packets_script.is_chair_label(label, _DAY, office_holders)
        for label in (
            "Mr Deputy Speaker",
            "Mdm Deputy Speaker",
            "Madam Deputy Speaker",
            "The Deputy Speaker",
        )
    ] == [False, False, False, True]


def test_the_printed_form_of_address_does_not_pick_out_one_of_two_holders_who_share_it() -> (
    None
):
    assert (
        build_hand_check_packets_script.is_chair_label(
            "Mr Deputy Speaker", _DAY, _build_two_male_deputy_speakers()
        )
        is True
    )


def test_a_deputy_speaker_label_is_an_office_label_on_a_day_with_one_or_no_holder() -> (
    None
):
    one_holder = [
        _build_holder("Deputy Speaker", "Charles Chong", HandCheckFormOfAddress.MR)
    ]

    assert (
        build_hand_check_packets_script.is_chair_label(
            "Mr Deputy Speaker", _DAY, one_holder
        )
        is False
    )
    assert (
        build_hand_check_packets_script.is_chair_label("Mr Deputy Speaker", _DAY, [])
        is False
    )


def test_an_office_holder_counts_from_the_first_day_to_the_last_day_inclusive() -> None:
    office_holder = _build_holder(
        "Speaker",
        "Abdullah Tarmugi",
        HandCheckFormOfAddress.MR,
        first_day=date(2010, 5, 5),
        last_day=date(2010, 5, 7),
    )

    assert [
        build_hand_check_packets_script.get_office_holders_on(
            "Speaker", sitting_day, [office_holder]
        )
        for sitting_day in (
            date(2010, 5, 4),
            date(2010, 5, 5),
            date(2010, 5, 7),
            date(2010, 5, 8),
        )
    ] == [[], [office_holder], [office_holder], []]


def test_an_office_holder_with_no_last_day_is_in_office_on_every_later_day() -> None:
    office_holder = _build_holder(
        "Speaker", "Seah Kian Peng", HandCheckFormOfAddress.MR
    )

    assert build_hand_check_packets_script.get_office_holders_on(
        "Speaker", date(2026, 11, 1), [office_holder]
    ) == [office_holder]


def test_the_office_match_ignores_case_and_ignores_other_offices() -> None:
    prime_minister = _build_holder(
        "Prime Minister", "Lee Hsien Loong", HandCheckFormOfAddress.MR
    )
    speaker = _build_holder("Speaker", "Abdullah Tarmugi", HandCheckFormOfAddress.MR)

    assert build_hand_check_packets_script.get_office_holders_on(
        "prime minister", _DAY, [prime_minister, speaker]
    ) == [prime_minister]


def test_an_office_label_gets_a_section_with_the_holders_of_that_office_on_the_day() -> (
    None
):
    prime_minister = _build_holder(
        "Prime Minister",
        "Lee Hsien Loong",
        HandCheckFormOfAddress.MR,
        first_day=date(2004, 8, 12),
    )
    later_prime_minister = _build_holder(
        "Prime Minister",
        "A Later Holder",
        HandCheckFormOfAddress.MR,
        first_day=date(2015, 1, 1),
    )

    assert build_hand_check_packets_script.get_role_section(
        "The Prime Minister", _DAY, [prime_minister, later_prime_minister]
    ) == HandCheckRoleSection(
        is_chair_label=False,
        office="Prime Minister",
        office_holders=[prime_minister],
        chair_marks=[],
    )


def test_an_office_label_with_no_table_entry_gets_a_section_with_no_holders() -> None:
    assert build_hand_check_packets_script.get_role_section(
        "The Chief Minister", _DAY, []
    ) == HandCheckRoleSection(
        is_chair_label=False, office="Chief Minister", office_holders=[], chair_marks=[]
    )


def test_a_chair_label_gets_a_section_with_the_speaker_and_deputy_speaker_entries_and_no_marks() -> (
    None
):
    prime_minister = _build_holder(
        "Prime Minister", "Lee Hsien Loong", HandCheckFormOfAddress.MR
    )
    [first_deputy, second_deputy] = _build_two_male_deputy_speakers()
    speaker = _build_holder("Speaker", "Abdullah Tarmugi", HandCheckFormOfAddress.MR)

    assert build_hand_check_packets_script.get_role_section(
        "The Chairman", _DAY, [prime_minister, first_deputy, second_deputy, speaker]
    ) == HandCheckRoleSection(
        is_chair_label=True,
        office=None,
        office_holders=[speaker, first_deputy, second_deputy],
        chair_marks=[],
    )


def test_the_chair_lines_of_a_committee_report_are_its_header_tag_and_its_chair_change() -> (
    None
):
    assert _get_chair_lines(SPRS2_COMMITTEE_HTML) == [
        build_hand_check_packets_script.ChairLine(_TAG_LINE, True, _TITLE),
        build_hand_check_packets_script.ChairLine(
            _THEREUPON_LINE, True, _TITLE, is_chair_change=True
        ),
    ]


def test_the_chair_lines_of_a_speaker_report_are_its_tag_its_note_and_its_chair_label() -> (
    None
):
    assert _get_chair_lines(SPRS2_APPENDIX_HTML) == [
        build_hand_check_packets_script.ChairLine(
            "MPs Speaking: Dr Yeoh Ghim Seng (Mr Speaker);", True, _TITLE
        ),
        build_hand_check_packets_script.ChairLine(
            "[Mr Speaker in the Chair]", True, _TITLE, is_chair_change=True
        ),
        build_hand_check_packets_script.ChairLine("Mr Speaker:", True, _TITLE),
    ]


def test_suspension_lines_are_chair_lines_that_are_not_marks() -> None:
    assert _get_chair_lines(_CHAIR_CHANGE_HTML) == [
        build_hand_check_packets_script.ChairLine("Mr Speaker:", True, _TITLE),
        build_hand_check_packets_script.ChairLine(
            "Sitting suspended at 4.00 pm.", False, _TITLE
        ),
        build_hand_check_packets_script.ChairLine(
            "Sitting resumed at 4.30 pm.", False, _TITLE
        ),
        build_hand_check_packets_script.ChairLine(
            "[Mr Deputy Speaker in the Chair]", True, _TITLE, is_chair_change=True
        ),
        build_hand_check_packets_script.ChairLine(
            "Thereupon, Mdm Speaker resumed the Chair.",
            True,
            _TITLE,
            is_chair_change=True,
        ),
        build_hand_check_packets_script.ChairLine("Mdm Speaker:", True, _TITLE),
    ]


@pytest.mark.parametrize(
    "line", ["Sitting accordingly suspended", "Sitting accordingly suspended at"]
)
def test_a_sitting_accordingly_suspended_line_is_a_chair_line_that_is_not_a_mark(
    line: str,
) -> None:
    assert _get_chair_lines(f"<p>{line}</p>") == [
        build_hand_check_packets_script.ChairLine(line, False, _TITLE)
    ]


@pytest.mark.parametrize(
    "report_html",
    [
        "<p>Mr Speaker said he is in the Chair of the day.</p>",
        "<p>MPs Speaking: Dr Tony Tan Keng Yam (Minister for Defence);</p>",
        "<p><b>The Chairman:</b> Order.</p>",
        "<p><b>Mr Lee Hsien Loong:</b> Yes.</p>",
        "<p>Mr Speaker left the Chair "
        + "after a long debate on the motion that went on for most of the day " * 4
        + "and the House rose.</p>",
    ],
)
def test_text_that_only_mentions_the_chair_is_not_a_chair_line(
    report_html: str,
) -> None:
    assert _get_chair_lines(report_html) == []


@pytest.mark.parametrize(
    ("report_html", "line", "is_chair_change"),
    [
        (
            "<p><b>Mr Deputy Speaker (Mr Charles Chong):</b> Order.</p>",
            "Mr Deputy Speaker (Mr Charles Chong):",
            False,
        ),
        (
            "<p>[Mdm Speaker temporarily in the Chair]</p>",
            "[Mdm Speaker temporarily in the Chair]",
            True,
        ),
        ("<p>Mr Speaker left the Chair.</p>", "Mr Speaker left the Chair.", True),
        (f"<p>{_WRAPPED_THEREUPON_LINE}</p>", _WRAPPED_THEREUPON_LINE, True),
    ],
)
def test_a_chair_label_a_chair_note_and_a_left_the_chair_line_are_marks(
    report_html: str, line: str, is_chair_change: bool
) -> None:
    assert _get_chair_lines(report_html) == [
        build_hand_check_packets_script.ChairLine(
            line, True, _TITLE, is_chair_change=is_chair_change
        )
    ]


def test_a_bare_deputy_label_on_a_two_deputy_day_is_not_a_mark() -> None:
    chair_lines = _get_chair_lines(
        _DEPUTY_SPEAKER_NOTE_HTML, _build_two_male_deputy_speakers()
    )
    one_holder = [
        _build_holder("Deputy Speaker", "Charles Chong", HandCheckFormOfAddress.MR)
    ]

    assert chair_lines == [
        build_hand_check_packets_script.ChairLine(
            _DEPUTY_SPEAKER_NOTE, True, _TITLE, is_chair_change=True
        )
    ]
    assert build_hand_check_packets_script.get_chair_marks(chair_lines, []) == [
        f"Last mark before the row: {_DEPUTY_SPEAKER_NOTE}{_TITLE_SUFFIX}"
    ]
    assert _get_chair_lines(_DEPUTY_SPEAKER_NOTE_HTML, one_holder) == [
        build_hand_check_packets_script.ChairLine(
            _DEPUTY_SPEAKER_NOTE, True, _TITLE, is_chair_change=True
        ),
        build_hand_check_packets_script.ChairLine("Mr Deputy Speaker:", True, _TITLE),
    ]


def test_the_chair_marks_of_the_thereupon_report_are_its_tag_before_and_the_chair_change_after() -> (
    None
):
    paragraphs = build_hand_check_packets_script.split_source_paragraphs(
        SPRS2_COMMITTEE_HTML
    )
    before_lines = build_hand_check_packets_script.get_chair_lines(
        paragraphs[:2], _TITLE, _DAY, []
    )
    after_lines = build_hand_check_packets_script.get_chair_lines(
        paragraphs[3:], _TITLE, _DAY, []
    )

    assert build_hand_check_packets_script.get_chair_marks(
        before_lines, after_lines
    ) == [
        "Last mark before the row: " + _TAG_LINE + _TITLE_SUFFIX,
        "Later change of chair after the row: " + _THEREUPON_LINE + _TITLE_SUFFIX,
    ]


def test_a_suspension_between_the_last_mark_and_the_row_is_listed_after_the_mark() -> (
    None
):
    chair_lines = _get_chair_lines(_CHAIR_CHANGE_HTML)

    assert build_hand_check_packets_script.get_chair_marks(
        chair_lines[:3], chair_lines[3:]
    ) == [
        f"Last mark before the row: Mr Speaker:{_TITLE_SUFFIX}",
        f"Between that mark and the row: Sitting suspended at 4.00 pm.{_TITLE_SUFFIX}",
        f"Between that mark and the row: Sitting resumed at 4.30 pm.{_TITLE_SUFFIX}",
        f"Later change of chair after the row: [Mr Deputy Speaker in the Chair]{_TITLE_SUFFIX}",
    ]


def test_a_suspension_between_the_row_and_the_next_mark_is_listed_before_that_mark() -> (
    None
):
    before_lines = [
        build_hand_check_packets_script.ChairLine(
            "[Mr Speaker in the Chair]", True, _TITLE
        )
    ]
    after_lines = [
        build_hand_check_packets_script.ChairLine(
            "Sitting suspended at 4.00 pm.", False, _TITLE
        ),
        build_hand_check_packets_script.ChairLine("Mr Speaker:", True, _TITLE),
        build_hand_check_packets_script.ChairLine(
            "Sitting resumed at 4.30 pm.", False, _TITLE
        ),
    ]

    assert build_hand_check_packets_script.get_chair_marks(
        before_lines, after_lines
    ) == [
        f"Last mark before the row: [Mr Speaker in the Chair]{_TITLE_SUFFIX}",
        f"Between the row and the next mark: Sitting suspended at 4.00 pm.{_TITLE_SUFFIX}",
        f"First mark after the row: Mr Speaker:{_TITLE_SUFFIX}",
    ]


def test_a_chair_note_after_the_row_is_listed_as_a_later_change_of_chair() -> None:
    before_lines = [
        build_hand_check_packets_script.ChairLine(
            "[Mr DEPUTY SPEAKER (Mr Mammen) in the Chair]",
            True,
            _TITLE,
            is_chair_change=True,
        )
    ]
    after_lines = [
        build_hand_check_packets_script.ChairLine(
            "Sitting suspended at 4.00 pm.", False, _TITLE
        ),
        build_hand_check_packets_script.ChairLine(
            "[Mr SPEAKER in the Chair]", True, _TITLE, is_chair_change=True
        ),
        build_hand_check_packets_script.ChairLine("Mr Speaker:", True, _TITLE),
    ]

    assert build_hand_check_packets_script.get_chair_marks(
        before_lines, after_lines
    ) == [
        f"Last mark before the row: [Mr DEPUTY SPEAKER (Mr Mammen) in the Chair]{_TITLE_SUFFIX}",
        f"Between the row and the next mark: Sitting suspended at 4.00 pm.{_TITLE_SUFFIX}",
        f"Later change of chair after the row: [Mr SPEAKER in the Chair]{_TITLE_SUFFIX}",
    ]


def test_only_the_last_mark_before_and_the_first_mark_after_the_row_are_listed() -> (
    None
):
    before_lines = [
        build_hand_check_packets_script.ChairLine(
            "[Mr Speaker in the Chair]", True, _TITLE
        ),
        build_hand_check_packets_script.ChairLine(
            "[Mr Deputy Speaker in the Chair]", True, _TITLE
        ),
    ]
    after_lines = [
        build_hand_check_packets_script.ChairLine("Mr Speaker:", True, _TITLE),
        build_hand_check_packets_script.ChairLine("Mdm Speaker:", True, _TITLE),
    ]

    assert build_hand_check_packets_script.get_chair_marks(
        before_lines, after_lines
    ) == [
        f"Last mark before the row: [Mr Deputy Speaker in the Chair]{_TITLE_SUFFIX}",
        f"First mark after the row: Mr Speaker:{_TITLE_SUFFIX}",
    ]


def test_there_are_no_chair_marks_when_neither_side_has_a_mark() -> None:
    suspension_line = build_hand_check_packets_script.ChairLine(
        "Sitting suspended at 4.00 pm.", False, _TITLE
    )

    assert build_hand_check_packets_script.get_chair_marks([], []) == []
    assert build_hand_check_packets_script.get_chair_marks([suspension_line], []) == []


def test_each_chair_mark_names_the_report_it_came_from() -> None:
    before_line = build_hand_check_packets_script.ChairLine(
        "[Mr Speaker in the Chair]", True, "Earlier Title"
    )
    after_line = build_hand_check_packets_script.ChairLine(
        "Mr Speaker:", True, "Later Title"
    )

    assert build_hand_check_packets_script.get_chair_marks(
        [before_line], [after_line]
    ) == [
        "Last mark before the row: [Mr Speaker in the Chair] (report: Earlier Title)",
        "First mark after the row: Mr Speaker: (report: Later Title)",
    ]


def test_a_newer_system_report_id_loses_its_trailing_hash_and_encodes_an_inner_one() -> (
    None
):
    assert (
        build_hand_check_packets_script.get_official_record_url(
            "00123456-ZZ.00123457-ZZ_1#", ReportVersion.SPRS3, None
        )
        == "https://sprs.parl.gov.sg/search/#/sprs3topic?reportid=00123456-ZZ.00123457-ZZ_1"
    )
    assert (
        build_hand_check_packets_script.get_official_record_url(
            "00076180-WA.00076632-WA_8#id-f8ee1819-646d-47b3-9e05-bdbbed80eae6#",
            ReportVersion.SPRS3,
            "ignored.html",
        )
        == "https://sprs.parl.gov.sg/search/#/sprs3topic?reportid=00076180-WA.00076632-WA_8%23id-f8ee1819-646d-47b3-9e05-bdbbed80eae6"
    )


def test_an_older_system_link_is_made_from_the_html_file_name() -> None:
    assert (
        build_hand_check_packets_script.get_official_record_url(
            "an-older-report-id", ReportVersion.SPRS2, "#030_20031016_S0003_T0008.html-"
        )
        == "https://sprs.parl.gov.sg/search/#/topic?reportid=%23030_20031016_S0003_T0008.html-"
    )


def test_an_older_system_report_with_no_html_file_name_links_to_the_search_page() -> (
    None
):
    assert (
        build_hand_check_packets_script.get_official_record_url(
            "an-older-report-id", ReportVersion.SPRS2, None
        )
        == "https://sprs.parl.gov.sg/search"
    )

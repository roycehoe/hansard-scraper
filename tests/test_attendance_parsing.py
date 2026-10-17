import json

from database.sitting import Sitting
from database.speaker import Speaker
from schemas.constituency_names import ConstituencyNames
from services.attendance import (
    build_constituency_lookups,
    build_speaker_lookups,
    get_sitting_attendance,
    get_sitting_attendance_from_list,
    resolve_canonical_name,
)

_CONSTITUENCY_LOOKUPS = build_constituency_lookups(ConstituencyNames(names=[], rows=[]))


def _get_rows(markdown: str, sitting_date: str = "1-1-1970") -> list[tuple[str, bool, str | None]]:
    sitting = Sitting(id=1, sitting_date=sitting_date, volume_no=29, markdown_content=markdown)
    records = get_sitting_attendance(sitting, build_speaker_lookups([]), _CONSTITUENCY_LOOKUPS)
    return [(record.speaker_name, record.is_present, record.location_name) for record in records]


def test_a_heading_glued_to_the_last_entry_ends_the_list() -> None:
    markdown = (
        "PRESENT:\nMr Lim Cher Kheng (Changi).\nMr Wong Foo Nam (Pasir Panjang). **APPROPRIATION BILL**\n"
        "Order read for resumed consideration in Committee\nMr Lee Kuan Yew (Tanjong Pagar).\n"
    )

    assert _get_rows(markdown) == [("Lim Cher Kheng", True, "Changi"), ("Wong Foo Nam", True, "Pasir Panjang")]


def test_an_assent_block_after_the_absent_list_gives_no_rows() -> None:
    markdown = (
        "PRESENT:\nMr Lim Cher Kheng (Changi).\nABSENT:\nMr Wong Foo Nam (Pasir Panjang).\n"
        "**ASSENT TO BILLS PASSED**\nThe following Bills were assented to by the President on the date stated:\n"
        "12th March 1996\n|  TAN SOO KHOON\n|  _Speaker_\n"
    )

    assert _get_rows(markdown) == [("Lim Cher Kheng", True, "Changi"), ("Wong Foo Nam", False, "Pasir Panjang")]


def test_a_date_a_table_row_a_heading_and_a_bold_label_each_end_the_list() -> None:
    for line in ("12th March, 1996", "|  _Speaker,_", "## PARLIAMENTARY DEBATES", "**Mr Speaker:** I have received a message", "*Appendix, cols. 895-900."):
        markdown = f"PRESENT:\nMr Lim Cher Kheng (Changi).\n{line}\nMr Wong Foo Nam (Pasir Panjang).\n"

        assert _get_rows(markdown) == [("Lim Cher Kheng", True, "Changi")], line


def test_a_bullet_entry_is_still_an_entry() -> None:
    assert _get_rows("PRESENT:\n* Mr Lim Cher Kheng (Changi).\n* Mr Wong Foo Nam (Pasir Panjang).\n") == [
        ("Lim Cher Kheng", True, "Changi"),
        ("Wong Foo Nam", True, "Pasir Panjang"),
    ]


def test_a_wrapped_office_title_gives_no_row_and_the_list_goes_on() -> None:
    markdown = (
        "PRESENT:\nDr Lee Chiaw Meng (Farrer Park), Minister for Science and Technology.\nTechnology.\n"
        "Mr Phua Bah Lee (Tampines), Senior Parliamentary Secretary to the Minister of Defence.\n"
        "Parliamentary Secretary to the Minister for Culture.\n"
        "Mr Rohan bin Kamis (Telok Blangah).\n"
    )

    assert _get_rows(markdown) == [
        ("Lee Chiaw Meng", True, "Farrer Park"),
        ("Phua Bah Lee", True, "Tampines"),
        ("Rohan bin Kamis", True, "Telok Blangah"),
    ]


def test_procedural_text_after_the_list_gives_no_row() -> None:
    markdown = "PRESENT:\nMr Wong Foo Nam (Pasir Panjang).\n\nBefore taking the Chair, Mr SPEAKER took and subscribed the Oath of Allegiance.\n#### ADMINISTRATION OF OATHS\n"

    assert _get_rows(markdown) == [("Wong Foo Nam", True, "Pasir Panjang")]


def test_a_title_without_a_constituency_is_still_a_name() -> None:
    assert _get_rows("PRESENT:\nMr P. Coomaraswamy, Deputy Speaker.\nMr SPEAKER (Sir George Oehlers, O.B.E.).\n") == [
        ("P. Coomaraswamy, Deputy Speaker", True, None),
        ("George Oehlers", True, None),
    ]


def test_a_speaker_line_that_names_the_speaker_before_the_constituency_gives_the_speaker() -> None:
    assert _get_rows("PRESENT:\nMr SPEAKER Mr Tan Soo Khoon (Bedok GRC).\nMr Abdullah Tarmugi (Bedok GRC).\n") == [
        ("Tan Soo Khoon", True, "Bedok GRC"),
        ("Abdullah Tarmugi", True, "Bedok GRC"),
    ]


def test_a_name_that_holds_markup_is_never_a_name() -> None:
    attendance_list = json.dumps([
        {"mpName": "Mr Lim Cher Kheng (Changi).", "attendance": True},
        {"mpName": "| _Speaker,_", "attendance": False},
        {"mpName": "Mr Foo_Bar (Changi).", "attendance": False},
    ])
    sitting = Sitting(id=1, sitting_date="1-1-2013", volume_no=89, attendance_list=attendance_list)

    records = get_sitting_attendance_from_list(sitting, build_speaker_lookups([]), _CONSTITUENCY_LOOKUPS)

    assert [record.speaker_name for record in records] == ["Lim Cher Kheng"]


def test_a_member_listed_as_present_and_absent_keeps_the_present_row() -> None:
    markdown = "PRESENT:\nMr Lim Cher Kheng (Changi).\nMr Wong Foo Nam (Pasir Panjang).\nABSENT:\nMr Lim Cher Kheng (Changi).\n"

    assert _get_rows(markdown) == [("Lim Cher Kheng", True, "Changi"), ("Wong Foo Nam", True, "Pasir Panjang")]


def test_a_member_listed_twice_as_absent_keeps_one_row() -> None:
    markdown = "PRESENT:\nMr Wong Foo Nam (Pasir Panjang).\nABSENT:\nMr Lim Cher Kheng (Changi).\nMr Lim Cher Kheng (Changi).\n"

    assert _get_rows(markdown) == [("Wong Foo Nam", True, "Pasir Panjang"), ("Lim Cher Kheng", False, "Changi")]


def test_an_attendance_list_keeps_one_row_per_member_too() -> None:
    attendance_list = json.dumps([
        {"mpName": "Mr Lim Cher Kheng (Changi).", "attendance": False},
        {"mpName": "Mr Lim Cher Kheng (Changi).", "attendance": True},
    ])
    sitting = Sitting(id=1, sitting_date="1-1-2013", volume_no=89, attendance_list=attendance_list)

    records = get_sitting_attendance_from_list(sitting, build_speaker_lookups([]), _CONSTITUENCY_LOOKUPS)

    assert [(record.speaker_name, record.is_present) for record in records] == [("Lim Cher Kheng", True)]


def test_three_ocr_forms_resolve_to_their_speakers() -> None:
    speakers = [
        Speaker(id=1, name="Wong Lin Ken", party="People's Action Party", is_legislative_assembly=False, parliament_number=2),
        Speaker(id=2, name="Irene Ng Phek Hoong", party="People's Action Party", is_legislative_assembly=False, parliament_number=12),
        Speaker(id=3, name="Braga, A.J.", party="Singapore Progressive Party", is_legislative_assembly=True, parliament_number=0),
    ]
    lookups = build_speaker_lookups(speakers)

    assert resolve_canonical_name("Wong Lm Ken", 2, lookups) == "Wong Lin Ken"
    assert resolve_canonical_name("Phek Hoong", 12, lookups) == "Irene Ng Phek Hoong"
    assert resolve_canonical_name("The Hounourable Mr A.J. Braga", 0, lookups) == "Braga, A.J."


def test_three_more_ocr_forms_resolve_to_their_speakers() -> None:
    speakers = [
        Speaker(id=1, name="Teo Chong Tee", party="People's Action Party", is_legislative_assembly=False, parliament_number=4),
        Speaker(id=2, name="Tan Cheng San", party="People's Action Party", is_legislative_assembly=False, parliament_number=4),
        Speaker(id=3, name="Tay Boon Too", party="People's Action Party", is_legislative_assembly=False, parliament_number=1),
    ]
    lookups = build_speaker_lookups(speakers)

    assert resolve_canonical_name("Too Chong Tee", 4, lookups) == "Teo Chong Tee"
    assert resolve_canonical_name("Tan Cheng Sen", 4, lookups) == "Tan Cheng San"
    assert resolve_canonical_name("Tay Bon Too", 1, lookups) == "Tay Boon Too"


def test_a_procession_line_ends_the_list_and_gives_no_row() -> None:
    markdown = (
        "PRESENT:\nMr SPEAKER (Sir George Oehlers, O.B.E.).\nMr Wong Foo Nam (Pasir Panjang).\nABSENT:\nMiss Fung Yin Ching (Stamford).\n"
        "Mr Speaker, preceded by the Serjeant at Arms (with Mace) and followed by the Clerk, entered the Chamber.\n"
    )

    assert _get_rows(markdown, "20-7-1960") == [("George Oehlers", True, None), ("Wong Foo Nam", True, "Pasir Panjang"), ("Fung Yin Ching", False, "Stamford")]


def test_a_speaker_entry_that_names_no_one_takes_the_name_of_the_presiding_officer_on_that_date() -> None:
    for line in ("Mr Speaker (Sir George Oehlers, O.B.E.).", "Mr Speaker (Dr Yeoh Ghim Seng) (Joo Chiat).", "Mr SPEAKER (Dr Yeoh Ghim Seng, B.B.M., J.P. (Joo Chiat)"):
        assert _get_rows(f"PRESENT:\n{line}\n", "3-8-1971") == [("Yeoh Ghim Seng", True, None)], line


def test_a_speaker_entry_stays_when_no_one_presided_on_that_date() -> None:
    assert _get_rows("PRESENT:\nMr Speaker (Sir George Oehlers, O.B.E.).\n", "1-1-1989") == [("Speaker", True, "Sir George Oehlers, O.B.E.")]


def test_a_wrapped_entry_whose_start_the_source_lost_becomes_the_member_it_belongs_to() -> None:
    markdown = "PRESENT:\nMr Wong Soon Fong (Toa Payoh).\nTunah), Parliamentary Secretary to the Prime Minister.\nMr Yong Nyuk Lin (Geylang West), Minister for Education.\n"

    assert _get_rows(markdown, "10-6-1963") == [
        ("Wong Soon Fong", True, "Toa Payoh"),
        ("Yaacob Bin Mohamed", True, "Bukit Timah"),
        ("Yong Nyuk Lin", True, "Geylang West"),
    ]

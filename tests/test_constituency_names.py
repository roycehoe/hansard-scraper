import json
from pathlib import Path

from crud.attendance import AttendanceLocationRow
from database.sitting import Sitting
from schemas.constituency_names import (
    ConstituencyName,
    ConstituencyNames,
    ConstituencyRowName,
)
from services.attendance import (
    ConstituencyLookups,
    LocationChange,
    build_constituency_lookups,
    build_speaker_lookups,
    get_constituency_name,
    get_location_changes,
    get_sitting_attendance,
    get_sitting_attendance_from_list,
)

_DATA_FILE = Path(__file__).parent.parent / "data" / "constituency_names.json"
_ROW_NAME_COUNT = 8


def _get_file_lookups() -> tuple[ConstituencyNames, ConstituencyLookups]:
    constituency_names = ConstituencyNames.model_validate(json.loads(_DATA_FILE.read_text()))
    return constituency_names, build_constituency_lookups(constituency_names)


def _get_test_lookups() -> ConstituencyLookups:
    return build_constituency_lookups(
        ConstituencyNames(
            names=[
                ConstituencyName(printed="Aijunied", constituency="Aljunied"),
                ConstituencyName(printed="Chua Chu Kang", parliament_number=0, constituency="Choa Chu Kang"),
                ConstituencyName(printed="Mac Pherson", constituency="MacPherson"),
            ],
            rows=[
                ConstituencyRowName(
                    sitting_date="13-2-1960", speaker_name="Goh Chew Chua", printed="Mac Pherson", constituency="Tampines", reason="test"
                )
            ],
        )
    )


def test_a_printed_form_with_no_entry_is_kept() -> None:
    assert get_constituency_name("Bukit Timah", 5, "1-1-1980", "Someone", _get_test_lookups()) == "Bukit Timah"


def test_a_missing_constituency_stays_missing() -> None:
    assert get_constituency_name(None, 5, "1-1-1980", "Someone", _get_test_lookups()) is None


def test_an_entry_without_a_parliament_applies_to_every_parliament() -> None:
    lookups = _get_test_lookups()

    assert get_constituency_name("Aijunied", 0, "1-1-1960", "Someone", lookups) == "Aljunied"
    assert get_constituency_name("Aijunied", 9, "1-1-2000", "Someone", lookups) == "Aljunied"
    assert get_constituency_name("Aijunied", None, None, None, lookups) == "Aljunied"


def test_an_entry_with_a_parliament_applies_to_that_parliament_only() -> None:
    lookups = _get_test_lookups()

    assert get_constituency_name("Chua Chu Kang", 0, "1-1-1960", "Someone", lookups) == "Choa Chu Kang"
    assert get_constituency_name("Chua Chu Kang", 2, "1-1-1970", "Someone", lookups) == "Chua Chu Kang"


def test_a_row_entry_beats_the_general_entry_and_applies_to_one_row() -> None:
    lookups = _get_test_lookups()

    assert get_constituency_name("Mac Pherson", 0, "13-2-1960", "Goh Chew Chua", lookups) == "Tampines"
    assert get_constituency_name("Mac Pherson", 0, "13-2-1960", "Someone Else", lookups) == "MacPherson"
    assert get_constituency_name("Mac Pherson", 0, "14-2-1960", "Goh Chew Chua", lookups) == "MacPherson"


def test_data_file_has_no_duplicate_keys_and_no_entry_that_maps_to_itself() -> None:
    constituency_names, _ = _get_file_lookups()

    name_keys = [(name.printed, name.parliament_number) for name in constituency_names.names]
    row_keys = [(row.sitting_date, row.speaker_name, row.printed) for row in constituency_names.rows]
    assert len(name_keys) == len(set(name_keys))
    assert len(row_keys) == len(set(row_keys))
    assert all(name.printed != name.constituency for name in constituency_names.names)
    assert all(row.printed != row.constituency for row in constituency_names.rows)
    assert len(constituency_names.rows) == _ROW_NAME_COUNT


def test_data_file_targets_of_general_entries_are_never_printed_forms_of_general_entries() -> None:
    constituency_names, _ = _get_file_lookups()

    printed_forms = {name.printed for name in constituency_names.names if name.parliament_number is None}
    assert not printed_forms & {name.constituency for name in constituency_names.names if name.parliament_number is None}
    assert not printed_forms & {row.constituency for row in constituency_names.rows}


def test_data_file_keeps_the_spellings_the_source_prints_consistently_as_the_election_spelling() -> None:
    _, lookups = _get_file_lookups()

    assert get_constituency_name("Ponggol-Tampenis", 0, "1-1-1957", "Someone", lookups) == "Punggol-Tampines"
    assert get_constituency_name("Kampung Glam", 3, "1-1-1969", "Someone", lookups) == "Kampong Glam"
    assert get_constituency_name("Choa Chu Kang", 2, "1-1-1970", "Someone", lookups) == "Chua Chu Kang"
    assert get_constituency_name("Mac Pherson", 3, "1-1-1969", "Someone", lookups) == "MacPherson"


def test_data_file_leaves_seat_types_and_non_places_alone() -> None:
    _, lookups = _get_file_lookups()

    assert get_constituency_name("Nominated Member", 8, "1-1-1995", "Someone", lookups) == "Nominated Member"
    assert get_constituency_name("Non-Constituency Member", 8, "1-1-1995", "Someone", lookups) == "Non-Constituency Member"
    assert get_constituency_name("Acting", 0, "1-1-1957", "Someone", lookups) == "Acting"
    assert get_constituency_name("Sir George Oehlers, O.B.E.", 0, "1-1-1957", "Someone", lookups) == "Sir George Oehlers, O.B.E."
    assert get_constituency_name("Amendment", 0, "1-1-1957", "Someone", lookups) == "Amendment"


def test_data_file_fixes_the_spelling_of_a_seat_type_only() -> None:
    _, lookups = _get_file_lookups()

    assert get_constituency_name("exofficio", 0, "1-1-1957", "Someone", lookups) == "ex-officio"
    assert get_constituency_name("NominatedMember", 10, "1-1-2005", "Someone", lookups) == "Nominated Member"


def test_data_file_fixes_the_ward_rows_of_the_sitting_of_7_march_2011() -> None:
    _, lookups = _get_file_lookups()

    assert get_constituency_name("Nee Soon", 11, "7-3-2011", "K Shanmugam", lookups) == "Sembawang"
    assert get_constituency_name("Nee Soon", 11, "7-3-2011", "Lee Bee Wah", lookups) == "Ang Mo Kio"
    assert get_constituency_name("Pioneer", 11, "7-3-2011", "Cedric Foo Chee Keng", lookups) == "West Coast"
    assert get_constituency_name("Pioneer", 12, "1-1-2012", "Someone", lookups) == "Pioneer"


def test_sitting_markdown_attendance_takes_the_mapped_constituency() -> None:
    markdown = "PRESENT:\nMr Goh Chew Chua (Mac Pherson).\nMr Lee Kuan Yew (Aijunied).\nMr Lim Cher Kheng (Changi).\nABSENT:\nMr Wong Foo Nam (Chua Chu Kang).\n"
    sitting = Sitting(id=1, sitting_date="13-2-1960", volume_no=14, markdown_content=markdown)

    records = get_sitting_attendance(sitting, build_speaker_lookups([]), _get_test_lookups())

    assert [(record.speaker_name, record.location_name) for record in records] == [
        ("Goh Chew Chua", "Tampines"),
        ("Lee Kuan Yew", "Aljunied"),
        ("Lim Cher Kheng", "Changi"),
        ("Wong Foo Nam", "Choa Chu Kang"),
    ]


def test_attendance_list_takes_the_mapped_constituency() -> None:
    attendance_list = json.dumps([{"mpName": "Mr Lee Kuan Yew (Aijunied)", "attendance": True}, {"mpName": "Mr Lim Cher Kheng", "attendance": False}])
    sitting = Sitting(id=1, sitting_date="13-2-1960", volume_no=89, attendance_list=attendance_list)

    records = get_sitting_attendance_from_list(sitting, build_speaker_lookups([]), _get_test_lookups())

    assert [(record.speaker_name, record.location_name) for record in records] == [("Lee Kuan Yew", "Aljunied"), ("Lim Cher Kheng", None)]


def test_location_changes_cover_the_rows_that_differ_and_are_empty_once_applied() -> None:
    lookups = _get_test_lookups()
    rows = [
        AttendanceLocationRow(1, "Lee Kuan Yew", "Aijunied", "1-1-1960", None, 14),
        AttendanceLocationRow(2, "Lim Cher Kheng", "Changi", "1-1-1960", None, 14),
        AttendanceLocationRow(3, "Wong Foo Nam", "Chua Chu Kang", "1-1-1960", None, 14),
        AttendanceLocationRow(4, "Wong Foo Nam", "Chua Chu Kang", "1-1-1970", None, 30),
    ]

    location_changes = get_location_changes(rows, lookups)

    assert location_changes == [
        LocationChange(1, "Lee Kuan Yew", "1-1-1960", "Aijunied", "Aljunied"),
        LocationChange(3, "Wong Foo Nam", "1-1-1960", "Chua Chu Kang", "Choa Chu Kang"),
    ]
    applied_rows = [
        AttendanceLocationRow(row.id, row.speaker_name, next((change.location_name_after for change in location_changes if change.id == row.id), row.location_name), row.sitting_date, row.parlement_no, row.volume_no)
        for row in rows
    ]
    assert get_location_changes(applied_rows, lookups) == []

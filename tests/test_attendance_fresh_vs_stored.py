from typing import Optional

from scripts.attendance_fresh_vs_stored import RowView, get_row_differences


def _get_view(speaker_name: str, is_present: bool = True, location_name: Optional[str] = None, speaker_id: Optional[int] = 1, attendance_id: Optional[int] = None) -> RowView:
    return RowView(attendance_id, speaker_name, is_present, location_name, speaker_id)


def test_equal_rows_cancel_out_whatever_their_order() -> None:
    stored_rows = [_get_view("A", speaker_id=1, attendance_id=1), _get_view("B", speaker_id=2, attendance_id=2)]
    fresh_rows = [_get_view("B", speaker_id=2), _get_view("A", speaker_id=1)]

    assert get_row_differences(stored_rows, fresh_rows) == []


def test_a_location_acting_row_is_its_own_class() -> None:
    stored_rows = [_get_view("A", location_name="Acting", attendance_id=1)]
    fresh_rows = [_get_view("A", location_name="ex-officio")]

    differences = get_row_differences(stored_rows, fresh_rows)

    assert [difference.difference_class for difference in differences] == ["acting_location"]
    assert differences[0].differing_fields == ("location_name",)


def test_a_spelling_difference_pairs_by_speaker_id() -> None:
    stored_rows = [_get_view("Tan  Ah", speaker_id=7, attendance_id=1)]
    fresh_rows = [_get_view("Tan Ah", speaker_id=7)]

    differences = get_row_differences(stored_rows, fresh_rows)

    assert [difference.difference_class for difference in differences] == ["differs_speaker_name"]


def test_unpaired_rows_stand_alone_on_each_side() -> None:
    stored_rows = [_get_view("A", speaker_id=1, attendance_id=1), _get_view("Old", speaker_id=2, attendance_id=2)]
    fresh_rows = [_get_view("A", speaker_id=1), _get_view("New", speaker_id=3)]

    classes = sorted(difference.difference_class for difference in get_row_differences(stored_rows, fresh_rows))

    assert classes == ["fresh_only", "stored_only"]


def test_a_stored_row_without_speaker_id_and_the_ocr_name_are_classed_first() -> None:
    no_id = get_row_differences([_get_view("Zed", speaker_id=None, attendance_id=1)], [_get_view("Zed", location_name="X", speaker_id=None)])
    ocr = get_row_differences([_get_view("Encik lbrahim", speaker_id=4, attendance_id=2)], [_get_view("Ibrahim", speaker_id=4)])

    assert [difference.difference_class for difference in no_id] == ["stored_without_speaker_id"]
    assert [difference.difference_class for difference in ocr] == ["ocr_lbrahim"]


def test_a_watched_row_equal_to_its_fresh_row_is_still_listed_with_no_differing_fields() -> None:
    stored_rows = [_get_view("A", location_name="Acting", attendance_id=1), _get_view("B", attendance_id=2)]
    fresh_rows = [_get_view("A", location_name="Acting"), _get_view("B")]

    differences = get_row_differences(stored_rows, fresh_rows)

    assert [(difference.difference_class, difference.differing_fields) for difference in differences] == [("acting_location", ())]

from crud.attached_file import AttachedFileRow
from crud.attached_file_pointer import AttachedFilePointerUntiedRow
from services.attached_file import (
    get_attached_file_ties,
    get_file_tie_count,
    is_paragraph_tie_stale,
)
from utils.attached_file_tie import AttachedFilePointerTie

_ADDRESS = "20230301/annex-Committee of Supply.pdf"
_OTHER_ADDRESS = "PDFs/Reply.pdf"
_TIED_POINTER_COUNT = 2


def test_a_pointer_ties_to_the_one_file_with_its_address() -> None:
    ties = get_attached_file_ties(
        [AttachedFilePointerUntiedRow(10, _ADDRESS)],
        [AttachedFileRow(20, _ADDRESS), AttachedFileRow(21, _OTHER_ADDRESS)],
    )

    assert ties == [AttachedFilePointerTie(10, 20)]


def test_no_file_gives_no_tie() -> None:
    ties = get_attached_file_ties(
        [AttachedFilePointerUntiedRow(10, _ADDRESS)],
        [AttachedFileRow(21, _OTHER_ADDRESS)],
    )

    assert ties == []


def test_two_files_with_one_address_give_no_tie() -> None:
    ties = get_attached_file_ties(
        [AttachedFilePointerUntiedRow(10, _ADDRESS)],
        [AttachedFileRow(20, _ADDRESS), AttachedFileRow(22, _ADDRESS)],
    )

    assert ties == []


def test_several_pointers_to_one_file_each_tie() -> None:
    ties = get_attached_file_ties(
        [
            AttachedFilePointerUntiedRow(10, _ADDRESS),
            AttachedFilePointerUntiedRow(11, _ADDRESS),
        ],
        [AttachedFileRow(20, _ADDRESS)],
    )

    assert ties == [AttachedFilePointerTie(10, 20), AttachedFilePointerTie(11, 20)]


def test_a_stale_paragraph_tie_is_detected_and_a_fresh_one_is_not() -> None:
    assert is_paragraph_tie_stale("Vernacular Speech", "Some other words.")
    assert not is_paragraph_tie_stale(
        "Vernacular Speech", "See __Vernacular\xa0Speech__."
    )


def test_file_tie_count_counts_only_an_address_held_by_exactly_one_file() -> None:
    assert (
        get_file_tie_count(
            [_ADDRESS, _ADDRESS, _OTHER_ADDRESS, "PDFs/none.pdf"],
            [_ADDRESS, _OTHER_ADDRESS, _OTHER_ADDRESS],
        )
        == _TIED_POINTER_COUNT
    )

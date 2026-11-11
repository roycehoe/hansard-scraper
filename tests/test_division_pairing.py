from datetime import date
from typing import Optional

from enums import MinutesDivisionPairing
from services.division_pairing import (
    PairableHansardDivision,
    PairableMinutesDivision,
    get_division_pairs,
)

_SITTING_DATE = date(2021, 10, 4)


def _hansard(
    division_id: int,
    speech_number: int,
    ayes: int,
    noes: int,
    abstentions: Optional[int] = None,
    sprs_report_id: str = "a",
    speech_ordinal: int = 1,
    sitting_date: date = _SITTING_DATE,
) -> PairableHansardDivision:
    return PairableHansardDivision(
        division_id,
        sitting_date,
        sprs_report_id,
        speech_number,
        speech_ordinal,
        ayes,
        noes,
        abstentions,
    )


def _minutes(
    ordinal: int,
    ayes: int,
    noes: int,
    abstentions: Optional[int] = None,
    sitting_date: date = _SITTING_DATE,
) -> PairableMinutesDivision:
    return PairableMinutesDivision(sitting_date, ordinal, ayes, noes, abstentions)


def test_equal_counts_pair_in_order() -> None:
    pairings = get_division_pairs(
        [_hansard(11, 2, 70, 10), _hansard(10, 1, 70, 10, sprs_report_id="b")],
        [_minutes(1, 70, 10), _minutes(2, 70, 10)],
    )

    assert [pairing.pairing for pairing in pairings] == [MinutesDivisionPairing.PAIRED] * 2
    assert [pairing.division_id for pairing in pairings] == [10, 11]
    assert [pairing.minutes_ordinal for pairing in pairings] == [1, 2]


def test_equal_counts_in_one_report_order_by_speech_ordinal() -> None:
    pairings = get_division_pairs(
        [_hansard(11, 1, 70, 10, speech_ordinal=9), _hansard(10, 1, 70, 10, speech_ordinal=3)],
        [_minutes(1, 70, 10), _minutes(2, 70, 10)],
    )

    assert [pairing.division_id for pairing in pairings] == [10, 11]


def test_unequal_numbers_pair_nothing_and_name_both_sides() -> None:
    pairings = get_division_pairs(
        [_hansard(10, 1, 70, 10)],
        [_minutes(1, 70, 10), _minutes(2, 70, 10)],
    )

    assert [pairing.pairing for pairing in pairings] == [
        MinutesDivisionPairing.UNEQUAL_NUMBER
    ] * 2
    assert [pairing.division_id for pairing in pairings] == [None, None]
    assert [pairing.hansard_division_ids for pairing in pairings] == [(10,), (10,)]


def test_different_counts_on_one_date_do_not_pair() -> None:
    pairings = get_division_pairs(
        [_hansard(10, 1, 70, 10)],
        [_minutes(1, 70, 11), _minutes(2, 71, 10)],
    )

    assert [pairing.pairing for pairing in pairings] == [
        MinutesDivisionPairing.NO_MATCHING_DIVISION
    ] * 2
    assert [pairing.division_id for pairing in pairings] == [None, None]
    assert [pairing.hansard_division_ids for pairing in pairings] == [(), ()]


def test_a_tie_on_speech_number_between_reports_is_tied() -> None:
    pairings = get_division_pairs(
        [
            _hansard(10, 1, 70, 10, sprs_report_id="a"),
            _hansard(11, 1, 70, 10, sprs_report_id="b"),
        ],
        [_minutes(1, 70, 10), _minutes(2, 70, 10)],
    )

    assert [pairing.pairing for pairing in pairings] == [MinutesDivisionPairing.TIED] * 2
    assert [pairing.division_id for pairing in pairings] == [None, None]
    assert [pairing.hansard_division_ids for pairing in pairings] == [(10, 11), (10, 11)]


def test_a_tie_on_speech_number_inside_one_report_is_not_tied() -> None:
    pairings = get_division_pairs(
        [
            _hansard(10, 1, 70, 10, speech_ordinal=1),
            _hansard(11, 1, 70, 10, speech_ordinal=2),
        ],
        [_minutes(1, 70, 10), _minutes(2, 70, 10)],
    )

    assert [pairing.pairing for pairing in pairings] == [MinutesDivisionPairing.PAIRED] * 2


def test_differing_printed_abstentions_pair_none_of_the_group() -> None:
    pairings = get_division_pairs(
        [_hansard(10, 1, 70, 10, abstentions=1), _hansard(11, 2, 70, 10, abstentions=2)],
        [_minutes(1, 70, 10, abstentions=1), _minutes(2, 70, 10, abstentions=3)],
    )

    assert [pairing.pairing for pairing in pairings] == [
        MinutesDivisionPairing.ABSTENTIONS_DIFFER
    ] * 2
    assert [pairing.division_id for pairing in pairings] == [None, None]
    assert [pairing.hansard_division_ids for pairing in pairings] == [(10, 11), (10, 11)]


def test_abstentions_missing_on_one_side_still_pair() -> None:
    pairings = get_division_pairs(
        [_hansard(10, 1, 70, 10, abstentions=None)],
        [_minutes(1, 70, 10, abstentions=2)],
    )

    assert [pairing.pairing for pairing in pairings] == [MinutesDivisionPairing.PAIRED]
    assert [pairing.division_id for pairing in pairings] == [10]


def test_no_hansard_division_is_no_matching_division() -> None:
    pairings = get_division_pairs([], [_minutes(1, 70, 10)])

    assert pairings[0].pairing == MinutesDivisionPairing.NO_MATCHING_DIVISION
    assert pairings[0].division_id is None
    assert pairings[0].hansard_division_ids == ()


def test_a_hansard_division_without_noes_is_not_a_candidate() -> None:
    hansard_division = PairableHansardDivision(
        10, _SITTING_DATE, "a", 1, 1, 70, None, None
    )

    pairings = get_division_pairs([hansard_division], [_minutes(1, 70, 0)])

    assert pairings[0].pairing == MinutesDivisionPairing.NO_MATCHING_DIVISION
    assert pairings[0].hansard_division_ids == ()


def test_divisions_on_other_dates_never_pair() -> None:
    pairings = get_division_pairs(
        [_hansard(10, 1, 70, 10, sitting_date=date(2021, 10, 5))],
        [_minutes(1, 70, 10)],
    )

    assert pairings[0].pairing == MinutesDivisionPairing.NO_MATCHING_DIVISION

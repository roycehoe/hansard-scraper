from datetime import date

from database.party_affiliation import PartyAffiliation
from enums import DatePrecision
from services.party_affiliation import PartyOnDate, get_party_on_date

_BALLOT_PARTY = "Singapore Democratic Alliance"
_FIRST_PARTY = "Singapore People's Party"
_SECOND_PARTY = "Workers' Party"
_FIRST_START = date(2001, 1, 1)
_SECOND_START = date(2006, 6, 1)


def _build_span(
    party: str,
    started_on: date,
    precision: DatePrecision = DatePrecision.DAY,
    is_started_on_upper_bound: bool = False,
) -> PartyAffiliation:
    return PartyAffiliation(
        party=party,
        started_on=started_on,
        started_on_precision=precision,
        is_started_on_upper_bound=is_started_on_upper_bound,
        event="x",
        source_url="https://example.org",
        speaker_id=1,
    )


def test_no_spans_gives_the_ballot_party_certain() -> None:
    assert get_party_on_date(_BALLOT_PARTY, [], date(2003, 1, 1)) == PartyOnDate(
        _BALLOT_PARTY, False
    )


def test_date_on_a_span_start_takes_that_span() -> None:
    spans = [_build_span(_FIRST_PARTY, _FIRST_START)]

    assert get_party_on_date(_BALLOT_PARTY, spans, _FIRST_START) == PartyOnDate(
        _FIRST_PARTY, False
    )


def test_date_after_the_last_span_takes_the_last_span_certain() -> None:
    spans = [
        _build_span(_FIRST_PARTY, _FIRST_START),
        _build_span(_SECOND_PARTY, _SECOND_START),
    ]

    assert get_party_on_date(_BALLOT_PARTY, spans, date(2010, 1, 1)) == PartyOnDate(
        _SECOND_PARTY, False
    )


def test_date_before_an_upper_bound_next_span_is_uncertain() -> None:
    spans = [
        _build_span(_FIRST_PARTY, _FIRST_START),
        _build_span(_SECOND_PARTY, _SECOND_START, is_started_on_upper_bound=True),
    ]

    assert get_party_on_date(_BALLOT_PARTY, spans, date(2005, 1, 1)) == PartyOnDate(
        _FIRST_PARTY, True
    )


def test_date_before_a_day_precision_next_span_is_certain() -> None:
    spans = [
        _build_span(_FIRST_PARTY, _FIRST_START),
        _build_span(_SECOND_PARTY, _SECOND_START),
    ]

    assert get_party_on_date(_BALLOT_PARTY, spans, date(2005, 1, 1)) == PartyOnDate(
        _FIRST_PARTY, False
    )


def test_date_in_the_month_of_a_made_up_month_span_is_uncertain() -> None:
    spans = [
        _build_span(_FIRST_PARTY, _FIRST_START),
        _build_span(_SECOND_PARTY, _SECOND_START, precision=DatePrecision.MONTH),
    ]

    assert get_party_on_date(_BALLOT_PARTY, spans, date(2006, 5, 20)) == PartyOnDate(
        _FIRST_PARTY, False
    )
    assert get_party_on_date(_BALLOT_PARTY, spans, date(2006, 6, 20)) == PartyOnDate(
        _SECOND_PARTY, True
    )


def test_date_before_the_first_span_takes_the_ballot_party_uncertain() -> None:
    spans = [_build_span(_FIRST_PARTY, _FIRST_START)]

    assert get_party_on_date(_BALLOT_PARTY, spans, date(2000, 1, 1)) == PartyOnDate(
        _BALLOT_PARTY, True
    )


def test_upper_bound_flag_on_the_span_in_force_does_not_make_the_date_uncertain() -> (
    None
):
    spans = [
        _build_span(_FIRST_PARTY, _FIRST_START),
        _build_span(_SECOND_PARTY, _SECOND_START, is_started_on_upper_bound=True),
    ]

    assert get_party_on_date(_BALLOT_PARTY, spans, date(2010, 1, 1)) == PartyOnDate(
        _SECOND_PARTY, False
    )

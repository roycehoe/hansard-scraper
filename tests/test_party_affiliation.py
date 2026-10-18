import json
from datetime import date
from pathlib import Path
from typing import Optional

import pytest
from pydantic import ValidationError

from database.party_affiliation import PartyAffiliation
from database.speaker import Speaker
from enums import DatePrecision
from exceptions import HansardPartyAffiliationError, HansardWriteCheckError
from schemas.party_affiliation import MembershipPartyAffiliations, PartyAffiliationSpan
from services.party_affiliation import (
    build_party_affiliations,
    get_unstored_party_affiliations,
)

_DATA_FILE = Path(__file__).parent.parent / "data" / "party_affiliations.json"
_ALLIANCE = "Singapore Democratic Alliance"
_PEOPLES_PARTY = "Singapore People's Party"
_EXAMPLE_URL = "https://example.org"
_CHIAM_SPEAKER_ID = 812
_SOURCE_REPORT_ID = 4321


def _get_speaker(speaker_id: int, name: str, parliament_number: int, party: str) -> Speaker:
    return Speaker(id=speaker_id, name=name, party=party, is_legislative_assembly=False, parliament_number=parliament_number)


def _get_span(
    party: str,
    started_on: str,
    started_on_precision: str = "DAY",
    is_started_on_upper_bound: bool = False,
    source_url: Optional[str] = _EXAMPLE_URL,
    source_report_id: Optional[int] = None,
) -> dict[str, object]:
    span: dict[str, object] = {
        "party": party,
        "started_on": started_on,
        "started_on_precision": started_on_precision,
        "event": "An event.",
        "is_started_on_upper_bound": is_started_on_upper_bound,
    }
    if source_url is not None:
        span["source_url"] = source_url
    if source_report_id is not None:
        span["source_report_id"] = source_report_id
    return span


def _get_membership(*spans: dict[str, object], name: str = "Chiam See Tong", parliament_number: int = 11) -> MembershipPartyAffiliations:
    return MembershipPartyAffiliations.model_validate({"name": name, "parliament_number": parliament_number, "affiliations": list(spans)})


def _get_chiam_speakers() -> list[Speaker]:
    return [
        _get_speaker(_CHIAM_SPEAKER_ID, "Chiam See Tong", 11, _ALLIANCE),
        _get_speaker(714, "Chiam See Tong", 10, _ALLIANCE),
        _get_speaker(916, "Lina Chiam", 12, _PEOPLES_PARTY),
    ]


def _get_party_affiliation(
    party: str,
    started_on: date,
    speaker_id: int = _CHIAM_SPEAKER_ID,
    event: str = "An event.",
    is_started_on_upper_bound: bool = False,
) -> PartyAffiliation:
    return PartyAffiliation(
        party=party,
        started_on=started_on,
        started_on_precision=DatePrecision.DAY,
        event=event,
        source_url=_EXAMPLE_URL,
        is_started_on_upper_bound=is_started_on_upper_bound,
        source_report_id=None,
        speaker_id=speaker_id,
    )


def test_month_date_is_stored_as_the_first_of_the_month() -> None:
    span = PartyAffiliationSpan.model_validate(_get_span(_PEOPLES_PARTY, "2011-03", "MONTH"))

    assert span.started_on == date(2011, 3, 1)
    assert span.started_on_precision == DatePrecision.MONTH


def test_day_date_keeps_its_day() -> None:
    span = PartyAffiliationSpan.model_validate(_get_span(_ALLIANCE, "2006-05-06"))

    assert span.started_on == date(2006, 5, 6)


def test_day_precision_refuses_a_month_date() -> None:
    with pytest.raises(ValidationError):
        PartyAffiliationSpan.model_validate(_get_span(_ALLIANCE, "2011-03", "DAY"))


def test_month_precision_refuses_a_day_date() -> None:
    with pytest.raises(ValidationError):
        PartyAffiliationSpan.model_validate(_get_span(_ALLIANCE, "2011-03-05", "MONTH"))


def test_span_without_the_upper_bound_flag_is_refused() -> None:
    span = _get_span(_ALLIANCE, "2006-05-06")
    del span["is_started_on_upper_bound"]

    with pytest.raises(ValidationError):
        PartyAffiliationSpan.model_validate(span)


def test_membership_without_affiliations_is_refused() -> None:
    with pytest.raises(ValidationError):
        MembershipPartyAffiliations.model_validate({"name": "Chiam See Tong", "parliament_number": 11, "affiliations": []})


def test_table_checks_for_exactly_one_source() -> None:
    constraint_names = {constraint.name for constraint in PartyAffiliation.__table__.constraints}

    assert "ck_partyaffiliation_exactly_one_source" in constraint_names


def test_data_file_builds_chiam_two_spans() -> None:
    memberships = [
        MembershipPartyAffiliations.model_validate(record) for record in json.loads(_DATA_FILE.read_text()) if record["name"] == "Chiam See Tong"
    ]

    party_affiliations = build_party_affiliations(memberships, _get_chiam_speakers())

    assert [
        (party_affiliation.party, party_affiliation.started_on, party_affiliation.started_on_precision, party_affiliation.speaker_id)
        for party_affiliation in party_affiliations
    ] == [
        (_ALLIANCE, date(2006, 5, 6), DatePrecision.DAY, _CHIAM_SPEAKER_ID),
        (_PEOPLES_PARTY, date(2011, 3, 2), DatePrecision.DAY, _CHIAM_SPEAKER_ID),
    ]
    assert all(party_affiliation.event != "" for party_affiliation in party_affiliations)
    assert all(party_affiliation.is_started_on_upper_bound is False for party_affiliation in party_affiliations)
    assert all(party_affiliation.source_report_id is None for party_affiliation in party_affiliations)
    assert all(party_affiliation.source_url.startswith("https://") for party_affiliation in party_affiliations)


def test_data_file_names_each_membership_once() -> None:
    memberships = [MembershipPartyAffiliations.model_validate(record) for record in json.loads(_DATA_FILE.read_text())]

    keys = [(membership.name, membership.parliament_number) for membership in memberships]

    assert len(keys) == len(set(keys))


def test_two_memberships_build_their_own_rows() -> None:
    speakers = [*_get_chiam_speakers(), _get_speaker(5, "Another Member", 11, "People's Action Party")]
    memberships = [
        _get_membership(_get_span(_ALLIANCE, "2006-05-06")),
        _get_membership(_get_span("People's Action Party", "2006-05-06"), name="Another Member"),
    ]

    party_affiliations = build_party_affiliations(memberships, speakers)

    assert [party_affiliation.speaker_id for party_affiliation in party_affiliations] == [_CHIAM_SPEAKER_ID, 5]


def test_span_carries_the_upper_bound_flag_and_a_report_source() -> None:
    membership = _get_membership(
        _get_span(_ALLIANCE, "2006-05-06"),
        _get_span(_PEOPLES_PARTY, "2008-08", "MONTH", is_started_on_upper_bound=True, source_url=None, source_report_id=_SOURCE_REPORT_ID),
    )

    party_affiliations = build_party_affiliations([membership], _get_chiam_speakers())

    assert [party_affiliation.is_started_on_upper_bound for party_affiliation in party_affiliations] == [False, True]
    assert [(party_affiliation.source_url, party_affiliation.source_report_id) for party_affiliation in party_affiliations] == [
        (_EXAMPLE_URL, None),
        (None, _SOURCE_REPORT_ID),
    ]


def test_membership_with_no_speaker_row_raises() -> None:
    membership = _get_membership(_get_span(_ALLIANCE, "2006-05-06"), parliament_number=9)

    with pytest.raises(HansardPartyAffiliationError, match="No speaker row"):
        build_party_affiliations([membership], _get_chiam_speakers())


def test_membership_with_two_speaker_rows_raises() -> None:
    membership = _get_membership(_get_span(_ALLIANCE, "2006-05-06"))
    speakers = [*_get_chiam_speakers(), _get_speaker(999, "Chiam See Tong", 11, _ALLIANCE)]

    with pytest.raises(HansardPartyAffiliationError, match="2 speaker rows"):
        build_party_affiliations([membership], speakers)


def test_stored_party_missing_from_the_spans_raises() -> None:
    membership = _get_membership(_get_span("Workers' Party", "2006-05-06"), _get_span(_PEOPLES_PARTY, "2011-03-01"))

    with pytest.raises(HansardPartyAffiliationError, match="not among the spans' parties"):
        build_party_affiliations([membership], _get_chiam_speakers())


def test_stored_party_that_is_not_the_first_span_is_allowed() -> None:
    membership = _get_membership(_get_span(_PEOPLES_PARTY, "2006-05-06"), _get_span(_ALLIANCE, "2011-03-01"))

    party_affiliations = build_party_affiliations([membership], _get_chiam_speakers())

    assert [party_affiliation.party for party_affiliation in party_affiliations] == [_PEOPLES_PARTY, _ALLIANCE]


def test_spans_out_of_date_order_raise() -> None:
    membership = _get_membership(_get_span(_ALLIANCE, "2011-03-01"), _get_span(_PEOPLES_PARTY, "2006-05-06"))

    with pytest.raises(HansardPartyAffiliationError, match="not after"):
        build_party_affiliations([membership], _get_chiam_speakers())


def test_spans_on_the_same_date_raise() -> None:
    membership = _get_membership(_get_span(_ALLIANCE, "2006-05-06"), _get_span(_PEOPLES_PARTY, "2006-05-06"))

    with pytest.raises(HansardPartyAffiliationError, match="not after"):
        build_party_affiliations([membership], _get_chiam_speakers())


def test_span_without_a_source_raises() -> None:
    membership = _get_membership(_get_span(_ALLIANCE, "2006-05-06", source_url=None))

    with pytest.raises(HansardPartyAffiliationError, match="has no source"):
        build_party_affiliations([membership], _get_chiam_speakers())


def test_span_with_two_sources_raises() -> None:
    membership = _get_membership(_get_span(_ALLIANCE, "2006-05-06", source_report_id=_SOURCE_REPORT_ID))

    with pytest.raises(HansardPartyAffiliationError, match="two sources"):
        build_party_affiliations([membership], _get_chiam_speakers())


def test_two_consecutive_spans_with_the_same_party_are_allowed() -> None:
    membership = _get_membership(_get_span(_ALLIANCE, "2006-05-06"), _get_span(_ALLIANCE, "2011-03-01"))

    party_affiliations = build_party_affiliations([membership], _get_chiam_speakers())

    assert [party_affiliation.party for party_affiliation in party_affiliations] == [_ALLIANCE, _ALLIANCE]


def test_same_party_in_non_consecutive_spans_is_allowed() -> None:
    membership = _get_membership(
        _get_span(_ALLIANCE, "2006-05-06"),
        _get_span(_PEOPLES_PARTY, "2008-01-01"),
        _get_span(_ALLIANCE, "2011-03-01"),
    )

    party_affiliations = build_party_affiliations([membership], _get_chiam_speakers())

    assert [party_affiliation.party for party_affiliation in party_affiliations] == [_ALLIANCE, _PEOPLES_PARTY, _ALLIANCE]


def test_nothing_stored_inserts_every_planned_row() -> None:
    planned = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6)), _get_party_affiliation(_PEOPLES_PARTY, date(2011, 3, 1))]

    assert get_unstored_party_affiliations(planned, []) == planned


def test_stored_rows_that_equal_planned_rows_are_skipped() -> None:
    planned = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6)), _get_party_affiliation(_PEOPLES_PARTY, date(2011, 3, 1))]
    stored = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6))]
    stored[0].id = 1

    assert get_unstored_party_affiliations(planned, stored) == [planned[1]]


def test_everything_stored_leaves_nothing_to_insert() -> None:
    planned = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6))]
    stored = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6))]
    stored[0].id = 1

    assert get_unstored_party_affiliations(planned, stored) == []


def test_stored_row_that_differs_from_the_planned_row_raises() -> None:
    planned = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6), event="The new sentence.")]
    stored = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6), event="The old sentence.")]

    with pytest.raises(HansardWriteCheckError, match="Speaker 812"):
        get_unstored_party_affiliations(planned, stored)


def test_stored_row_with_a_different_upper_bound_flag_raises() -> None:
    planned = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6), is_started_on_upper_bound=True)]
    stored = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6), is_started_on_upper_bound=False)]

    with pytest.raises(HansardWriteCheckError, match="Speaker 812"):
        get_unstored_party_affiliations(planned, stored)


def test_stored_row_the_file_no_longer_holds_raises() -> None:
    planned = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6))]
    stored = [_get_party_affiliation(_ALLIANCE, date(2006, 5, 6)), _get_party_affiliation(_PEOPLES_PARTY, date(2011, 3, 1))]

    with pytest.raises(HansardWriteCheckError, match="does not"):
        get_unstored_party_affiliations(planned, stored)

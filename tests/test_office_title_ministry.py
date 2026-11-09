from typing import Optional

import pytest

from enums import OfficeTitleMinistrySource
from services.office_title_ministry import (
    OfficeTitlePlacement,
    get_office_title_placement,
)
from utils.data_files import get_ministry_names

_PRIME_MINISTERS_OFFICE = "Prime Minister's Office"
_PRIME_MINISTERS_DEPARTMENT = "Prime Minister's Department"
_TITLE_TO_MINISTRY_NAMES = {"Prime Minister": [_PRIME_MINISTERS_OFFICE]}
_RULE = OfficeTitleMinistrySource.CLOSED_LIST_RULE
_HAND_KEPT = OfficeTitleMinistrySource.HAND_KEPT_TITLE


def _get_placement(office_printed: str) -> Optional[list[OfficeTitlePlacement]]:
    return get_office_title_placement(
        office_printed,
        sorted(get_ministry_names(), key=len, reverse=True),
        _TITLE_TO_MINISTRY_NAMES,
    )


def _rule(*ministry_names: str) -> list[OfficeTitlePlacement]:
    return [OfficeTitlePlacement(name, _RULE) for name in ministry_names]


@pytest.mark.parametrize(
    ("office_printed", "placements"),
    [
        pytest.param("Minister for Finance", _rule("Finance"), id="head_for_name"),
        pytest.param(
            "Second Minister for Defence (Policy)",
            _rule("Defence"),
            id="rank_word_and_bracket_removed",
        ),
        pytest.param(
            "Minister, Prime Minister's Office",
            _rule(_PRIME_MINISTERS_OFFICE),
            id="role_clause_then_closed_list_name",
        ),
        pytest.param(
            "Prime Minister",
            [OfficeTitlePlacement(_PRIME_MINISTERS_OFFICE, _HAND_KEPT)],
            id="hand_kept_title",
        ),
        pytest.param(
            "Acting Prime Minister",
            [OfficeTitlePlacement(_PRIME_MINISTERS_OFFICE, _HAND_KEPT)],
            id="hand_kept_title_after_rank_word",
        ),
        pytest.param(
            "Prime Minister and Minister for Defence",
            [
                OfficeTitlePlacement(_PRIME_MINISTERS_OFFICE, _HAND_KEPT),
                OfficeTitlePlacement("Defence", _RULE),
            ],
            id="hand_kept_clause_then_rule",
        ),
        pytest.param(
            "Minister in the Prime Minister's Department",
            _rule(_PRIME_MINISTERS_DEPARTMENT),
            id="prefix_accepts_in",
        ),
        pytest.param("Deputy Prime Minister", [], id="role_only"),
        pytest.param(
            "Deputy Prime Minister and Leader of the House", [], id="two_role_clauses"
        ),
        pytest.param("The Honourable Mr SPEAKER", [], id="chair_form"),
        pytest.param("Chief Secretary (Acting)", [], id="role_only_with_bracket"),
        pytest.param(
            "Senior Parliamentary Secretary to the Prime Minister",
            [],
            id="role_only_after_rank_word",
        ),
        pytest.param(
            "Minister for Culture, Community and Youth",
            _rule("Culture, Community and Youth"),
            id="comma_inside_a_name",
        ),
        pytest.param(
            "Minister for Sustainability and the Environment",
            _rule("Sustainability and the Environment"),
            id="and_the_inside_a_name",
        ),
        pytest.param(
            "Minister for Law and National Development",
            _rule("Law", "National Development"),
            id="two_names_after_one_head",
        ),
        pytest.param(
            "Minister of State, Ministry of Finance and Ministry of Communications",
            _rule("Finance", "Communications"),
            id="two_ministry_clauses",
        ),
        pytest.param(
            "Minister for Finance, Minister for Health and Minister for Education",
            _rule("Finance", "Health", "Education"),
            id="three_clauses",
        ),
        pytest.param(
            "Minister for Manpower and Second Minister for Trade and Industry",
            _rule("Manpower", "Trade and Industry"),
            id="second_minister_clause",
        ),
        pytest.param(
            "Minister-in-charge of Muslim Affairs",
            _rule("Muslim Affairs"),
            id="minister_in_charge",
        ),
        pytest.param(
            "Senior Parliamentary Secretary to the Minister of Defence",
            _rule("Defence"),
            id="parliamentary_secretary_to_the_minister_of",
        ),
        pytest.param(
            "Coordinating Minister for National Security",
            _rule("National Security"),
            id="coordinating_minister",
        ),
        pytest.param("Senior Minister", [], id="senior_minister_is_role_only"),
        pytest.param(
            "Senior Minister of State for Finance",
            _rule("Finance"),
            id="senior_minister_of_state_for_a_name",
        ),
        pytest.param("Minister for Nonsense", None, id="unknown_name"),
        pytest.param(
            "Minister for Finance and Minister for Nonsense",
            None,
            id="one_unknown_clause_leaves_the_title_unplaced",
        ),
        pytest.param("(Anson)", None, id="bracket_only"),
        pytest.param(";", None, id="punctuation_only"),
    ],
)
def test_title_placement(
    office_printed: str, placements: Optional[list[OfficeTitlePlacement]]
) -> None:
    assert _get_placement(office_printed) == placements


def test_an_exact_hand_kept_title_places_before_any_clause_is_read() -> None:
    placements = get_office_title_placement(
        "The  Minister of State.  Prime Minister's Office",
        sorted(get_ministry_names(), key=len, reverse=True),
        {"Minister of State. Prime Minister's Office": [_PRIME_MINISTERS_OFFICE]},
    )

    assert placements == [OfficeTitlePlacement(_PRIME_MINISTERS_OFFICE, _HAND_KEPT)]


def test_an_empty_hand_kept_entry_places_the_title_with_no_ministry() -> None:
    placements = get_office_title_placement(
        "(Anson)", sorted(get_ministry_names(), key=len, reverse=True), {"(Anson)": []}
    )

    assert placements == []

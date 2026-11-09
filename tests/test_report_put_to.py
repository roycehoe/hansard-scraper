from typing import Optional

import pytest

from crud.speech import SpeechAskerRow
from enums import ReportPutToSource
from services.report_put_to import PutToPhrase, get_put_to_phrases

_ORDINAL = 3
_ASTERISK_TRANSCRIPT = "asked the *Chief Secretary whether"
_NO_HEAD_TRANSCRIPT = "asked the question why"
_TWO_OPENINGS_TRANSCRIPT = "asked the Minister for Health about the Minister for Law"
_HEALTH_TRANSCRIPT = "asked the Minister for Health if"
_DEFENCE_TRANSCRIPT = "To ask the Minister for Defence for details"


def _build_row(ordinal: int, transcript: str) -> SpeechAskerRow:
    return SpeechAskerRow(
        id=ordinal,
        report_id=1,
        ordinal=ordinal,
        speaker=None,
        transcript=transcript,
        kind=None,
        speaker_id=None,
    )


def _get_single_phrase(transcript: str) -> Optional[PutToPhrase]:
    phrases = get_put_to_phrases(
        [_build_row(_ORDINAL, transcript)], frozenset({_ORDINAL})
    )
    return phrases[0] if phrases else None


@pytest.mark.parametrize(
    ("transcript", "office_printed", "source"),
    [
        pytest.param(
            "asked the Minister for National Development (a) how",
            "Minister for National Development",
            ReportPutToSource.ASKED_THE,
            id="head_for_name_then_lowercase",
        ),
        pytest.param(
            "To ask the Minister for National Development for HDB flats",
            "Minister for National Development",
            ReportPutToSource.TO_ASK_THE,
            id="to_ask_the_stops_before_for",
        ),
        pytest.param(
            "asked the Minister for Education (Schools) what",
            "Minister for Education (Schools)",
            ReportPutToSource.ASKED_THE,
            id="capitalised_bracket_stays",
        ),
        pytest.param(
            "asked the Minister for Information and the Arts whether",
            "Minister for Information and the Arts",
            ReportPutToSource.ASKED_THE,
            id="and_the_inside_a_name",
        ),
        pytest.param(
            "asked the Minister for the Environment whether",
            "Minister for the Environment",
            ReportPutToSource.ASKED_THE,
            id="the_after_for",
        ),
        pytest.param(
            "asked the Minister for Culture, Community and Youth if",
            "Minister for Culture, Community and Youth",
            ReportPutToSource.ASKED_THE,
            id="comma_inside_a_name",
        ),
        pytest.param(
            "asked the Prime Minister and Minister for Finance whether",
            "Prime Minister and Minister for Finance",
            ReportPutToSource.ASKED_THE,
            id="two_heads_joined_by_and",
        ),
        pytest.param(
            "asked the Minister-in-charge of Muslim Affairs, in the last",
            "Minister-in-charge of Muslim Affairs",
            ReportPutToSource.ASKED_THE,
            id="comma_then_lowercase_ends_the_title",
        ),
        pytest.param(
            "asked the Acting Minister-in-charge of Muslim Affairs if",
            "Acting Minister-in-charge of Muslim Affairs",
            ReportPutToSource.ASKED_THE,
            id="acting_minister_in_charge",
        ),
        pytest.param(
            "asked the Deputy Prime Minister and Leader of the House if",
            "Deputy Prime Minister and Leader of the House",
            ReportPutToSource.ASKED_THE,
            id="deputy_prime_minister_and_leader_of_the_house",
        ),
        pytest.param(
            "asked the Minister or Health whether",
            "Minister or Health",
            ReportPutToSource.ASKED_THE,
            id="misprinted_for",
        ),
        pytest.param(
            "asked the Minster for Labour if",
            "Minster for Labour",
            ReportPutToSource.ASKED_THE,
            id="misprinted_head",
        ),
        pytest.param(
            "asked the Minister for Education- what",
            "Minister for Education",
            ReportPutToSource.ASKED_THE,
            id="hyphen_before_a_space",
        ),
        pytest.param(
            "asked the Minister for Health the cost",
            "Minister for Health",
            ReportPutToSource.ASKED_THE,
            id="the_before_lowercase",
        ),
        pytest.param(
            "asked the Minister whether",
            "Minister",
            ReportPutToSource.ASKED_THE,
            id="bare_minister",
        ),
    ],
)
def test_office_is_read_up_to_where_the_title_ends(
    transcript: str, office_printed: str, source: ReportPutToSource
) -> None:
    phrase = _get_single_phrase(transcript)

    assert phrase is not None
    assert phrase.office_printed == office_printed
    assert phrase.source == source
    assert phrase.first_ordinal == _ORDINAL


def test_a_leading_asterisk_stays_in_the_printed_text_and_out_of_the_office() -> None:
    phrase = _get_single_phrase(_ASTERISK_TRANSCRIPT)

    assert phrase == PutToPhrase(
        "Chief Secretary",
        "asked the *Chief Secretary",
        ReportPutToSource.ASKED_THE,
        _ORDINAL,
    )


def test_an_opening_with_no_office_head_gives_none() -> None:
    assert _get_single_phrase(_NO_HEAD_TRANSCRIPT) is None


def test_only_the_first_opening_of_a_row_is_read() -> None:
    phrase = _get_single_phrase(_TWO_OPENINGS_TRANSCRIPT)

    assert phrase is not None
    assert phrase.office_printed == "Minister for Health"
    assert (
        len(
            get_put_to_phrases(
                [_build_row(_ORDINAL, _TWO_OPENINGS_TRANSCRIPT)],
                frozenset({_ORDINAL}),
            )
        )
        == 1
    )


def test_a_row_outside_the_question_rows_gives_none() -> None:
    phrases = get_put_to_phrases(
        [_build_row(_ORDINAL, _HEALTH_TRANSCRIPT)], frozenset({_ORDINAL + 1})
    )

    assert phrases == []


def test_two_rows_with_one_phrase_give_one_record_at_the_first_ordinal() -> None:
    phrases = get_put_to_phrases(
        [_build_row(2, _HEALTH_TRANSCRIPT), _build_row(5, _HEALTH_TRANSCRIPT)],
        frozenset({2, 5}),
    )

    assert [(phrase.office_printed, phrase.first_ordinal) for phrase in phrases] == [
        ("Minister for Health", 2)
    ]


def test_two_rows_with_two_phrases_give_two_records_in_order() -> None:
    phrases = get_put_to_phrases(
        [_build_row(2, _HEALTH_TRANSCRIPT), _build_row(5, _DEFENCE_TRANSCRIPT)],
        frozenset({2, 5}),
    )

    assert [
        (phrase.office_printed, phrase.source, phrase.first_ordinal)
        for phrase in phrases
    ] == [
        ("Minister for Health", ReportPutToSource.ASKED_THE, 2),
        ("Minister for Defence", ReportPutToSource.TO_ASK_THE, 5),
    ]

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
        pytest.param(
            "asked Minister for Education (a) what",
            "Minister for Education",
            ReportPutToSource.MISPRINTED_OPENING,
            id="opening_with_no_the_report_9060",
        ),
        pytest.param(
            "14 To ask Minister for Culture, Community and Youth (a) whether",
            "Minister for Culture, Community and Youth",
            ReportPutToSource.MISPRINTED_OPENING,
            id="to_ask_with_no_the_report_12035",
        ),
        pytest.param(
            "asked Deputy Prime Minister and Minister for Home Affairs whether",
            "Deputy Prime Minister and Minister for Home Affairs",
            ReportPutToSource.MISPRINTED_OPENING,
            id="no_the_before_a_longer_head_report_19714",
        ),
        pytest.param(
            "asked the the Prime Minister when",
            "Prime Minister",
            ReportPutToSource.MISPRINTED_OPENING,
            id="the_printed_twice_report_33683",
        ),
        pytest.param(
            "asked the, Minister for Labour what",
            "Minister for Labour",
            ReportPutToSource.MISPRINTED_OPENING,
            id="the_with_a_comma_report_38845",
        ),
        pytest.param(
            "asked The Minister for Foreign Affairs and Minister for Labour the total",
            "Minister for Foreign Affairs and Minister for Labour",
            ReportPutToSource.MISPRINTED_OPENING,
            id="capital_the_report_37059",
        ),
        pytest.param(
            "asked he Minister for the Environment and Water Resources if",
            "Minister for the Environment and Water Resources",
            ReportPutToSource.MISPRINTED_OPENING,
            id="he_for_the_report_18022",
        ),
        pytest.param(
            "asked the asked the Minister for Transport (a) what",
            "Minister for Transport",
            ReportPutToSource.MISPRINTED_OPENING,
            id="verb_printed_twice_report_20481",
        ),
        pytest.param(
            "asked (Mr Lim Koon Teck not being present to rise and ask his question) the Chief Secretary whether",
            "Chief Secretary",
            ReportPutToSource.MISPRINTED_OPENING,
            id="bracket_before_the_report_40396",
        ),
        pytest.param(
            "asked the Acting minister for Social Affairs (a) if",
            "Acting minister for Social Affairs",
            ReportPutToSource.ASKED_THE,
            id="lower_case_minister_report_33258",
        ),
        pytest.param(
            "asked the Minister for Information, Communications and the Arts & Minister-in-charge of Muslim Affairs (a) what",
            "Minister for Information, Communications and the Arts & Minister-in-charge of Muslim Affairs",
            ReportPutToSource.ASKED_THE,
            id="ampersand_joins_two_offices",
        ),
        pytest.param(
            "asked the Minister for Trade and lndustry and Minister for Education what",
            "Minister for Trade and lndustry and Minister for Education",
            ReportPutToSource.ASKED_THE,
            id="misprinted_title_lndustry",
        ),
        pytest.param(
            "asked the Minister for Trade and industry and Minister for Education what",
            "Minister for Trade and industry and Minister for Education",
            ReportPutToSource.ASKED_THE,
            id="misprinted_title_lower_case_industry",
        ),
        pytest.param(
            "asked the Minister for Trade and Industry and Minister f6r Health whether",
            "Minister for Trade and Industry and Minister f6r Health",
            ReportPutToSource.ASKED_THE,
            id="misprinted_title_f6r",
        ),
        pytest.param(
            "asked the Acting Minister for Community Develop- ment how",
            "Acting Minister for Community Develop- ment",
            ReportPutToSource.ASKED_THE,
            id="misprinted_title_broken_word",
        ),
        pytest.param(
            "To ask the Minister for National development (a) how",
            "Minister for National development",
            ReportPutToSource.TO_ASK_THE,
            id="misprinted_title_lower_case_development",
        ),
        pytest.param(
            "asked the Minister for labour and law what",
            "Minister for labour and law",
            ReportPutToSource.ASKED_THE,
            id="misprinted_title_lower_case_labour_and_law",
        ),
        pytest.param(
            "asked the Minister for transport whether",
            "Minister for transport",
            ReportPutToSource.ASKED_THE,
            id="misprinted_title_lower_case_transport",
        ),
        pytest.param(
            "asked the Minister forCommunications if",
            "Minister forCommunications",
            ReportPutToSource.ASKED_THE,
            id="misprinted_title_glued_for",
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


@pytest.mark.parametrize(
    "transcript",
    [
        pytest.param(
            "asked Mr Ong Teng Cheong, Minister without portfolio, what",
            id="a_named_person",
        ),
        pytest.param(
            "asked whether the decision not to publish",
            id="no_addressee_report_19540",
        ),
        pytest.param(
            "asked the the present shortage of parking lots",
            id="the_printed_twice_with_no_head_report_42236",
        ),
    ],
)
def test_a_misprinted_opening_with_no_office_head_gives_no_phrase(
    transcript: str,
) -> None:
    assert _get_single_phrase(transcript) is None


def test_a_later_ask_does_not_stand_in_for_a_misprinted_opening() -> None:
    assert (
        _get_single_phrase(
            "asked whether he will ask Minister for Health about the waiting times"
        )
        is None
    )


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

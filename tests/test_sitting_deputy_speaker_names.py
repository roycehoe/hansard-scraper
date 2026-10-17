import json

from crud.speech import SpeechRow
from services.role_context import (
    build_sitting_text_from_markdown,
    build_sitting_text_from_sections,
    sitting_deputy_speaker_names,
)

_REPORT_ID = 1
_REPORT_TITLE = "Employment (Amendment) Bill"
_BRACKET = "**[Deputy Speaker (Mr Lim Biow Chuan) in the Chair]**"
_MEMBER_SPEECH = "**Mr Gan Thiam Poh (Ang Mo Kio)** : I rise in support of the Bill before the House today."
_CALL = "**Mr Deputy Speaker** : Mr Leon Perera, please proceed with your speech."
_SPEECH_ROWS = [
    SpeechRow(1, 1, "Mr Gan Thiam Poh (Ang Mo Kio)", "I rise in support of the Bill before the House today.", _REPORT_ID, 10),
    SpeechRow(2, 2, "Mr Deputy Speaker", "Mr Leon Perera, please proceed with your speech.", _REPORT_ID, None),
]


def _get_names(markdown: str) -> dict[int, str]:
    return sitting_deputy_speaker_names(build_sitting_text_from_markdown(markdown), _REPORT_TITLE, _SPEECH_ROWS)


def test_bare_deputy_row_takes_the_deputy_named_by_the_last_bracket() -> None:
    names = _get_names("\n\n".join((_BRACKET, _MEMBER_SPEECH, _CALL)))

    assert names == {2: "Mr Lim Biow Chuan"}


def test_bare_deputy_row_with_no_bracket_before_it_gets_no_name() -> None:
    names = _get_names("\n\n".join((_MEMBER_SPEECH, _CALL, _BRACKET)))

    assert names == {}


def test_speaker_chair_label_after_the_bracket_voids_it() -> None:
    names = _get_names("\n\n".join((_BRACKET, "**Mr Speaker** : Mr Gan Thiam Poh.", _MEMBER_SPEECH, _CALL)))

    assert names == {}


def test_unnamed_chair_change_after_the_bracket_voids_it() -> None:
    names = _get_names("\n\n".join((_BRACKET, "Thereupon Mr Deputy Speaker left the Chair.", _MEMBER_SPEECH, _CALL)))

    assert names == {}


def test_suspension_after_the_bracket_voids_it() -> None:
    names = _get_names("\n\n".join((_BRACKET, "Sitting suspended at 1.30 pm until 2.30 pm.", _MEMBER_SPEECH, _CALL)))

    assert names == {}


def test_deputy_speaking_as_a_member_after_the_bracket_voids_it() -> None:
    names = _get_names("\n\n".join((_BRACKET, "**Mr Lim Biow Chuan (Mountbatten)** : I have a short question for the Minister.", _MEMBER_SPEECH, _CALL)))

    assert names == {}


def test_next_bracket_naming_the_same_deputy_voids_it() -> None:
    names = _get_names("\n\n".join((_BRACKET, _MEMBER_SPEECH, _CALL, _BRACKET)))

    assert names == {}


def test_bracket_in_an_earlier_section_carries_into_the_report() -> None:
    sections = json.dumps([
        {"title": "Public Sector (Governance) Bill", "content": "<p><strong>[Deputy Speaker (Mr Lim Biow Chuan) in the Chair]</strong></p><p><strong>Mr Ong Ye Kung</strong>: I beg to move.</p>"},
        {"title": _REPORT_TITLE, "content": "<p><strong>Mr Gan Thiam Poh (Ang Mo Kio)</strong>: I rise in support of the Bill before the House today.</p><p><strong>Mr Deputy Speaker</strong>: Mr Leon Perera, please proceed with your speech.</p>"},
    ])

    names = sitting_deputy_speaker_names(build_sitting_text_from_sections(sections), _REPORT_TITLE, _SPEECH_ROWS)

    assert names == {2: "Mr Lim Biow Chuan"}

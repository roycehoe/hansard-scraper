from crud.speech import SpeechRow
from services.role_context import chairman_names

_REPORT_ID = 1
_DIVISION_CALL = "Will the hon Members in support of the Division, please rise in their places?"
_BELLS = "Clerk, ring the Division bells."
_LOCK = "Serjeant-at-Arms, lock the doors."
_SPEECH_ROWS = [
    SpeechRow(1, 1, "Mr Deputy Speaker", _DIVISION_CALL, _REPORT_ID, None),
    SpeechRow(2, 2, "The Chairman", _BELLS, _REPORT_ID, None),
    SpeechRow(3, 3, "The Chairman", _LOCK, _REPORT_ID, None),
]
_HEADERLESS_MARKDOWN = "\n".join((
    f"**Mr Deputy Speaker** : {_DIVISION_CALL}",
    "**[Mr Speaker in the Chair]**",
    f"**The Chairman** : {_BELLS}",
    f"**The Chairman** : {_LOCK}",
))


def test_chairman_under_a_speaker_annotation_in_a_report_with_no_header_takes_the_annotation() -> None:
    names = chairman_names(_HEADERLESS_MARKDOWN, _SPEECH_ROWS)

    assert names == {2: "Mr Speaker", 3: "Mr Speaker"}


def test_chair_change_line_after_the_speaker_annotation_voids_it() -> None:
    markdown = _HEADERLESS_MARKDOWN.replace("**[Mr Speaker in the Chair]**", "**[Mr Speaker in the Chair]**\nThereupon Mr Speaker left the Chair.")

    names = chairman_names(markdown, _SPEECH_ROWS)

    assert names == {}


def test_chairman_under_a_speaker_annotation_in_a_report_whose_header_names_no_speaker_stays_unnamed() -> None:
    markdown = "|MPs Speaking:|Mr Pritam Singh|\n" + _HEADERLESS_MARKDOWN

    names = chairman_names(markdown, _SPEECH_ROWS)

    assert names == {}

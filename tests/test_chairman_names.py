from crud.speech import SpeechRow
from services.speaker_link import get_chairman_names

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
    names = get_chairman_names(_HEADERLESS_MARKDOWN, _SPEECH_ROWS)

    assert names == {2: "Mr Speaker", 3: "Mr Speaker"}


def test_chair_change_line_after_the_speaker_annotation_voids_it() -> None:
    markdown = _HEADERLESS_MARKDOWN.replace("**[Mr Speaker in the Chair]**", "**[Mr Speaker in the Chair]**\nThereupon Mr Speaker left the Chair.")

    names = get_chairman_names(markdown, _SPEECH_ROWS)

    assert names == {}


def test_chairman_under_a_speaker_annotation_in_a_report_whose_header_names_no_speaker_stays_unnamed() -> None:
    markdown = "|MPs Speaking:|Mr Pritam Singh|\n" + _HEADERLESS_MARKDOWN

    names = get_chairman_names(markdown, _SPEECH_ROWS)

    assert names == {}


_RULING = "I am introducing the following ruling on the time allowed for amendments."
_NEXT_HEAD = "I shall deal first with the heads of expenditure in respect of which amendments stand."
_CHAIRMAN_ROWS = [
    SpeechRow(1, 1, "The Chairman", _RULING, _REPORT_ID, None),
    SpeechRow(2, 2, "The Chairman", _NEXT_HEAD, _REPORT_ID, None),
]
_SPEAKER_HEADER_MARKDOWN = "\n".join((
    "|MPs Speaking:| Dr Yeoh Ghim Seng (Mr Speaker);  ",
    "#### [Mr Speaker in the Chair]",
    f"**The Chairman:** {_RULING}",
    f"**The Chairman:** {_NEXT_HEAD}",
))


def test_chairman_under_a_speaker_annotation_takes_the_one_speaker_the_header_tags() -> None:
    names = get_chairman_names(_SPEAKER_HEADER_MARKDOWN, _CHAIRMAN_ROWS)

    assert names == {1: "Yeoh Ghim Seng", 2: "Yeoh Ghim Seng"}


def test_deputy_speaker_named_in_the_report_keeps_the_chairman_unnamed() -> None:
    markdown = _SPEAKER_HEADER_MARKDOWN + "\nThereupon Mr Deputy Speaker left the Chair of the Committee."

    names = get_chairman_names(markdown, _CHAIRMAN_ROWS)

    assert names == {}


def test_suspension_between_the_annotation_and_the_row_keeps_the_chairman_unnamed() -> None:
    markdown = _SPEAKER_HEADER_MARKDOWN.replace(f"**The Chairman:** {_NEXT_HEAD}", f"_Sitting resumed at 2.30 p.m._\n**The Chairman:** {_NEXT_HEAD}")

    names = get_chairman_names(markdown, _CHAIRMAN_ROWS)

    assert names == {1: "Yeoh Ghim Seng"}

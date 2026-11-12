import pytest

from enums import SpeechKind
from exceptions import HansardUnlabelledSpeechError
from schemas.unlabelled_speech import UnlabelledSpeechRange
from services.speech import ParsedSpeech, apply_unlabelled_speech_range
from utils.data_files import get_unlabelled_speech_ranges

_CHAIR = "Mr Speaker"
_MINISTER = "The Minister for Manpower (Dr Tan See Leng)"
_CREDITED_NAME = "Tan See Leng"
_OPENING_SPEECH_REPORT_ID = 24248
_OPENING_SPEECH_CREDITED_NAME = "Gan Kim Yong"
_NOTICE_OF_MOTION_REPORT_ID = 42017


def _build_chair_resumption() -> list[ParsedSpeech]:
    return [
        ParsedSpeech(
            speaker=_MINISTER,
            transcript="May I display some slides on the LED screens?",
            kind=SpeechKind.SPEECH,
        ),
        ParsedSpeech(speaker=_CHAIR, transcript="Yes, please.", kind=SpeechKind.SPEECH),
        ParsedSpeech(
            speaker=None,
            transcript="[_Slides were shown to hon Members._]",
            kind=SpeechKind.CHAMBER_EVENT,
        ),
        ParsedSpeech(
            speaker=_CHAIR,
            transcript="First, look at the local PMET employment.",
            kind=SpeechKind.SPEECH,
        ),
        ParsedSpeech(
            speaker=None, transcript="[_Applause._]", kind=SpeechKind.CHAMBER_EVENT
        ),
        ParsedSpeech(
            speaker=_CHAIR,
            transcript="The Motion acknowledges our anxieties.",
            kind=SpeechKind.SPEECH,
        ),
        ParsedSpeech(
            speaker=_CHAIR, transcript="Mr Leong Mun Wai.", kind=SpeechKind.SPEECH
        ),
    ]


def test_rows_in_the_range_lose_the_wrong_label() -> None:
    speech_range = UnlabelledSpeechRange(
        report_id=8732,
        speaker=_CHAIR,
        credited_speaker_name=_CREDITED_NAME,
        first_transcript_start="First, look",
        last_transcript_start="The Motion",
        reason="",
    )

    parsed_speeches = apply_unlabelled_speech_range(
        _build_chair_resumption(), speech_range
    )

    assert [
        [parsed_speech.speaker, parsed_speech.kind] for parsed_speech in parsed_speeches
    ] == [
        [_MINISTER, SpeechKind.SPEECH],
        [_CHAIR, SpeechKind.SPEECH],
        [None, SpeechKind.CHAMBER_EVENT],
        [None, SpeechKind.SPEECH],
        [None, SpeechKind.CHAMBER_EVENT],
        [None, SpeechKind.SPEECH],
        [_CHAIR, SpeechKind.SPEECH],
    ]


def test_unclassified_rows_before_the_first_speaker_become_speech() -> None:
    speeches = [
        ParsedSpeech(
            speaker=None,
            transcript="Mr Speaker, Sir, I beg to move,",
            kind=SpeechKind.UNCLASSIFIED,
        ),
        ParsedSpeech(
            speaker=None, transcript="Sir, I beg to move.", kind=SpeechKind.UNCLASSIFIED
        ),
        ParsedSpeech(
            speaker=None, transcript="Question proposed.", kind=SpeechKind.PROCEDURAL
        ),
    ]
    speech_range = UnlabelledSpeechRange(
        report_id=24248,
        speaker=None,
        credited_speaker_name=_CREDITED_NAME,
        first_transcript_start="Mr Speaker, Sir",
        last_transcript_start="Sir, I beg",
        reason="",
    )

    parsed_speeches = apply_unlabelled_speech_range(speeches, speech_range)

    assert [
        [parsed_speech.speaker, parsed_speech.kind] for parsed_speech in parsed_speeches
    ] == [
        [None, SpeechKind.SPEECH],
        [None, SpeechKind.SPEECH],
        [None, SpeechKind.PROCEDURAL],
    ]


def test_a_range_the_parse_no_longer_holds_raises() -> None:
    speech_range = UnlabelledSpeechRange(
        report_id=8732,
        speaker=_CHAIR,
        credited_speaker_name=_CREDITED_NAME,
        first_transcript_start="Second, look",
        last_transcript_start="The Motion",
        reason="",
    )

    with pytest.raises(HansardUnlabelledSpeechError):
        apply_unlabelled_speech_range(_build_chair_resumption(), speech_range)


def test_the_data_file_holds_one_range_per_report() -> None:
    speech_ranges = get_unlabelled_speech_ranges()

    assert len({speech_range.report_id for speech_range in speech_ranges}) == len(
        speech_ranges
    )


def test_the_data_file_credits_the_opening_speech_of_24248_and_leaves_42017_out() -> (
    None
):
    report_id_to_credited_name = {
        speech_range.report_id: speech_range.credited_speaker_name
        for speech_range in get_unlabelled_speech_ranges()
    }

    assert (
        report_id_to_credited_name[_OPENING_SPEECH_REPORT_ID]
        == _OPENING_SPEECH_CREDITED_NAME
    )
    assert _NOTICE_OF_MOTION_REPORT_ID not in report_id_to_credited_name

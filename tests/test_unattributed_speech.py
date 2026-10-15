import json
from pathlib import Path

import pytest

from enums import SpeechKind
from exceptions import HansardUnattributedSpeechError
from schemas.unattributed_speech import UnattributedSpeechRange
from services.speech import ParsedSpeech, apply_unattributed_speech_range

_DATA_FILE = Path(__file__).parent.parent / "data" / "unattributed_speech.json"
_CHAIR = "Mr Speaker"
_MINISTER = "The Minister for Manpower (Dr Tan See Leng)"


def _build_chair_resumption() -> list[ParsedSpeech]:
    return [
        ParsedSpeech(speaker=_MINISTER, transcript="May I display some slides on the LED screens?", kind=SpeechKind.SPEECH),
        ParsedSpeech(speaker=_CHAIR, transcript="Yes, please.", kind=SpeechKind.SPEECH),
        ParsedSpeech(speaker=None, transcript="[_Slides were shown to hon Members._]", kind=SpeechKind.CHAMBER_EVENT),
        ParsedSpeech(speaker=_CHAIR, transcript="First, look at the local PMET employment.", kind=SpeechKind.SPEECH),
        ParsedSpeech(speaker=None, transcript="[_Applause._]", kind=SpeechKind.CHAMBER_EVENT),
        ParsedSpeech(speaker=_CHAIR, transcript="The Motion acknowledges our anxieties.", kind=SpeechKind.SPEECH),
        ParsedSpeech(speaker=_CHAIR, transcript="Mr Leong Mun Wai.", kind=SpeechKind.SPEECH),
    ]


def test_rows_in_the_range_lose_the_wrong_label() -> None:
    speech_range = UnattributedSpeechRange(
        report_id=8732, speaker=_CHAIR, first_transcript_start="First, look", last_transcript_start="The Motion", reason="",
    )

    rows = apply_unattributed_speech_range(_build_chair_resumption(), speech_range)

    assert [[row.speaker, row.kind] for row in rows] == [
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
        ParsedSpeech(speaker=None, transcript="Mr Speaker, Sir, I beg to move,", kind=SpeechKind.UNCLASSIFIED),
        ParsedSpeech(speaker=None, transcript="Sir, I beg to move.", kind=SpeechKind.UNCLASSIFIED),
        ParsedSpeech(speaker=None, transcript="Question proposed.", kind=SpeechKind.PROCEDURAL),
    ]
    speech_range = UnattributedSpeechRange(
        report_id=24248, speaker=None, first_transcript_start="Mr Speaker, Sir", last_transcript_start="Sir, I beg", reason="",
    )

    rows = apply_unattributed_speech_range(speeches, speech_range)

    assert [[row.speaker, row.kind] for row in rows] == [
        [None, SpeechKind.SPEECH],
        [None, SpeechKind.SPEECH],
        [None, SpeechKind.PROCEDURAL],
    ]


def test_a_range_the_parse_no_longer_holds_raises() -> None:
    speech_range = UnattributedSpeechRange(
        report_id=8732, speaker=_CHAIR, first_transcript_start="Second, look", last_transcript_start="The Motion", reason="",
    )

    with pytest.raises(HansardUnattributedSpeechError):
        apply_unattributed_speech_range(_build_chair_resumption(), speech_range)


def test_the_data_file_holds_one_range_per_report() -> None:
    speech_ranges = [UnattributedSpeechRange.model_validate(entry) for entry in json.loads(_DATA_FILE.read_text())]

    assert len({speech_range.report_id for speech_range in speech_ranges}) == len(speech_ranges)

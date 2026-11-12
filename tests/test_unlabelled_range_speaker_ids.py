from typing import Optional

import pytest

from crud.speech import SpeechKindRow
from enums import SpeechKind
from exceptions import HansardUnlabelledSpeechError
from schemas.unlabelled_speech import UnlabelledSpeechRange
from services.speaker_link import get_unlabelled_range_speaker_ids

_CHAIR = "Mr Deputy Speaker"
_MEMBER = "Ms Rahayu Mahzam"
_CREDITED_SPEAKER_ID = 1210
_OTHER_SPEAKER_ID = 7
_OPENING_LOCATOR = "We have been working"
_CLOSING_LOCATOR = "Healthy living starts"
_CHAMBER_EVENT_ROW_ID = 4
_ROW_AFTER_RANGE_ID = 7
_LABELLED_ROW_ID = 8


def _build_range(
    first_transcript_start: str, last_transcript_start: str
) -> UnlabelledSpeechRange:
    return UnlabelledSpeechRange(
        report_id=6150,
        speaker=_CHAIR,
        credited_speaker_name="Rahayu Mahzam",
        first_transcript_start=first_transcript_start,
        last_transcript_start=last_transcript_start,
        reason="",
    )


def _build_row(
    row_id: int,
    transcript: str,
    speaker: Optional[str] = None,
    kind: SpeechKind = SpeechKind.SPEECH,
    speaker_id: Optional[int] = None,
) -> SpeechKindRow:
    return SpeechKindRow(row_id, speaker, transcript, kind, speaker_id)


def _build_chair_resumption() -> list[SpeechKindRow]:
    return [
        _build_row(
            1, "May I speak in Malay?", _MEMBER, speaker_id=_CREDITED_SPEAKER_ID
        ),
        _build_row(2, "Please do.", _CHAIR, speaker_id=_OTHER_SPEAKER_ID),
        _build_row(3, "[_Please refer to Vernacular Speech_.] We have been working"),
        _build_row(
            _CHAMBER_EVENT_ROW_ID, "[_Applause._]", kind=SpeechKind.CHAMBER_EVENT
        ),
        _build_row(5, "Healthy living starts with you and me."),
        _build_row(6, "Thank you.", _CHAIR, speaker_id=_OTHER_SPEAKER_ID),
        _build_row(_ROW_AFTER_RANGE_ID, "An unlabelled row after the range."),
    ]


def test_unlabelled_speech_rows_in_the_range_take_the_credited_speaker() -> None:
    speech_range = _build_range(
        "[_Please refer to Vernacular Speech_.] We have", _CLOSING_LOCATOR
    )

    speaker_ids = get_unlabelled_range_speaker_ids(
        speech_range, _build_chair_resumption(), _CREDITED_SPEAKER_ID
    )

    assert speaker_ids == {3: _CREDITED_SPEAKER_ID, 5: _CREDITED_SPEAKER_ID}


def test_a_chamber_event_inside_the_range_stays_uncredited() -> None:
    speech_range = _build_range(
        "[_Please refer to Vernacular Speech_.] We have", _CLOSING_LOCATOR
    )

    speaker_ids = get_unlabelled_range_speaker_ids(
        speech_range, _build_chair_resumption(), _CREDITED_SPEAKER_ID
    )

    assert _CHAMBER_EVENT_ROW_ID not in speaker_ids


def test_a_row_after_the_last_locator_stays_uncredited() -> None:
    speech_range = _build_range(
        "[_Please refer to Vernacular Speech_.] We have", _CLOSING_LOCATOR
    )

    speaker_ids = get_unlabelled_range_speaker_ids(
        speech_range, _build_chair_resumption(), _CREDITED_SPEAKER_ID
    )

    assert _ROW_AFTER_RANGE_ID not in speaker_ids


def test_a_row_with_a_label_inside_the_range_keeps_its_speaker() -> None:
    speech_range = _build_range(
        "[_Please refer to Vernacular Speech_.] We have", _CLOSING_LOCATOR
    )
    speech_rows = _build_chair_resumption()
    speech_rows.insert(
        3, _build_row(_LABELLED_ROW_ID, "Order.", _CHAIR, speaker_id=_OTHER_SPEAKER_ID)
    )

    speaker_ids = get_unlabelled_range_speaker_ids(
        speech_range, speech_rows, _CREDITED_SPEAKER_ID
    )

    assert _LABELLED_ROW_ID not in speaker_ids


def test_a_stray_underscore_before_the_locator_still_matches() -> None:
    speech_rows = [
        _build_row(1, "_[_Please refer to Vernacular Speech_.] Mdm Speaker, I learn"),
        _build_row(2, "I hope that the message in this year's Budget"),
    ]
    speech_range = _build_range(
        "[_Please refer to Vernacular Speech_.] Mdm Speaker, I learn",
        "I hope that the message",
    )

    speaker_ids = get_unlabelled_range_speaker_ids(
        speech_range, speech_rows, _CREDITED_SPEAKER_ID
    )

    assert speaker_ids == {1: _CREDITED_SPEAKER_ID, 2: _CREDITED_SPEAKER_ID}


def test_a_labelled_row_with_the_locator_text_does_not_start_the_range() -> None:
    speech_rows = [
        _build_row(
            1, "Healthy living starts here.", _CHAIR, speaker_id=_OTHER_SPEAKER_ID
        ),
        _build_row(2, "We have been working"),
        _build_row(3, "Healthy living starts with you and me."),
    ]
    speech_range = _build_range(_OPENING_LOCATOR, _CLOSING_LOCATOR)

    speaker_ids = get_unlabelled_range_speaker_ids(
        speech_range, speech_rows, _CREDITED_SPEAKER_ID
    )

    assert speaker_ids == {2: _CREDITED_SPEAKER_ID, 3: _CREDITED_SPEAKER_ID}


def test_a_range_of_one_row_credits_that_row() -> None:
    speech_rows = [_build_row(1, "As we look forward to scale new heights")]
    speech_range = _build_range("As we look forward", "As we look forward")

    speaker_ids = get_unlabelled_range_speaker_ids(
        speech_range, speech_rows, _CREDITED_SPEAKER_ID
    )

    assert speaker_ids == {1: _CREDITED_SPEAKER_ID}


def test_a_credited_row_is_not_planned_again_but_still_marks_the_range() -> None:
    speech_rows = [
        _build_row(1, "We have been working", speaker_id=_CREDITED_SPEAKER_ID),
        _build_row(2, "Healthy living starts with you and me."),
    ]
    speech_range = _build_range(_OPENING_LOCATOR, _CLOSING_LOCATOR)

    speaker_ids = get_unlabelled_range_speaker_ids(
        speech_range, speech_rows, _CREDITED_SPEAKER_ID
    )

    assert speaker_ids == {2: _CREDITED_SPEAKER_ID}


@pytest.mark.parametrize(
    ("first_transcript_start", "last_transcript_start"),
    [("We have not been working", _CLOSING_LOCATOR), (_OPENING_LOCATOR, "Never said")],
)
def test_a_missing_locator_raises(
    first_transcript_start: str, last_transcript_start: str
) -> None:
    speech_range = _build_range(first_transcript_start, last_transcript_start)

    with pytest.raises(HansardUnlabelledSpeechError):
        get_unlabelled_range_speaker_ids(
            speech_range, _build_chair_resumption(), _CREDITED_SPEAKER_ID
        )

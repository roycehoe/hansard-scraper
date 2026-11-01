import json

import pytest
from pydantic import ValidationError

from enums import HandCheckDifferenceClass, HandCheckErrorTier, HandCheckSpeakerVerdict
from schemas.hand_check_verdict import HandCheckVerdict


def _get_verdict_fields(**fields: object) -> dict[str, object]:
    verdict_fields: dict[str, object] = {
        "packet_id": "3f9a1c07b2de",
        "speaker_verdict": "RIGHT",
        "speaker_tier": None,
        "note": "",
        "difference_classes": [],
    }
    return verdict_fields | fields


def test_a_clean_line_reads_back_equal() -> None:
    verdict = HandCheckVerdict.model_validate_json(json.dumps(_get_verdict_fields()))

    assert HandCheckVerdict.model_validate_json(verdict.model_dump_json()) == verdict
    assert verdict.speaker_verdict is HandCheckSpeakerVerdict.RIGHT
    assert verdict.difference_classes == []


def test_a_wrong_speaker_with_a_tier_and_classes_is_accepted() -> None:
    verdict = HandCheckVerdict.model_validate_json(
        json.dumps(
            _get_verdict_fields(
                speaker_verdict="WRONG",
                speaker_tier="A",
                difference_classes=["SUBSTANTIVE", "COSMETIC"],
            )
        )
    )

    assert verdict.speaker_tier is HandCheckErrorTier.A
    assert verdict.difference_classes == [
        HandCheckDifferenceClass.SUBSTANTIVE,
        HandCheckDifferenceClass.COSMETIC,
    ]


def test_a_line_without_the_classes_key_reads_as_no_classes() -> None:
    verdict_fields = _get_verdict_fields()
    verdict_fields.pop("difference_classes")

    verdict = HandCheckVerdict.model_validate_json(json.dumps(verdict_fields))

    assert verdict.difference_classes == []


def test_the_schema_takes_any_number_of_classes() -> None:
    verdict = HandCheckVerdict.model_validate_json(
        json.dumps(
            _get_verdict_fields(
                difference_classes=["LISTED_CHANGE", "SUBSTANTIVE", "COSMETIC"]
            )
        )
    )

    assert verdict.difference_classes == [
        HandCheckDifferenceClass.LISTED_CHANGE,
        HandCheckDifferenceClass.SUBSTANTIVE,
        HandCheckDifferenceClass.COSMETIC,
    ]


def test_a_line_that_is_not_json_is_refused() -> None:
    with pytest.raises(ValidationError, match="json_invalid"):
        HandCheckVerdict.model_validate_json("not json {")


@pytest.mark.parametrize(
    "key", ["packet_id", "speaker_verdict", "speaker_tier", "note"]
)
def test_a_missing_key_is_refused(key: str) -> None:
    verdict_fields = _get_verdict_fields()
    verdict_fields.pop(key)

    with pytest.raises(ValidationError, match=key):
        HandCheckVerdict.model_validate_json(json.dumps(verdict_fields))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("speaker_verdict", "MOSTLY_RIGHT"),
        ("speaker_verdict", "right"),
        ("speaker_tier", "D"),
        ("difference_classes", ["glue"]),
        ("difference_classes", ["substantive"]),
        ("difference_classes", ["SUBSTANTIVE_ERROR"]),
    ],
)
def test_a_word_outside_the_enums_is_refused(key: str, value: object) -> None:
    with pytest.raises(ValidationError):
        HandCheckVerdict.model_validate_json(
            json.dumps(_get_verdict_fields(**{key: value}))
        )


@pytest.mark.parametrize("key", ["verdict_note", "text_verdict", "text_tier"])
def test_an_unknown_key_is_refused(key: str) -> None:
    with pytest.raises(ValidationError, match=key):
        HandCheckVerdict.model_validate_json(
            json.dumps(_get_verdict_fields(**{key: "x"}))
        )


def test_a_wrong_speaker_without_a_tier_is_refused() -> None:
    with pytest.raises(ValidationError, match="needs a speaker_tier"):
        HandCheckVerdict.model_validate_json(
            json.dumps(_get_verdict_fields(speaker_verdict="WRONG"))
        )


@pytest.mark.parametrize("speaker_verdict", ["RIGHT", "RECORD_DOES_NOT_SAY"])
def test_a_speaker_tier_on_any_other_verdict_is_refused(speaker_verdict: str) -> None:
    with pytest.raises(ValidationError, match="only a wrong speaker verdict"):
        HandCheckVerdict.model_validate_json(
            json.dumps(
                _get_verdict_fields(speaker_verdict=speaker_verdict, speaker_tier="A")
            )
        )

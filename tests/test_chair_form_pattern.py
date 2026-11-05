import pytest

from utils.names import CHAIR_FORM_PATTERN


@pytest.mark.parametrize(
    "label", ["Mr Speaker", "Mdm Deputy Speaker", "Mr Sppeaker", "Mr Speake"]
)
def test_chair_form_pattern_matches_the_chair_and_its_two_printed_typos(
    label: str,
) -> None:
    assert CHAIR_FORM_PATTERN.search(label) is not None


@pytest.mark.parametrize("label", ["Mr Speakes", "Mr Spear", "Mr Sppeakers"])
def test_chair_form_pattern_rejects_other_misspellings(label: str) -> None:
    assert CHAIR_FORM_PATTERN.search(label) is None

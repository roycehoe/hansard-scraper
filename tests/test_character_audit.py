import pytest

from services.character_audit import (
    get_character_fault_counts,
    get_derived_text_counts,
    get_unbalanced_pairs,
)


@pytest.mark.parametrize(
    ("text", "is_derived", "signature_counts"),
    [
        ("breaking their heads.�?", True, {"replacement character": 1}),
        ("Presidentâ€™s Address", True, {"mojibake": 1}),
        ("Sir,&nbsp;I <p>agree", True, {"HTML entity": 1, "HTML tag": 1}),
        ("Sir,&nbsp;I <p>agree", False, {}),
        ("the “Education Bank”, akin to", True, {}),
        ("invest more in R&D; and (3) to", True, {}),
    ],
)
def test_signatures_are_counted(text: str, is_derived: bool, signature_counts: dict[str, int]) -> None:
    get_counts = get_derived_text_counts if is_derived else get_character_fault_counts
    assert get_counts(text) == signature_counts


def test_a_quote_left_open_is_unbalanced() -> None:
    assert get_unbalanced_pairs("an “Education Bank�?, akin to (an Edusave") == ["unbalanced double quotes", "unbalanced parentheses"]

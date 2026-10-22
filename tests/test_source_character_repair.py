import pytest

from utils.markdown_parser import repair_source_characters


@pytest.mark.parametrize(
    ("markdown", "repaired_markdown"),
    [
        ("an \u201cEducation Bank\ufffd?, akin", "an \u201cEducation Bank\u201d, akin"),
        ("we \u591a\ufffd?\ufffd\u591a\u8bb2", "we \u591a\ufffd?\ufffd\u591a\u8bb2"),
        ("the fa\u00c3\u00a7ade of the", "the fa\u00e7ade of the"),
        ("lost souls\u00ef\u00bf\u00bd? in", "lost souls\u201d in"),
        ("our entrep\ufffdt economy", "our entrep\u00f4t economy"),
        ("risen from \ufffd281.7 million", "risen from \u00a3281.7 million"),
        ("about 4\ufffd% and 2\ufffd per cent", "about 4\ufffd% and 2\ufffd per cent"),
        ("**\ufeff Er Lee Bee Wah (Ang Mo Kio):**", "** Er Lee Bee Wah (Ang Mo Kio):**"),
    ],
)
def test_source_characters_are_repaired_only_where_one_answer_fits(markdown: str, repaired_markdown: str) -> None:
    assert repair_source_characters(markdown) == repaired_markdown

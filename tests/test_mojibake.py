import pytest

from utils.text import fix_mojibake


@pytest.mark.parametrize(
    ("text", "fixed_text"),
    [
        ("Debate on Presidentâ€™s Address", "Debate on President’s Address"),
        ("Committee of Supply âˆ’ Head U (Prime Minister’s Office)", "Committee of Supply − Head U (Prime Minister’s Office)"),
        ("Committee of Supply – Head S (Ministry of Manpower)", "Committee of Supply – Head S (Ministry of Manpower)"),
        ("PENAL CODE (AMENDMENT) BILL", "PENAL CODE (AMENDMENT) BILL"),
    ],
)
def test_each_garbled_run_is_fixed_and_correct_text_is_kept(text: str, fixed_text: str) -> None:
    assert fix_mojibake(text) == fixed_text

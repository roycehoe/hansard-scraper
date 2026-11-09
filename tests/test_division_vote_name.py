from utils.division_vote_name import get_name_to_resolve


def test_a_trailing_title_and_period_are_stripped() -> None:
    assert get_name_to_resolve("Chan Choy Siong. Madam") == "Chan Choy Siong"
    assert get_name_to_resolve("Fung Yin Ching. Miss.") == "Fung Yin Ching"


def test_an_initial_keeps_its_period() -> None:
    assert get_name_to_resolve("Koh, C.") == "Koh, C."
    assert get_name_to_resolve("Bani, S.T.") == "Bani, S.T."


def test_a_plain_name_is_unchanged() -> None:
    assert get_name_to_resolve("Chiam See Tong") == "Chiam See Tong"
    assert get_name_to_resolve("  Buang bin Omar Junid.  ") == "Buang bin Omar Junid"

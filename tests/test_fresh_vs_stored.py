from schemas.fresh_vs_stored_report import ComparedSpeechRow, FreshVsStoredStatus
from scripts.fresh_vs_stored import compare_rows, get_row_differences, tokenize


def test_equal_rows_with_gapless_ordinals_are_same() -> None:
    rows = [ComparedSpeechRow(speaker="A", transcript="one", kind=None), ComparedSpeechRow(speaker="B", transcript="two", kind=None)]

    assert compare_rows(rows, [1, 2], rows) == FreshVsStoredStatus.SAME


def test_equal_rows_with_gapped_ordinals_are_ordinal_only() -> None:
    rows = [ComparedSpeechRow(speaker="A", transcript="one", kind=None), ComparedSpeechRow(speaker="B", transcript="two", kind=None)]

    assert compare_rows(rows, [1, 3], rows) == FreshVsStoredStatus.ORDINAL_ONLY


def test_a_changed_transcript_is_content_and_counts_the_words_lost() -> None:
    stored = [ComparedSpeechRow(speaker="A", transcript="one two", kind=None)]
    fresh = [ComparedSpeechRow(speaker="A", transcript="one", kind=None)]

    row_differences = get_row_differences(stored, fresh)

    assert compare_rows(stored, [1], fresh) == FreshVsStoredStatus.CONTENT
    assert row_differences.word_lost_count == 1
    assert row_differences.word_gained_count == 0
    assert row_differences.is_kind_only is False


def test_tokens_are_lowercase_ascii_letters_and_digits() -> None:
    assert tokenize("Hello, hello 2nd-time") == {"hello": 2, "2nd": 1, "time": 1}

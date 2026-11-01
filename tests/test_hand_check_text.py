import pytest

from utils.hand_check_text import (
    WordDifference,
    get_word_differences,
    normalize_hand_check_text,
)


@pytest.mark.parametrize(
    ("text", "normalized_text"),
    [
        ("<p>The <b>Minister</b> said</p>", "The Minister said"),
        ("<i>one</i> two", "one two"),
        ('<a href="x">link</a> text', "link text"),
        ("248<sup>1</sup> psychiatrists", "2481 psychiatrists"),
    ],
)
def test_a_tag_is_dropped_and_its_text_kept(text: str, normalized_text: str) -> None:
    assert normalize_hand_check_text(text) == normalized_text


@pytest.mark.parametrize(
    "text",
    [
        "one<br>two",
        "one<br/>two",
        "one<br />two",
        "one<BR>two",
        'one<br clear="all">two',
    ],
)
def test_a_line_break_tag_becomes_a_space_in_every_spelling(text: str) -> None:
    assert normalize_hand_check_text(text) == "one two"


@pytest.mark.parametrize(
    ("text", "normalized_text"),
    [
        ("R&amp;D", "R&D"),
        ("a &ndash; b", "a – b"),
        ("caf&eacute;", "café"),
        ("it&#8217;s", "it’s"),
        ("it&#x2019;s", "it’s"),
    ],
)
def test_character_references_are_decoded(text: str, normalized_text: str) -> None:
    assert normalize_hand_check_text(text) == normalized_text


@pytest.mark.parametrize("text", ["a&nbsp;b", "a&#160;b", "a b"])
def test_a_non_breaking_space_becomes_a_space_as_a_reference_and_as_a_character(
    text: str,
) -> None:
    assert normalize_hand_check_text(text) == "a b"


@pytest.mark.parametrize(
    ("text", "normalized_text"),
    [
        ("**bold** word", "bold word"),
        ("_italic_ word", "italic word"),
        ("__strong__ word", "strong word"),
        ('[_Please refer to "__Title__"_]', '[Please refer to "Title"]'),
        ("snake_case", "snakecase"),
    ],
)
def test_emphasis_markers_are_dropped(text: str, normalized_text: str) -> None:
    assert normalize_hand_check_text(text) == normalized_text


@pytest.mark.parametrize("text", ["5 * 3", "a*b", "*one*"])
def test_a_lone_asterisk_is_kept(text: str) -> None:
    assert normalize_hand_check_text(text) == text


@pytest.mark.parametrize("text", ["  a \n\t b  ", "a\r\n\r\nb", " a b "])
def test_runs_of_whitespace_fold_to_one_space_and_both_ends_are_trimmed(
    text: str,
) -> None:
    assert normalize_hand_check_text(text) == "a b"


@pytest.mark.parametrize(
    ("text", "word_count"),
    [
        ("one two three", 3),
        ("a  b", 2),
        ("<b>one</b> <i>two</i>", 2),
        ("_one_ _two_", 2),
        ("one&nbsp;two", 2),
        ("one<br>two", 2),
    ],
)
def test_no_space_between_two_words_is_deleted(text: str, word_count: int) -> None:
    assert normalize_hand_check_text(text).count(" ") == word_count - 1


def test_two_words_and_one_glued_word_stay_different() -> None:
    assert normalize_hand_check_text("one two") != normalize_hand_check_text("onetwo")


def test_a_footnote_marker_stays_and_differs_from_a_stripped_superscript() -> None:
    normalized_text = normalize_hand_check_text("248[1] psychiatrists")

    assert normalized_text == "248[1] psychiatrists"
    assert normalized_text != normalize_hand_check_text("248<sup>1</sup> psychiatrists")


@pytest.mark.parametrize("text", ["a rate of <1% and >5%", "x < y > z"])
def test_a_less_than_sign_that_opens_no_tag_is_kept(text: str) -> None:
    assert normalize_hand_check_text(text) == text


def test_an_escaped_tag_is_decoded_after_tags_are_dropped() -> None:
    assert normalize_hand_check_text("x &lt;b&gt; y") == "x <b> y"


def test_texts_that_differ_only_in_markup_and_spacing_have_no_word_differences() -> (
    None
):
    assert get_word_differences("<p>one  <b>two</b></p>", "one _two_") == []


def test_a_dropped_word_is_a_delete() -> None:
    assert get_word_differences("one two three", "one three") == [
        WordDifference("delete", "two", "")
    ]


def test_an_added_word_is_an_insert() -> None:
    assert get_word_differences("one two", "one two three") == [
        WordDifference("insert", "", "three")
    ]


def test_a_changed_word_is_a_replace() -> None:
    assert get_word_differences("one two three", "one 2 three") == [
        WordDifference("replace", "two", "2")
    ]


def test_glued_words_are_one_replace_of_two_words_by_one() -> None:
    assert get_word_differences("one two three", "onetwo three") == [
        WordDifference("replace", "one two", "onetwo")
    ]


def test_a_footnote_marker_is_a_replace() -> None:
    assert get_word_differences(
        "248<sup>1</sup> psychiatrists", "248[1] psychiatrists"
    ) == [WordDifference("replace", "2481", "248[1]")]


def test_a_cut_out_chamber_event_is_a_delete() -> None:
    assert get_word_differences("one [Applause] two", "one two") == [
        WordDifference("delete", "[Applause]", "")
    ]


def test_each_separated_run_is_reported_on_its_own_in_order() -> None:
    assert get_word_differences("a b c d e", "a x c d y") == [
        WordDifference("replace", "b", "x"),
        WordDifference("replace", "e", "y"),
    ]


def test_an_empty_row_deletes_every_source_word() -> None:
    assert get_word_differences("one two", "") == [
        WordDifference("delete", "one two", "")
    ]
    assert get_word_differences("", "one two") == [
        WordDifference("insert", "", "one two")
    ]

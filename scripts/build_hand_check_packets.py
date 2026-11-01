import html
import re
from dataclasses import dataclass
from typing import Optional

from enums import HandCheckMatchStatus
from schemas.hand_check_packet import HandCheckGapCheck
from utils.hand_check_text import normalize_hand_check_text

_HEAD_BLOCK_RE = re.compile(r"<head\b.*?</head\s*>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# NOTE: a table cell is not a split tag, so a header table row stays one paragraph.
_PARAGRAPH_BREAK_RE = re.compile(
    r"(</?(?:p|br|div|h[1-6]|tr|li|ul|ol|table|tbody|thead|pre|blockquote|center|hr|body|html)\b[^>]*>)",
    re.IGNORECASE,
)
_HEADING_OPENING_RE = re.compile(r"<h[1-6]\b", re.IGNORECASE)
_PAGE_FURNITURE_RE = re.compile(r"^(?:Column|Page)(?:\s+No)?\s*:\s*\d+$", re.IGNORECASE)
# NOTE: the older system prints "<b>Mr Speaker:</b>" and the newer "<strong>Mr Speaker</strong>:", or no colon in a question.
_LABEL_RE = re.compile(
    r"^(?P<prefix>(?:\s|&nbsp;|\d{1,3}[.\\]*|<(?!/?(?:b|strong)\b)[^>]*>)*)"
    r"<(?P<tag>b|strong)\b[^>]*>(?P<label>.*?)</(?P=tag)\s*>"
    r"(?P<colon>(?:\s|&nbsp;)*:)?",
    re.IGNORECASE | re.DOTALL,
)
_PLAIN_CHAIR_LABEL_RE = re.compile(
    r"^(?P<prefix>(?:\s|&nbsp;)*)(?P<label>(?:Mr|Mdm|Madam)\s+(?:Deputy\s+)?Speaker)\s*:",
    re.IGNORECASE,
)
_NAME_OPENING_RE = re.compile(r"^(?:Mr|Mrs|Ms|Mdm|Madam|Dr|Prof|Assoc|Er|The)\b")
_LETTER_RE = re.compile(r"[A-Za-z]")
_ALPHANUMERIC_RE = re.compile(r"[A-Za-z0-9]")
_LABEL_TRAILING_CHARACTERS = " :"
_PROBE_WORD_COUNTS = (8, 5, 3)
_GAP_PROBE_WORD_COUNT = 5
_TIME_STAMP_RE = re.compile(
    r"^\d{1,2}(?:\s*[.:]\s*\d{2})?\s*(?:[ap]\.?m|noon|midnight)\.?$", re.IGNORECASE
)
_CHAIR_NOTE_RE = re.compile(r"^[\[(][^\[\]]{0,150}?\bin the Chair\b", re.IGNORECASE)
_CELL_END_RE = re.compile(r"</t[dh]\s*>", re.IGNORECASE)
_DISPLAY_TAG_RE = re.compile(r"<(/?)(b|strong|i|em|sup|sub)\b[^>]*>", re.IGNORECASE)
# NOTE: a tag opens with a letter or a slash, as in utils/hand_check_text.py, so "<5%" in running text is not one.
_OTHER_TAG_RE = re.compile(
    r"<(?!/?(?:b|strong|i|em|sup|sub)\b)/?[A-Za-z][^<>]*>", re.IGNORECASE
)
_WHITESPACE_RE = re.compile(r"\s+")
_BOLD_TAG_NAMES = frozenset({"b", "strong"})
_ITALIC_TAG_NAMES = frozenset({"i", "em"})


@dataclass(frozen=True)
class SourceParagraph:
    label: Optional[str]
    full_html: str
    body_html: str
    is_heading: bool


@dataclass(frozen=True)
class SourceRun:
    first_index: int
    last_index: int


@dataclass(frozen=True)
class SourceMatch:
    status: HandCheckMatchStatus
    run: Optional[SourceRun]


def _build_source_paragraph(paragraph_html: str, is_heading: bool) -> SourceParagraph:
    unlabelled_paragraph = SourceParagraph(
        None, paragraph_html, paragraph_html, is_heading
    )
    plain_label_match = _PLAIN_CHAIR_LABEL_RE.match(paragraph_html)
    if plain_label_match is not None:
        return SourceParagraph(
            normalize_hand_check_text(plain_label_match.group("label")),
            paragraph_html,
            plain_label_match.group("prefix")
            + paragraph_html[plain_label_match.end() :],
            is_heading,
        )
    label_match = _LABEL_RE.match(paragraph_html)
    if label_match is None:
        return unlabelled_paragraph
    label_text = normalize_hand_check_text(label_match.group("label"))
    label = label_text.rstrip(_LABEL_TRAILING_CHARACTERS)
    if _LETTER_RE.search(label) is None:
        return unlabelled_paragraph
    rest_html = paragraph_html[label_match.end() :]
    is_colon_printed = label_match.group("colon") is not None or label_text.endswith(
        ":"
    )
    is_question_form = (
        normalize_hand_check_text(rest_html) != ""
        and _NAME_OPENING_RE.match(label) is not None
    )
    if not is_colon_printed and not is_question_form:
        return unlabelled_paragraph
    return SourceParagraph(
        label, paragraph_html, label_match.group("prefix") + rest_html, is_heading
    )


def split_source_paragraphs(report_html: str) -> list[SourceParagraph]:
    body_html = _COMMENT_RE.sub("", _HEAD_BLOCK_RE.sub("", report_html))
    pieces = _PARAGRAPH_BREAK_RE.split(body_html)
    paragraphs = []
    for opening_tag, paragraph_html in zip([""] + pieces[1::2], pieces[0::2]):
        text = normalize_hand_check_text(paragraph_html)
        if text == "":
            continue
        if _PAGE_FURNITURE_RE.match(text) is not None:
            continue
        paragraphs.append(
            _build_source_paragraph(
                paragraph_html, _HEADING_OPENING_RE.match(opening_tag) is not None
            )
        )
    return paragraphs


def _get_label_key(label: Optional[str]) -> str:
    if label is None:
        return ""
    return normalize_hand_check_text(label).casefold()


def _get_turn_label_keys(paragraphs: list[SourceParagraph]) -> list[str]:
    turn_label_keys = []
    turn_label_key = ""
    for paragraph in paragraphs:
        if paragraph.label is not None:
            turn_label_key = _get_label_key(paragraph.label)
        turn_label_keys.append(turn_label_key)
    return turn_label_keys


def _get_exact_runs(
    row_text: str, body_texts: list[str], full_texts: list[str]
) -> list[SourceRun]:
    exact_runs = []
    for first_index, body_text in enumerate(body_texts):
        joined_text = body_text
        for last_index in range(first_index, len(full_texts)):
            if last_index != first_index:
                joined_text = f"{joined_text} {full_texts[last_index]}"
            if joined_text == row_text:
                exact_runs.append(SourceRun(first_index, last_index))
                break
            if not row_text.startswith(f"{joined_text} "):
                break
    return exact_runs


def _is_word_run_in(probe: str, text: str) -> bool:
    return f" {probe} " in f" {text} "


def _get_closest_run(
    row_text: str,
    body_texts: list[str],
    full_texts: list[str],
    turn_label_keys: list[str],
    row_label_key: str,
) -> Optional[SourceRun]:
    row_words = row_text.split(" ")
    for probe_word_count in _PROBE_WORD_COUNTS:
        probe_length = min(probe_word_count, len(row_words))
        first_probe = " ".join(row_words[:probe_length])
        last_probe = " ".join(row_words[-probe_length:])
        first_indexes = [
            index
            for index, body_text in enumerate(body_texts)
            if _is_word_run_in(first_probe, body_text)
        ]
        if not first_indexes:
            continue
        first_index = next(
            (
                index
                for index in first_indexes
                if turn_label_keys[index] == row_label_key
            ),
            first_indexes[0],
        )
        last_index = next(
            (
                index
                for index in range(first_index, len(full_texts))
                if _is_word_run_in(last_probe, full_texts[index])
            ),
            None,
        )
        if last_index is not None:
            return SourceRun(first_index, last_index)
    return None


def _is_row_start(source_text: str, row_text: str) -> bool:
    source_words = source_text.split(" ")
    row_words = row_text.split(" ")
    probe_length = min(_GAP_PROBE_WORD_COUNT, len(source_words), len(row_words))
    return source_words[:probe_length] == row_words[:probe_length]


def _is_skipped_paragraph(paragraph: SourceParagraph) -> bool:
    if paragraph.is_heading:
        return True
    text = normalize_hand_check_text(paragraph.full_html)
    if _TIME_STAMP_RE.match(text) is not None:
        return True
    if _CHAIR_NOTE_RE.match(text) is not None:
        return True
    return _ALPHANUMERIC_RE.search(text) is None


def _get_next_paragraph_index(
    paragraphs: list[SourceParagraph], last_index: int
) -> Optional[int]:
    for index in range(last_index + 1, len(paragraphs)):
        if not _is_skipped_paragraph(paragraphs[index]):
            return index
    return None


def _is_followed_by_next_row(
    paragraphs: list[SourceParagraph],
    body_texts: list[str],
    last_index: int,
    next_row_text: Optional[str],
) -> bool:
    next_index = _get_next_paragraph_index(paragraphs, last_index)
    if next_index is None:
        return False
    if next_row_text is None:
        return False
    return _is_row_start(body_texts[next_index], next_row_text)


def get_source_match(
    paragraphs: list[SourceParagraph],
    speaker: Optional[str],
    transcript: str,
    next_transcript: Optional[str],
) -> SourceMatch:
    row_text = normalize_hand_check_text(transcript)
    body_texts = [
        normalize_hand_check_text(paragraph.body_html) for paragraph in paragraphs
    ]
    full_texts = [
        normalize_hand_check_text(paragraph.full_html) for paragraph in paragraphs
    ]
    turn_label_keys = _get_turn_label_keys(paragraphs)
    row_label_key = _get_label_key(speaker)
    exact_runs = _get_exact_runs(row_text, body_texts, full_texts)
    if exact_runs:
        next_row_text = (
            None
            if next_transcript is None
            else normalize_hand_check_text(next_transcript)
        )
        # NOTE: a short reply can repeat word for word, so the run whose next paragraph starts the next row wins, then the run under the row's own label.
        best_exact_run = max(
            exact_runs,
            key=lambda exact_run: (
                _is_followed_by_next_row(
                    paragraphs, body_texts, exact_run.last_index, next_row_text
                ),
                turn_label_keys[exact_run.first_index] == row_label_key,
            ),
        )
        return SourceMatch(HandCheckMatchStatus.EXACT, best_exact_run)
    closest_run = _get_closest_run(
        row_text, body_texts, full_texts, turn_label_keys, row_label_key
    )
    if closest_run is not None:
        return SourceMatch(HandCheckMatchStatus.INEXACT, closest_run)
    return SourceMatch(HandCheckMatchStatus.NOT_FOUND, None)


def _get_display_tag(tag_match: re.Match[str]) -> str:
    closing_slash = tag_match.group(1)
    tag_name = tag_match.group(2).lower()
    if tag_name in _BOLD_TAG_NAMES:
        return f"<{closing_slash}B>"
    if tag_name in _ITALIC_TAG_NAMES:
        return f"<{closing_slash}I>"
    return f"<{closing_slash}{tag_name.upper()}>"


def render_source_html(source_html: str) -> str:
    without_other_tags = _OTHER_TAG_RE.sub("", _CELL_END_RE.sub(" ", source_html))
    marked_text = _DISPLAY_TAG_RE.sub(_get_display_tag, without_other_tags)
    return _WHITESPACE_RE.sub(" ", html.unescape(marked_text)).strip()


def get_matched_source_html(
    paragraphs: list[SourceParagraph], source_match: SourceMatch
) -> str:
    if source_match.run is None:
        return ""
    run = source_match.run
    return " ".join(
        [
            paragraphs[run.first_index].body_html,
            *(
                paragraph.full_html
                for paragraph in paragraphs[run.first_index + 1 : run.last_index + 1]
            ),
        ]
    )


def _get_context_start_index(
    paragraphs: list[SourceParagraph], first_index: int
) -> int:
    for index in range(first_index, -1, -1):
        if paragraphs[index].label is not None:
            return index
    return 0


def get_context_paragraphs(
    paragraphs: list[SourceParagraph], source_match: SourceMatch
) -> list[str]:
    if source_match.run is None:
        return []
    run = source_match.run
    start_index = _get_context_start_index(paragraphs, run.first_index)
    return [
        render_source_html(paragraph.full_html)
        for paragraph in paragraphs[start_index : run.last_index + 1]
    ]


def get_after_paragraph(
    paragraphs: list[SourceParagraph], source_match: SourceMatch
) -> Optional[str]:
    if source_match.run is None:
        return None
    if source_match.run.last_index + 1 == len(paragraphs):
        return None
    return render_source_html(paragraphs[source_match.run.last_index + 1].full_html)


def get_gap_check(
    paragraphs: list[SourceParagraph], last_index: int, next_transcript: Optional[str]
) -> HandCheckGapCheck:
    skipped_paragraphs = []
    for index in range(last_index + 1, len(paragraphs)):
        if _is_skipped_paragraph(paragraphs[index]):
            skipped_paragraphs.append(render_source_html(paragraphs[index].full_html))
            continue
        next_source_text = normalize_hand_check_text(paragraphs[index].body_html)
        return HandCheckGapCheck(
            is_next_row=next_transcript is not None
            and _is_row_start(
                next_source_text, normalize_hand_check_text(next_transcript)
            ),
            skipped_paragraphs=skipped_paragraphs,
            next_source_text=next_source_text,
        )
    return HandCheckGapCheck(
        is_next_row=next_transcript is None,
        skipped_paragraphs=skipped_paragraphs,
        next_source_text=None,
    )

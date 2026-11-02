import argparse
import html
import json
import random
import re
import secrets
from collections import Counter
from dataclasses import dataclass
from datetime import date
from functools import partial
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from database.init import build_read_only_engine
from database.report import Report
from enums import (
    HandCheckAnswerStatus,
    HandCheckFormOfAddress,
    HandCheckLiveCheckStatus,
    HandCheckMatchStatus,
    ReportVersion,
)
from exceptions import HansardGatewayError, HansardHandCheckError
from gateway.hansard_topic import get_hansard_topic_response
from logs import logger
from schemas.hand_check_office_holder import HandCheckOfficeHolder
from schemas.hand_check_packet import (
    HandCheckGapCheck,
    HandCheckPacket,
    HandCheckPackets,
    HandCheckRoleSection,
    HandCheckWordDifference,
)
from schemas.hand_check_snapshot import (
    HandCheckSnapshot,
    HandCheckSnapshotRow,
    HandCheckSnapshotRows,
)
from schemas.hansard_report_response import HansardReportSection
from schemas.hansard_topic_response import HansardTopicResponse
from services.hansard_website import get_topic_html_content, get_topic_id
from settings import settings
from utils.data_files import get_hand_check_office_holders
from utils.hand_check_text import (
    RowContext,
    get_word_differences,
    normalize_hand_check_text,
)
from utils.markdown_parser import PROC_TEXT_CLOSE_TAG, PROC_TEXT_OPEN_TAG
from utils.sitting_dates import get_sitting_date_key

_HEAD_BLOCK_RE = re.compile(r"<head\b.*?</head\s*>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# NOTE: a table cell is not a split tag, so a header table row stays one paragraph.
_PARAGRAPH_BREAK_RE = re.compile(
    r"(</?(?:p|br|div|h[1-6]|tr|li|ul|ol|table|tbody|thead|pre|blockquote|center|hr|body|html)\b[^>]*>)",
    re.IGNORECASE,
)
_HEADING_OPENING_RE = re.compile(r"<h[1-6]\b", re.IGNORECASE)
_PREFORMATTED_OPENING_RE = re.compile(r"<pre\b", re.IGNORECASE)
_PREFORMATTED_CLOSING_RE = re.compile(r"</pre\b", re.IGNORECASE)
_LINE_BREAK_RE = re.compile(r"\r?\n")
_PAGE_FURNITURE_RE = re.compile(r"^(?:Column|Page)(?:\s+No)?\s*:\s*\d+$", re.IGNORECASE)
# NOTE: the HTML form of the language note the parser strips from a label (`_LANGUAGE_NOTE` in services/speech.py), as in "<b>Mr Chin Harn Tong (Aljunied)</b>(<i>In Mandarin</i>):"
_LANGUAGE_NOTE_HTML = (
    r"(?:<[^>]*>)*\((?:\s|&nbsp;|<[^>]*>)*(?:in|dalam)\s+"
    r"(?:Mandar\w+|Malay|English|Tamil|Hokkien|Cantonese|Teochew|Hakka)"
    r"(?:\s|&nbsp;|<[^>]*>)*\)(?:<[^>]*>)*"
)
# NOTE: the older system prints "<b>Mr Speaker:</b>" and the newer "<strong>Mr Speaker</strong>:", or no colon in a question.
_LABEL_RE = re.compile(
    r"^(?P<prefix>(?:\s|&nbsp;|\d{1,3}[.\\]*|<(?!/?(?:b|strong)\b)[^>]*>)*)"
    r"<(?P<tag>b|strong)\b[^>]*>(?P<label>.*?)</(?P=tag)\s*>"
    r"(?P<colon>(?:\s|&nbsp;)*(?P<note>" + _LANGUAGE_NOTE_HTML + r"(?:\s|&nbsp;)*)?:)?",
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
_SPEAKER_OFFICE = "Speaker"
_DEPUTY_SPEAKER_OFFICE = "Deputy Speaker"
_CHAIR_OFFICES = (_SPEAKER_OFFICE, _DEPUTY_SPEAKER_OFFICE)
_WOMAN_PRINTED_FORMS_OF_ADDRESS = frozenset({"mdm", "madam"})
_CHAIRMAN_LABEL_RE = re.compile(r"^(?:The|Mr|Mdm|Madam)\s+Chairman$", re.IGNORECASE)
_SPEAKER_LABEL_RE = re.compile(r"^(?:Mr|Mdm|Madam)\s+Speaker$", re.IGNORECASE)
_DEPUTY_SPEAKER_LABEL_RE = re.compile(
    r"^(?:Mr|Mdm|Madam|The)\s+Deputy\s*Speaker$", re.IGNORECASE
)
_ARTICLE_OFFICE_LABEL_RE = re.compile(
    r"^(?:The|His Excellency the)\s+([^()]+)$", re.IGNORECASE
)
_PRINTED_FORM_OF_ADDRESS_RE = re.compile(r"^(Mr|Mdm|Madam)\b", re.IGNORECASE)
_MAX_CHAIR_LINE_LENGTH = 200
_CHAIR_EVENT_RE = re.compile(
    r"^[\[(]?(?:Thereupon\b|(?:Mr|Mdm|Madam)\s+(?:Deputy\s+)?Speaker\b).{0,150}?\b(?:left|took|resumed|vacated|assumed)\s+the\s+Chair\b",
    re.IGNORECASE,
)
_MPS_SPEAKING_TAG_RE = re.compile(
    r"^MPs? Speaking:.*\(\s*(?:Mr|Mdm|Madam)\s*(?:Deputy\s*)?Speaker\s*\)",
    re.IGNORECASE,
)
_PRESIDING_LABEL_RE = re.compile(
    r"^(?:Mr|Mdm|Madam|The)\s+(?:Deputy\s+)?Speaker\b", re.IGNORECASE
)
_SUSPENSION_RE = re.compile(
    r"Sitting (?:was |accordingly )?suspended|Sitting resumed|resumed at \d",
    re.IGNORECASE,
)
_LAST_MARK_PREFIX = "Last mark before the row: "
_BEFORE_ROW_LINE_PREFIX = "Between that mark and the row: "
_AFTER_ROW_LINE_PREFIX = "Between the row and the next mark: "
_FIRST_MARK_PREFIX = "First mark after the row: "
_LATER_CHANGE_PREFIX = "Later change of chair after the row: "
_SPRS_SEARCH_URL = "https://sprs.parl.gov.sg/search"
_SPRS3_TOPIC_URL = f"{_SPRS_SEARCH_URL}/#/sprs3topic"
_SPRS2_TOPIC_URL = f"{_SPRS_SEARCH_URL}/#/topic"
_NEWER_SYSTEM_ID_SUFFIX = "#"
_NO_CONTENT_NOTE = "No content"
_ERROR_ANSWER_NOTE = "Error answer"
_LIVE_CHECK_SEED = 20_261_114
_LIVE_CHECK_REPORT_COUNT = 50
_MAX_LIVE_CHECK_DIFFERENCES = 2
_PACKET_ID_LENGTH = 12
_PACKET_ID_LIMIT = 16**_PACKET_ID_LENGTH
_BATCH_PACKET_LIMIT = 50
_BATCH_CHARACTER_LIMIT = 80_000
_NO_LABEL_TEXT = "(none)"
_NO_PERSON_TEXT = "(none)"
_NO_END_DATE_TEXT = "no end date"
_NO_TABLE_ENTRY_TEXT = "No entry in the table."
_NO_CHAIR_MARK_TEXT = "No chair mark found."
_NOT_AVAILABLE_TEXT = "Not available."
_LIVE_CHECK_EQUAL_TEXT = (
    "Today's SPRS text equals the stored copy this packet is built from."
)
_LIVE_CHECK_DIFFERS_TEXT = (
    "Today's SPRS text differs from the stored copy this packet is built from."
)
_RECORDS_DIRECTORY_NAME = "records"
_BATCHES_DIRECTORY_NAME = "batches"
_PACKETS_FILE_NAME = "packets.json"
_BATCH_FILE_NAME = "packets.md"
_SONNET_DIRECTORY_NAME = "sonnet"
_OPUS_DIRECTORY_NAME = "opus"
_READER_DIRECTORY_NAMES = (_SONNET_DIRECTORY_NAME, _OPUS_DIRECTORY_NAME)
_BATCH_LEGEND = (
    "# Packets\n\n"
    "In text copied from the Official Report, <B>...</B> marks bold, <I>...</I> italic, "
    "<SUP>...</SUP> raised text and <SUB>...</SUB> lowered text. "
    "Snapshot text is shown as the database stores it, with its own markers."
)
_WORD_DIFFERENCES_LEGEND = (
    "A Word differences part numbers the differences the script found between "
    "the source text and the snapshot text, one per line."
)


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
    is_colon_in_label = label_text.endswith(":")
    # NOTE: a language note after a label that already holds its colon is the transcript's, as the parser reads it
    body_start = (
        label_match.start("colon")
        if is_colon_in_label and label_match.group("note") is not None
        else label_match.end()
    )
    rest_html = paragraph_html[body_start:]
    is_colon_printed = label_match.group("colon") is not None or is_colon_in_label
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
    is_preformatted = False
    for opening_tag, piece_html in zip([""] + pieces[1::2], pieces[0::2]):
        if _PREFORMATTED_OPENING_RE.match(opening_tag) is not None:
            is_preformatted = True
        elif _PREFORMATTED_CLOSING_RE.match(opening_tag) is not None:
            is_preformatted = False
        # NOTE: the parser keeps each line of a preformatted block (it joins only wrapped prose), so each line is a paragraph
        paragraph_htmls = (
            _LINE_BREAK_RE.split(piece_html) if is_preformatted else [piece_html]
        )
        for paragraph_html in paragraph_htmls:
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


def _get_run_placement(
    paragraphs: list[SourceParagraph],
    body_texts: list[str],
    turn_label_keys: list[str],
    next_row_text: Optional[str],
    row_label_key: str,
    run: SourceRun,
) -> tuple[bool, bool]:
    return (
        _is_followed_by_next_row(paragraphs, body_texts, run.last_index, next_row_text),
        turn_label_keys[run.first_index] == row_label_key,
    )


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
    next_row_text = (
        None if next_transcript is None else normalize_hand_check_text(next_transcript)
    )
    get_placement = partial(
        _get_run_placement,
        paragraphs,
        body_texts,
        turn_label_keys,
        next_row_text,
        row_label_key,
    )
    # NOTE: a short reply can repeat word for word, so the run whose next paragraph starts the next row wins, then the run under the row's own label.
    best_exact_run = max(exact_runs, key=get_placement, default=None)
    if best_exact_run is not None and any(get_placement(best_exact_run)):
        return SourceMatch(HandCheckMatchStatus.EXACT, best_exact_run)
    closest_run = _get_closest_run(
        row_text, body_texts, full_texts, turn_label_keys, row_label_key
    )
    # NOTE: a reply repeated under another label can be the only exact copy when the row's own paragraph also holds a line the parser cut into the next row, so a run under the row's own label wins over it
    is_closest_run_under_row_label = (
        closest_run is not None
        and turn_label_keys[closest_run.first_index] == row_label_key
    )
    if best_exact_run is not None and not is_closest_run_under_row_label:
        return SourceMatch(HandCheckMatchStatus.EXACT, best_exact_run)
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


@dataclass(frozen=True)
class ChairLine:
    text: str
    is_mark: bool
    report_title: str
    is_chair_change: bool = False


def _get_last_mark_index(chair_lines: list[ChairLine]) -> Optional[int]:
    for index in range(len(chair_lines) - 1, -1, -1):
        if chair_lines[index].is_mark:
            return index
    return None


def _has_chair_mark(chair_lines: list[ChairLine]) -> bool:
    return _get_last_mark_index(chair_lines) is not None


def _get_chair_line_text(chair_line: ChairLine) -> str:
    return f"{chair_line.text} (report: {chair_line.report_title})"


def get_chair_marks(
    before_lines: list[ChairLine], after_lines: list[ChairLine]
) -> list[str]:
    chair_marks = []
    last_mark_index = _get_last_mark_index(before_lines)
    if last_mark_index is not None:
        chair_marks.append(
            f"{_LAST_MARK_PREFIX}{_get_chair_line_text(before_lines[last_mark_index])}"
        )
        chair_marks.extend(
            f"{_BEFORE_ROW_LINE_PREFIX}{_get_chair_line_text(chair_line)}"
            for chair_line in before_lines[last_mark_index + 1 :]
        )
    first_mark_index = next(
        (index for index, chair_line in enumerate(after_lines) if chair_line.is_mark),
        None,
    )
    if first_mark_index is not None:
        first_mark = after_lines[first_mark_index]
        chair_marks.extend(
            f"{_AFTER_ROW_LINE_PREFIX}{_get_chair_line_text(chair_line)}"
            for chair_line in after_lines[:first_mark_index]
        )
        first_mark_prefix = (
            _LATER_CHANGE_PREFIX if first_mark.is_chair_change else _FIRST_MARK_PREFIX
        )
        chair_marks.append(f"{first_mark_prefix}{_get_chair_line_text(first_mark)}")
    return chair_marks


def get_label_office(label: str) -> Optional[str]:
    if _CHAIRMAN_LABEL_RE.match(label) is not None:
        return None
    if _SPEAKER_LABEL_RE.match(label) is not None:
        return _SPEAKER_OFFICE
    if _DEPUTY_SPEAKER_LABEL_RE.match(label) is not None:
        return _DEPUTY_SPEAKER_OFFICE
    article_match = _ARTICLE_OFFICE_LABEL_RE.match(label)
    if article_match is None:
        return None
    return _WHITESPACE_RE.sub(" ", article_match.group(1)).strip()


def get_office_holders_on(
    office: str, sitting_day: date, office_holders: list[HandCheckOfficeHolder]
) -> list[HandCheckOfficeHolder]:
    return [
        office_holder
        for office_holder in office_holders
        if office_holder.office.casefold() == office.casefold()
        and office_holder.first_day <= sitting_day
        and (office_holder.last_day is None or sitting_day <= office_holder.last_day)
    ]


def _get_printed_form_of_address(label: str) -> Optional[HandCheckFormOfAddress]:
    printed_match = _PRINTED_FORM_OF_ADDRESS_RE.match(label)
    if printed_match is None:
        return None
    if printed_match.group(1).casefold() in _WOMAN_PRINTED_FORMS_OF_ADDRESS:
        return HandCheckFormOfAddress.MDM
    return HandCheckFormOfAddress.MR


def is_chair_label(
    label: str, sitting_day: date, office_holders: list[HandCheckOfficeHolder]
) -> bool:
    if _CHAIRMAN_LABEL_RE.match(label) is not None:
        return True
    if get_label_office(label) != _DEPUTY_SPEAKER_OFFICE:
        return False
    deputy_speakers = get_office_holders_on(
        _DEPUTY_SPEAKER_OFFICE, sitting_day, office_holders
    )
    form_of_address = _get_printed_form_of_address(label)
    if form_of_address is not None:
        deputy_speakers = [
            deputy_speaker
            for deputy_speaker in deputy_speakers
            if deputy_speaker.form_of_address == form_of_address
        ]
    return len(deputy_speakers) > 1


def get_chair_lines(
    paragraphs: list[SourceParagraph],
    report_title: str,
    sitting_day: date,
    office_holders: list[HandCheckOfficeHolder],
) -> list[ChairLine]:
    chair_lines = []
    for paragraph in paragraphs:
        if paragraph.label is not None:
            is_mark = _PRESIDING_LABEL_RE.match(
                paragraph.label
            ) is not None and not is_chair_label(
                paragraph.label, sitting_day, office_holders
            )
            if is_mark:
                chair_lines.append(ChairLine(f"{paragraph.label}:", True, report_title))
            continue
        text = normalize_hand_check_text(paragraph.full_html)
        if _MPS_SPEAKING_TAG_RE.match(text) is not None:
            chair_lines.append(
                ChairLine(render_source_html(paragraph.full_html), True, report_title)
            )
            continue
        # NOTE: the newer system wraps a whole procedural line in "[(proc text) ... (proc text)]" (register line 33), so the chair patterns read the line inside
        unwrapped_text = text.removeprefix(PROC_TEXT_OPEN_TAG).removesuffix(
            PROC_TEXT_CLOSE_TAG
        )
        if len(unwrapped_text) > _MAX_CHAIR_LINE_LENGTH:
            continue
        if _CHAIR_NOTE_RE.match(unwrapped_text) is not None:
            chair_lines.append(
                ChairLine(text, True, report_title, is_chair_change=True)
            )
            continue
        if _CHAIR_EVENT_RE.match(unwrapped_text) is not None:
            chair_lines.append(
                ChairLine(text, True, report_title, is_chair_change=True)
            )
            continue
        if _SUSPENSION_RE.search(unwrapped_text) is not None:
            chair_lines.append(ChairLine(text, False, report_title))
    return chair_lines


def get_role_section(
    label: str, sitting_day: date, office_holders: list[HandCheckOfficeHolder]
) -> Optional[HandCheckRoleSection]:
    if is_chair_label(label, sitting_day, office_holders):
        return HandCheckRoleSection(
            is_chair_label=True,
            office=None,
            office_holders=[
                office_holder
                for chair_office in _CHAIR_OFFICES
                for office_holder in get_office_holders_on(
                    chair_office, sitting_day, office_holders
                )
            ],
            chair_marks=[],
        )
    office = get_label_office(label)
    if office is None:
        return None
    return HandCheckRoleSection(
        is_chair_label=False,
        office=office,
        office_holders=get_office_holders_on(office, sitting_day, office_holders),
        chair_marks=[],
    )


# NOTE: this repeats get_official_record_url in the site's api/utils/official_record.py, and the site has no test of it. Change the two together.
def get_official_record_url(
    report_id: str, report_version: str, html_file_name: Optional[str]
) -> str:
    if report_version == ReportVersion.SPRS3:
        return f"{_SPRS3_TOPIC_URL}?reportid={quote(report_id.rstrip(_NEWER_SYSTEM_ID_SUFFIX), safe='')}"
    if html_file_name is None:
        return _SPRS_SEARCH_URL
    return f"{_SPRS2_TOPIC_URL}?reportid={quote(html_file_name, safe='')}"


@dataclass(frozen=True)
class TopicAnswer:
    status: HandCheckAnswerStatus
    text: Optional[str]
    note: str


def classify_topic_answer(
    hansard_topic_response: HansardTopicResponse, report_version: str
) -> TopicAnswer:
    if hansard_topic_response.error_code is not None:
        return TopicAnswer(
            HandCheckAnswerStatus.ERROR,
            None,
            f"{_ERROR_ANSWER_NOTE} {hansard_topic_response.error_code}: {hansard_topic_response.description}",
        )
    text = get_topic_html_content(hansard_topic_response, report_version)
    if text is None:
        return TopicAnswer(HandCheckAnswerStatus.NO_CONTENT, None, _NO_CONTENT_NOTE)
    if text == "":
        return TopicAnswer(HandCheckAnswerStatus.NO_CONTENT, None, _NO_CONTENT_NOTE)
    return TopicAnswer(HandCheckAnswerStatus.TEXT, text, "")


@dataclass(frozen=True)
class LiveCheck:
    status: HandCheckLiveCheckStatus
    live_paragraphs: list[SourceParagraph]


def get_live_check_hansard_report_ids(hansard_report_ids: list[str]) -> list[str]:
    distinct_hansard_report_ids = sorted(set(hansard_report_ids))
    return random.Random(_LIVE_CHECK_SEED).sample(
        distinct_hansard_report_ids,
        min(_LIVE_CHECK_REPORT_COUNT, len(distinct_hansard_report_ids)),
    )


def get_live_check(live_text: str, stored_text: str) -> LiveCheck:
    if live_text == stored_text:
        return LiveCheck(HandCheckLiveCheckStatus.EQUAL, [])
    return LiveCheck(
        HandCheckLiveCheckStatus.DIFFERS, split_source_paragraphs(live_text)
    )


def validate_can_build_after_live_check(
    hansard_report_id_to_live_check: dict[str, LiveCheck],
) -> None:
    differing_hansard_report_ids = sorted(
        hansard_report_id
        for hansard_report_id, live_check in hansard_report_id_to_live_check.items()
        if live_check.status == HandCheckLiveCheckStatus.DIFFERS
    )
    if len(differing_hansard_report_ids) <= _MAX_LIVE_CHECK_DIFFERENCES:
        return
    logger.error(
        f"Reports whose live SPRS text differs from the stored copy: {', '.join(differing_hansard_report_ids)}"
    )
    raise HansardHandCheckError(
        f"{len(differing_hansard_report_ids)} of {len(hansard_report_id_to_live_check)} live-checked reports differ from the stored copy, and {_MAX_LIVE_CHECK_DIFFERENCES} is the most the build allows"
    )


def get_validated_stored_texts(
    hansard_report_ids: list[str], reports: list[Report]
) -> dict[str, str]:
    hansard_report_id_to_stored_text = {
        report.report_id: report.content
        for report in reports
        if report.content is not None and report.content != ""
    }
    missing_hansard_report_ids = [
        hansard_report_id
        for hansard_report_id in hansard_report_ids
        if hansard_report_id not in hansard_report_id_to_stored_text
    ]
    if missing_hansard_report_ids:
        raise HansardHandCheckError(
            f"Stored text is missing or empty for {len(missing_hansard_report_ids)} of {len(hansard_report_ids)} reports: {', '.join(missing_hansard_report_ids)}"
        )
    return hansard_report_id_to_stored_text


def get_packet_ids(count: int) -> list[str]:
    return [
        f"{packet_number:0{_PACKET_ID_LENGTH}x}"
        for packet_number in secrets.SystemRandom().sample(
            range(_PACKET_ID_LIMIT), count
        )
    ]


def get_earlier_reports(sitting_reports: list[Report], report: Report) -> list[Report]:
    # NOTE: speech_number alone is not reliable for every row (data dictionary line 42), so equal numbers fall back to the SPRS report id
    report_order = (report.speech_number, report.report_id)
    return sorted(
        (
            sitting_report
            for sitting_report in sitting_reports
            if (sitting_report.speech_number, sitting_report.report_id) < report_order
        ),
        key=lambda earlier_report: (
            earlier_report.speech_number,
            earlier_report.report_id,
        ),
        reverse=True,
    )


def _get_packet_word_differences(
    source_match: SourceMatch,
    matched_source_html: str,
    context_paragraphs: list[str],
    snapshot_row: HandCheckSnapshotRow,
) -> list[HandCheckWordDifference]:
    if source_match.run is None:
        return []
    return [
        HandCheckWordDifference(
            operation=word_difference.operation,
            source_words=word_difference.source_words,
            row_words=word_difference.row_words,
            kind=word_difference.kind,
        )
        for word_difference in get_word_differences(
            matched_source_html,
            snapshot_row.transcript,
            RowContext(
                speaker=snapshot_row.speaker,
                turn_first_paragraph=next(iter(context_paragraphs), None),
                next_speaker=snapshot_row.next_speaker,
                next_transcript=snapshot_row.next_transcript,
            ),
        )
    ]


def _get_row_role_section(
    snapshot_row: HandCheckSnapshotRow,
    paragraphs: list[SourceParagraph],
    source_match: SourceMatch,
    office_holders: list[HandCheckOfficeHolder],
    earlier_chair_lines: list[ChairLine],
) -> Optional[HandCheckRoleSection]:
    if snapshot_row.speaker is None:
        return None
    sitting_day = snapshot_row.sitting_date.date()
    role_section = get_role_section(snapshot_row.speaker, sitting_day, office_holders)
    if role_section is None:
        return None
    if not role_section.is_chair_label:
        return role_section
    if source_match.run is None:
        return role_section
    own_before_lines = get_chair_lines(
        paragraphs[: source_match.run.first_index],
        snapshot_row.report_title,
        sitting_day,
        office_holders,
    )
    before_lines = (
        own_before_lines
        if _has_chair_mark(own_before_lines)
        else [*earlier_chair_lines, *own_before_lines]
    )
    after_lines = get_chair_lines(
        paragraphs[source_match.run.last_index + 1 :],
        snapshot_row.report_title,
        sitting_day,
        office_holders,
    )
    return role_section.model_copy(
        update={"chair_marks": get_chair_marks(before_lines, after_lines)}
    )


def build_packet(
    packet_id: str,
    snapshot_row: HandCheckSnapshotRow,
    paragraphs: list[SourceParagraph],
    live_check: Optional[LiveCheck],
    office_holders: list[HandCheckOfficeHolder],
    earlier_chair_lines: list[ChairLine],
) -> HandCheckPacket:
    source_match = get_source_match(
        paragraphs,
        snapshot_row.speaker,
        snapshot_row.transcript,
        snapshot_row.next_transcript,
    )
    matched_source_html = get_matched_source_html(paragraphs, source_match)
    context_paragraphs = get_context_paragraphs(paragraphs, source_match)
    return HandCheckPacket(
        packet_id=packet_id,
        snapshot=snapshot_row,
        official_record_url=get_official_record_url(
            snapshot_row.hansard_report_id,
            snapshot_row.report_version,
            snapshot_row.html_file_name,
        ),
        match_status=source_match.status,
        matched_source_html=matched_source_html,
        context_paragraphs=context_paragraphs,
        after_paragraph=get_after_paragraph(paragraphs, source_match),
        word_differences=_get_packet_word_differences(
            source_match, matched_source_html, context_paragraphs, snapshot_row
        ),
        gap_check=(
            None
            if source_match.run is None
            else get_gap_check(
                paragraphs, source_match.run.last_index, snapshot_row.next_transcript
            )
        ),
        role_section=_get_row_role_section(
            snapshot_row, paragraphs, source_match, office_holders, earlier_chair_lines
        ),
        live_check_status=None if live_check is None else live_check.status,
        live_match_status=(
            get_source_match(
                live_check.live_paragraphs,
                snapshot_row.speaker,
                snapshot_row.transcript,
                snapshot_row.next_transcript,
            ).status
            if live_check is not None
            and live_check.status == HandCheckLiveCheckStatus.DIFFERS
            else None
        ),
    )


def _get_match_status_text(match_status: HandCheckMatchStatus) -> str:
    return match_status.value.replace("_", " ").lower()


def _get_office_holder_lines(office_holders: list[HandCheckOfficeHolder]) -> list[str]:
    if not office_holders:
        return [_NO_TABLE_ENTRY_TEXT]
    return [
        f"- {office_holder.holder} ({office_holder.form_of_address}), "
        f"{office_holder.first_day.isoformat()} to "
        f"{_NO_END_DATE_TEXT if office_holder.last_day is None else office_holder.last_day.isoformat()}, "
        f"source {office_holder.source_url}"
        for office_holder in office_holders
    ]


def _get_role_section_lines(role_section: HandCheckRoleSection) -> list[str]:
    if role_section.is_chair_label:
        return [
            "",
            "### Role section",
            "Chair label. Table entries for the Speaker and the Deputy Speaker on the sitting date:",
            *_get_office_holder_lines(role_section.office_holders),
            "Chair marks:",
            *(
                [f"- {chair_mark}" for chair_mark in role_section.chair_marks]
                if role_section.chair_marks
                else [_NO_CHAIR_MARK_TEXT]
            ),
        ]
    return [
        "",
        "### Role section",
        f"Office label: {role_section.office}. Table entries for that office on the sitting date:",
        *_get_office_holder_lines(role_section.office_holders),
    ]


def _get_gap_check_lines(gap_check: Optional[HandCheckGapCheck]) -> list[str]:
    if gap_check is None:
        return [_NOT_AVAILABLE_TEXT]
    return [
        f"The next source paragraph starts the next row: {'yes' if gap_check.is_next_row else 'no'}",
        *(
            [
                f"Skipped, as the site gives them no row: {' | '.join(gap_check.skipped_paragraphs)}"
            ]
            if gap_check.skipped_paragraphs
            else []
        ),
        *(
            []
            if gap_check.next_source_text is None
            else [f"Next source paragraph: {gap_check.next_source_text}"]
        ),
    ]


def _get_word_difference_lines(packet: HandCheckPacket) -> list[str]:
    if (
        packet.match_status != HandCheckMatchStatus.INEXACT
        or not packet.word_differences
    ):
        return []
    return [
        "",
        "### Word differences",
        *(
            f'{number}. {word_difference.operation}: source "{word_difference.source_words}", snapshot "{word_difference.row_words}"'
            for number, word_difference in enumerate(packet.word_differences, 1)
        ),
    ]


def _get_live_check_text_lines(
    live_check_status: HandCheckLiveCheckStatus,
    live_match_status: Optional[HandCheckMatchStatus],
) -> list[str]:
    if live_check_status == HandCheckLiveCheckStatus.EQUAL:
        return [_LIVE_CHECK_EQUAL_TEXT]
    match_status = (
        HandCheckMatchStatus.NOT_FOUND
        if live_match_status is None
        else live_match_status
    )
    return [
        _LIVE_CHECK_DIFFERS_TEXT,
        f"Against today's SPRS text the match status is {_get_match_status_text(match_status)}.",
    ]


def render_packet(packet: HandCheckPacket, is_for_sonnet: bool) -> str:
    snapshot_row = packet.snapshot
    lines = [
        f"## Packet {packet.packet_id}",
        "",
        "### Label and credited person",
        f"Label: {_NO_LABEL_TEXT if snapshot_row.speaker is None else snapshot_row.speaker}",
        f"Credited to: {snapshot_row.speaker_name}",
        f"Linked person: {_NO_PERSON_TEXT if snapshot_row.person_name is None else snapshot_row.person_name}",
        "",
        "### Report",
        snapshot_row.report_title,
        f"Sitting date: {snapshot_row.sitting_date.day} {snapshot_row.sitting_date:%B %Y}",
        f"Report type: {snapshot_row.report_type}",
        "",
        "### Snapshot text",
        snapshot_row.transcript,
        "",
        "### Context",
        *(
            [
                f"- {context_paragraph}"
                for context_paragraph in packet.context_paragraphs
            ]
            if packet.context_paragraphs
            else [_NOT_AVAILABLE_TEXT]
        ),
        *(
            []
            if packet.after_paragraph is None
            else [f"After the paragraph: {packet.after_paragraph}"]
        ),
        "",
        "### Match status and Matched source",
        f"Status: {_get_match_status_text(packet.match_status)}",
        *(
            [render_source_html(packet.matched_source_html)]
            if packet.matched_source_html != ""
            else []
        ),
        *(_get_word_difference_lines(packet) if is_for_sonnet else []),
        "",
        "### Gap check",
        *_get_gap_check_lines(packet.gap_check),
        *(
            []
            if packet.role_section is None
            else _get_role_section_lines(packet.role_section)
        ),
        "",
        "### Official record link",
        packet.official_record_url,
        *(
            []
            if packet.live_check_status is None
            else [
                "",
                "### Live check note",
                *_get_live_check_text_lines(
                    packet.live_check_status, packet.live_match_status
                ),
            ]
        ),
    ]
    return "\n".join(lines)


def get_batches(rendered_packets: list[str]) -> list[list[str]]:
    batches = []
    batch: list[str] = []
    batch_length = 0
    for rendered_packet in rendered_packets:
        if batch and (
            len(batch) == _BATCH_PACKET_LIMIT
            or batch_length + len(rendered_packet) > _BATCH_CHARACTER_LIMIT
        ):
            batches.append(batch)
            batch = []
            batch_length = 0
        batch.append(rendered_packet)
        batch_length += len(rendered_packet)
    if batch:
        batches.append(batch)
    return batches


def render_batch(rendered_packets: list[str], is_for_sonnet: bool) -> str:
    legend = (
        f"{_BATCH_LEGEND} {_WORD_DIFFERENCES_LEGEND}"
        if is_for_sonnet
        else _BATCH_LEGEND
    )
    return "\n\n".join([legend, *rendered_packets]) + "\n"


def write_hand_check_packets(
    packets: list[HandCheckPacket], output_directory: Path
) -> dict[str, int]:
    output_directory.mkdir(parents=True)
    records_directory = output_directory / _RECORDS_DIRECTORY_NAME
    records_directory.mkdir()
    (records_directory / _PACKETS_FILE_NAME).write_text(
        HandCheckPackets(packets).model_dump_json(indent=1), encoding="utf-8"
    )
    shuffled_packets = list(packets)
    secrets.SystemRandom().shuffle(shuffled_packets)
    directory_name_to_batch_count: dict[str, int] = {}
    for reader_directory_name in _READER_DIRECTORY_NAMES:
        is_for_sonnet = reader_directory_name == _SONNET_DIRECTORY_NAME
        batches = get_batches(
            [render_packet(packet, is_for_sonnet) for packet in shuffled_packets]
        )
        for batch_number, batch in enumerate(batches, 1):
            batch_directory = (
                output_directory
                / _BATCHES_DIRECTORY_NAME
                / reader_directory_name
                / f"batch-{batch_number:03d}"
            )
            batch_directory.mkdir(parents=True)
            (batch_directory / _BATCH_FILE_NAME).write_text(
                render_batch(batch, is_for_sonnet), encoding="utf-8"
            )
        directory_name_to_batch_count[reader_directory_name] = len(batches)
    return directory_name_to_batch_count


def _fetch_live_text(snapshot_row: HandCheckSnapshotRow) -> str:
    topic_id = get_topic_id(
        snapshot_row.hansard_report_id,
        snapshot_row.html_file_name,
        snapshot_row.report_version,
    )
    logger.info(f"Fetching live SPRS topic {topic_id}")
    try:
        topic_answer = classify_topic_answer(
            get_hansard_topic_response(topic_id), snapshot_row.report_version
        )
    except HansardGatewayError as error:
        raise HansardHandCheckError(
            f"The live check request failed for {snapshot_row.hansard_report_id}"
        ) from error
    if topic_answer.text is None:
        raise HansardHandCheckError(
            f"The live check answer for {snapshot_row.hansard_report_id} holds no text ({topic_answer.status}): {topic_answer.note}"
        )
    return topic_answer.text


@dataclass(frozen=True)
class EarlierText:
    title: str
    html: str


# NOTE: the sections run in the order of the sitting, which speech_number does not on every day, and a report whose text no section equals falls back to speech_number order
def get_earlier_section_texts(
    sitting_sections: list[HansardReportSection], report_html: str
) -> Optional[list[EarlierText]]:
    section_indexes = [
        index
        for index, sitting_section in enumerate(sitting_sections)
        if sitting_section.content == report_html
    ]
    if len(section_indexes) != 1:
        return None
    return [
        EarlierText((sitting_section.title or "").strip(), sitting_section.content)
        for sitting_section in reversed(sitting_sections[: section_indexes[0]])
        if sitting_section.content is not None
    ]


def get_earlier_chair_lines(
    earlier_texts: list[EarlierText],
    sitting_day: date,
    office_holders: list[HandCheckOfficeHolder],
) -> list[ChairLine]:
    chair_lines: list[ChairLine] = []
    for earlier_text in earlier_texts:
        earlier_lines = get_chair_lines(
            split_source_paragraphs(earlier_text.html),
            earlier_text.title,
            sitting_day,
            office_holders,
        )
        chair_lines = [*earlier_lines, *chair_lines]
        if _has_chair_mark(earlier_lines):
            break
    return chair_lines


def _get_earlier_texts(session: Session, report: Report) -> list[EarlierText]:
    if report.report_version == ReportVersion.SPRS3 and report.content is not None:
        section_rows = CRUDSitting(
            session
        ).get_date_sections_rows_by_sitting_dates_and_sections_not_null(
            [get_sitting_date_key(report.sitting_date)]
        )
        for section_row in section_rows:
            sitting_sections = [
                HansardReportSection.model_validate(raw_section)
                for raw_section in json.loads(section_row.sections)
            ]
            earlier_section_texts = get_earlier_section_texts(
                sitting_sections, report.content
            )
            if earlier_section_texts is not None:
                return earlier_section_texts
    return [
        EarlierText(earlier_report.title, earlier_report.content)
        for earlier_report in get_earlier_reports(
            CRUDReport(session).get_by_sitting_dates([report.sitting_date]), report
        )
        if earlier_report.content is not None
    ]


def _has_chair_label_row(
    snapshot_rows: list[HandCheckSnapshotRow],
    office_holders: list[HandCheckOfficeHolder],
) -> bool:
    return any(
        snapshot_row.speaker is not None
        and is_chair_label(
            snapshot_row.speaker,
            snapshot_row.sitting_date.date(),
            office_holders,
        )
        for snapshot_row in snapshot_rows
    )


def build_hand_check_packets(
    snapshot_path: Path,
    plants_path: Optional[Path],
    output_directory: Path,
) -> None:
    sample_rows = HandCheckSnapshot.model_validate_json(
        snapshot_path.read_text(encoding="utf-8")
    ).rows
    plant_rows = (
        []
        if plants_path is None
        else HandCheckSnapshotRows.model_validate_json(
            plants_path.read_text(encoding="utf-8")
        ).root
    )
    snapshot_rows = [*sample_rows, *plant_rows]
    hansard_report_id_to_rows: dict[str, list[HandCheckSnapshotRow]] = {}
    for snapshot_row in snapshot_rows:
        hansard_report_id_to_rows.setdefault(snapshot_row.hansard_report_id, []).append(
            snapshot_row
        )
    speech_id_to_packet_id = dict(
        zip(
            (snapshot_row.speech_id for snapshot_row in snapshot_rows),
            get_packet_ids(len(snapshot_rows)),
        )
    )
    office_holders = get_hand_check_office_holders()
    with Session(build_read_only_engine(settings.database_url)) as session:
        reports = CRUDReport(session).get_by_ids(
            sorted({snapshot_row.report_id for snapshot_row in snapshot_rows})
        )
        hansard_report_id_to_stored_text = get_validated_stored_texts(
            list(hansard_report_id_to_rows), reports
        )
        hansard_report_id_to_earlier_chair_lines = {
            report.report_id: get_earlier_chair_lines(
                _get_earlier_texts(session, report),
                report.sitting_date.date(),
                office_holders,
            )
            for report in reports
            if _has_chair_label_row(
                hansard_report_id_to_rows[report.report_id], office_holders
            )
        }
    hansard_report_id_to_live_check = {
        hansard_report_id: get_live_check(
            _fetch_live_text(hansard_report_id_to_rows[hansard_report_id][0]),
            hansard_report_id_to_stored_text[hansard_report_id],
        )
        for hansard_report_id in get_live_check_hansard_report_ids(
            [snapshot_row.hansard_report_id for snapshot_row in sample_rows]
        )
    }
    validate_can_build_after_live_check(hansard_report_id_to_live_check)
    packets: list[HandCheckPacket] = []
    for hansard_report_id, report_snapshot_rows in hansard_report_id_to_rows.items():
        paragraphs = split_source_paragraphs(
            hansard_report_id_to_stored_text[hansard_report_id]
        )
        packets.extend(
            build_packet(
                speech_id_to_packet_id[snapshot_row.speech_id],
                snapshot_row,
                paragraphs,
                hansard_report_id_to_live_check.get(hansard_report_id),
                office_holders,
                hansard_report_id_to_earlier_chair_lines.get(hansard_report_id, []),
            )
            for snapshot_row in report_snapshot_rows
        )

    directory_name_to_batch_count = write_hand_check_packets(packets, output_directory)

    match_status_to_count = Counter(packet.match_status for packet in packets)
    for match_status in HandCheckMatchStatus:
        logger.info(
            f"{match_status.value}: {match_status_to_count[match_status]} packets"
        )
    live_check_status_to_count = Counter(
        live_check.status for live_check in hansard_report_id_to_live_check.values()
    )
    for directory_name, batch_count in directory_name_to_batch_count.items():
        logger.info(f"{batch_count} batches for {directory_name}")
    logger.info(
        f"stored copy matched live SPRS in {live_check_status_to_count[HandCheckLiveCheckStatus.EQUAL]} of {len(hansard_report_id_to_live_check)}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build the human hand check's reader packets from a snapshot and the stored SPRS answers, read only, check a seeded 50 of the sampled reports against today's SPRS, and write the packet records and the shuffled reader batches"
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        required=True,
        help="the draw's snapshot.json, such as plans/hand-check/main/snapshot.json",
    )
    parser.add_argument(
        "--plants",
        type=Path,
        help="the plants file of the round being read; its rows are packed with the snapshot's",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="write records/packets.json and the batches/sonnet and batches/opus trees here; the directory must not exist yet",
    )
    arguments = parser.parse_args()
    build_hand_check_packets(
        arguments.snapshot,
        arguments.plants,
        arguments.output_directory,
    )

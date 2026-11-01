import html
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional
from urllib.parse import quote

from enums import HandCheckFormOfAddress, HandCheckMatchStatus, ReportVersion
from schemas.hand_check_office_holder import HandCheckOfficeHolder
from schemas.hand_check_packet import HandCheckGapCheck, HandCheckRoleSection
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
    r"Sitting (?:was )?suspended|Sitting resumed|resumed at \d", re.IGNORECASE
)
_LAST_MARK_PREFIX = "Last mark before the row: "
_BEFORE_ROW_LINE_PREFIX = "Between that mark and the row: "
_AFTER_ROW_LINE_PREFIX = "Between the row and the next mark: "
_FIRST_MARK_PREFIX = "First mark after the row: "
_SPRS_SEARCH_URL = "https://sprs.parl.gov.sg/search"
_SPRS3_TOPIC_URL = f"{_SPRS_SEARCH_URL}/#/sprs3topic"
_SPRS2_TOPIC_URL = f"{_SPRS_SEARCH_URL}/#/topic"
_NEWER_SYSTEM_ID_SUFFIX = "#"


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


@dataclass(frozen=True)
class ChairLine:
    text: str
    is_mark: bool
    report_title: str


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
        chair_marks.extend(
            f"{_AFTER_ROW_LINE_PREFIX}{_get_chair_line_text(chair_line)}"
            for chair_line in after_lines[:first_mark_index]
        )
        chair_marks.append(
            f"{_FIRST_MARK_PREFIX}{_get_chair_line_text(after_lines[first_mark_index])}"
        )
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
        if len(text) > _MAX_CHAIR_LINE_LENGTH:
            continue
        if _CHAIR_NOTE_RE.match(text) is not None:
            chair_lines.append(ChairLine(text, True, report_title))
            continue
        if _CHAIR_EVENT_RE.match(text) is not None:
            chair_lines.append(ChairLine(text, True, report_title))
            continue
        if _SUSPENSION_RE.search(text) is not None:
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

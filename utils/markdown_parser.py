import re
from collections import Counter
from html.entities import html5

import html2text

from enums import ReportVersion
from utils.text import fix_mojibake

_MAX_ADJOURNMENT_CONTINUATIONS = 6
_BOLD_MARKER = "**"
_BOLD_MARKER_LENGTH = len(_BOLD_MARKER)
_EMPHASIS_MARK = "_"
_EMPHASIS_MARKER_LENGTH = len(_EMPHASIS_MARK)
_EMPTY_ITALIC_LINE = "__"
_ONE_COLUMN_TABLE_SEPARATOR_LINE = "---|---"
_PERIOD = "."
_PERIOD_THEN_EMPHASIS_MARK = _PERIOD + _EMPHASIS_MARK
_OPENING_BRACKET = "["
_HYPHEN = "-"
_CLOSING_BRACKET = "]"
_COLUMN_MARKER_PATTERN = r"Column(?:\s+No)?\s*:\s*\d+"
_PAGE_TEXT_PATTERN = r"Page:\s*\d+"
_PAGE_BREAK_SENTINEL = "\ue000"
_PARAGRAPH_MARKER_PATTERN = (
    r"</?p\b[^>]*>\s*(?:<span[^>]*>)?\s*(?:" + _COLUMN_MARKER_PATTERN + "|" + _PAGE_TEXT_PATTERN + r")\s*(?:</span>)?\s*</?p\b[^>]*>"
)
_SENTENCE_END_PATTERN = r"[.?!:][\"'\u201d\u2019)\]*_\s]*$"
_NON_SPEECH_BLOCK_PATTERN = r"^(#{1,6}|\* \* \*|!\[)"
_STAGE_DIRECTION_END_PATTERN = r"[\]_*]\s*$"
_EMPHASIS_START_PATTERN = r"^\s*[_*]"
_COLUMN_RANGE_LINE_PATTERN = r"\*Cols?\."
_TIME_OF_DAY_LINE_PATTERN = r"\d{1,2}[.:]\d{2}\s*[ap]m\s*"
_HYPHENATED_FRAGMENT_PATTERN = r"[A-Za-z]-$"
_LIST_ITEM_START_PATTERN = r"^\s*(?:\(\s*(?:[a-z]{1,3}|[ivxl]{1,5}|[A-Z]|\d{1,2})\s*\)|\d{1,3}[.)])\s+\S"
_PERSON_NAME_LINE_PATTERN = r"^(?:Mr|Mrs|Ms|Miss|Mdm|Madam|Dr|Prof|Assoc Prof|Assoc\. Prof|Er|Encik|Inche|Haji|Tuan|Che|BG|RAdm|COL|LG|MG)\.? [A-Z][^.?!:;]{2,60}$"
_MAX_NAME_LINE_WORDS = 12
_PAGE_BREAK_ARTIFACT_PATTERN = r"   \n  \n\*\*\*\*  \n  \n"
_TWO_SPACE_PAGE_BREAK_ARTIFACT_PATTERN = r"^([^\n|]*[^\s.?!:;\"'\u201d\u2019)\]_*|])  \n  \n\*\*\*\*  \n  \n"
_BOLD_ONLY_LINE_PATTERN = r"\*\*[^\n*].*\*\*"
_SPLIT_BOLD_LABEL_PATTERN = r"(\*\*[^\n*][^\n*]*\([^)\n*]*)\*\*\n(?:\*\*\n)?([^*\n]*\))\*\*"
_CONCATENATED_PART_PATTERN = r"\bPART([IVX]+)OF\b"
_CONCATENATED_VOLUME_PATTERN = r"\bVOLUME(\d+)\b"
_TABLE_SEPARATOR_LINE_PATTERN = r"-{3}\s*"
_ASTERISK_ONLY_LINE_PATTERN = r"\*+\s*"
_LEADING_EMPTY_BOLD_PATTERN = r"^(\*{4})+"
_TRAILING_EMPTY_BOLD_PATTERN = r"(\*{4})+$"
_LEADING_NESTED_BOLD_PATTERN = r"^\*{4}([^*\n]+)\*\*([^*\n]+)\*\*"
_ADJOURNMENT_LINE_PATTERN = r"Adjourned accordingly at"
_SPLIT_DIRECTION_LINE_PATTERN = r"_?(?:Adjourned accordingly|(?:Sitting|Debate) (?:accordingly )?suspended)"
_DIRECTION_START_PATTERN = r"_?(?:Adjourned|Sitting|Debate)\b"
_ALPHANUMERIC_PATTERN = r"[A-Za-z0-9]"
_TIME_ABBREVIATION_END_PATTERN = r"[ap]\.m\.[\"')\]*_\s]*$"
_BLOCK_START_PATTERN = r"^(\*\*|#{1,6}|\* \* \*)"
_BYTE_ORDER_MARK = "\ufeff"
_NBSP_ENTITY = "&nbsp;"
_STRAY_CLOSING_TAG = "</p />"
_STRAY_OPENING_ANGLE = "<"
_STRAY_HEAD_TAG_PATTERN = r"<(head)(?=\s)"
_ESCAPED_OPENING_ANGLE = "&lt;"
_FOOTNOTE_HASH_MARKER_PATTERN = r"#(?:&nbsp;)+(</sup>)?\s*"
_SUPERSCRIPT_FOOTNOTE_PATTERN = r"<sup\b[^>]*>\s*(?:<a\b[^>]*>)?\s*(\d{1,3}(?:\s*,\s*\d{1,3})*)\s*(?:</a>)?\s*</sup>"
_HTML_TAG_PATTERN = r"<[^>]*>"
_BLOCK_TAG_PATTERN = r"</?(?:p|div|br|li|ul|ol|h[1-6]|table|tr|td|th|hr|blockquote|pre)\b[^>]*>"
_PRECEDING_HTML_LENGTH = 600
_EXPONENT_BASE_PATTERN = r"(?:^|[^A-Za-z])(?:[A-Za-z]|CO|NO|SO|km|cm|mm)$"
_LIST_COMMA_PATTERN = r"\s*,\s*"
_CLOSING_EMPHASIS_END_PATTERN = r"</(?:i|em|u|b|strong)\s*>$"
_ANCHOR_TAG_PATTERN = r"<a\b"
_AMPERSAND_PATTERN = r"&([A-Za-z][A-Za-z0-9]*|#)?"
_AMPERSAND_ENTITY = "&amp;"
_NBSP_ONLY_EMPHASIS_PATTERN = r"<(i|b|u|em|strong)\b[^>]*>\s*(?:&nbsp;\s*)+</\1\s*>"
_EMPTY_EMPHASIS_PATTERN = r"<(strong|em)[^>]*>(\s|&nbsp;|\ufeff)*</\1>"
_PROC_TEXT_PAIR_PATTERN = r"\[\s*\(proc text\)\s*(.*?)\s*\(proc text\)\s*\]"
_PROC_TEXT_LONE_PATTERN = r"\[?\s*\(proc text\)\s*\]?"
_PROC_TEXT_BLOCK_PATTERN = (
    r"(<(p|h[1-6])\b[^>]*>(?:\s|&nbsp;|<(?:span|em|strong|b|i|u)\b[^>]*>)*)"
    r"\[\s*\(proc text\)\s*((?:(?!\(proc text\)|</?(?:p|h[1-6]|div|br|table|tr|td|li|ul|ol)\b).)+?)\s*\(proc text\)\s*\]"
    r"((?:\s|&nbsp;|</(?:span|em|strong|b|i|u)\s*>)*</\2\s*>)"
)
_PROC_TEXT_OPEN_SENTINEL = "\ue001"
_PROC_TEXT_CLOSE_SENTINEL = "\ue002"
PROC_TEXT_OPEN_TAG = "[(proc text) "
PROC_TEXT_CLOSE_TAG = " (proc text)]"
_PROC_TEXT_LINE_START_PATTERN = r"^[\s_*]*" + re.escape(PROC_TEXT_OPEN_TAG)
_ESCAPED_TEXT_CHARACTER_PATTERN = r"\\([\\.+\-])"
_DATA_IMAGE_PATTERN = r"<img[^>]*src=\"data:[^\"]*\"[^>]*>"
_SPACE_BEFORE_ANCHOR_PATTERN = r"(\s+)(<a\b[^>]*>)"
_FOOTNOTE_SECTION_PATTERN = r"(<div class=\"fns\">)"
_PREFORMATTED_BLOCK_PATTERN = r"(<pre\b[^>]*>)(.*?)(</pre>)"
_HTML_TAG_START = "<"
_WIDE_GAP_PATTERN = r"(?<=\S) {3,}(?=\S)"
_TABLE_MARK_PATTERN = r"\. \. \.|_{3}|={3}|[}|]|(?<=\S) {6,}(?=\S)"
_NUMBER_AFTER_GAP_PATTERN = r"\S {3,}[^ ]*\d.{0,40}$"
_LIST_ITEM_PATTERN = r"^[a-z0-9]{1,4}[.)]\s"
_MIN_DOUBLE_SPACED_GAPS = 2
_MIN_WRAPPED_LINE_LENGTH = 20
_MIN_WRAPPED_LINE_RATIO = 0.6
_PARAGRAPH_GAP_SINGLE_SPACED = 1
_PARAGRAPH_GAP_DOUBLE_SPACED = 2
_NO_BREAK_SPACE = "\u00a0"
# NOTE: a prefilter for stored text: a run fix_mojibake can change starts with a character from U+00C2 to U+00F4.
REPAIRABLE_TEXT_PATTERN = "[\u00c2-\u00f4\ufffd\ufeff]"
_LOST_CLOSING_QUOTE_PATTERN = r"(?<=[A-Za-z0-9.,;:!?')\]_*])\ufffd\?"
_CLOSING_DOUBLE_QUOTE = "\u201d"
# NOTE: a lost Latin-1 byte where only one character fits, checked by hand on 22 Oct 2026; "$" is ASCII and cannot be lost, so "\ufffd" before an amount is "£".
_LOST_CHARACTER_WORDS = {
    "entrep\ufffdt": "entrep\u00f4t",
    "b\ufffdte noire": "b\u00eate noire",
    "expos\ufffd earlier": "expos\u00e9 earlier",
    "Communiqu\ufffd": "Communiqu\u00e9",
    "Associat\ufffdon": "Association",
}
_LOST_POUND_SIGN_PATTERN = r"(?<![\w\ufffd])\ufffd(?=\d)"
_POUND_SIGN = "\u00a3"
ASCII_FOLDED_CHARACTERS = str.maketrans(
    {html5[name + ";"]: folded for name, folded in html2text.config.UNIFIABLE.items() if name != "nbsp"}
)


# NOTE: html2text puts a space between an emphasis mark and the letter before it but not after ASCII punctuation, so a character from an entity is judged by its ASCII fold, as it was when the converter folded it; a no-break space stays a space, as "&nbsp;" does.
class _SourceCharacterConverter(html2text.HTML2Text):
    def __init__(self):
        super().__init__(bodywidth=0)
        self.unicode_snob = True

    def handle_data(self, data: str, entity_char: bool = False) -> None:
        super().handle_data(data, entity_char)
        if entity_char:
            self.preceding_data = self.preceding_data.translate(ASCII_FOLDED_CHARACTERS)

    def handle(self, data: str) -> str:
        return super().handle(data).replace(_NO_BREAK_SPACE, " ")


def _replace_nbsp_only_emphasis_with_space(html: str) -> str:
    return re.sub(_NBSP_ONLY_EMPHASIS_PATTERN, " ", html, flags=re.IGNORECASE)


def _replace_nbsp_with_space(html: str) -> str:
    return html.replace(_NBSP_ENTITY, " ")


def _glue_footnote_hash_markers(html: str) -> str:
    # NOTE: a marker followed by a space would read as a markdown heading, so it stays glued to its note like the other markers.
    return re.sub(_FOOTNOTE_HASH_MARKER_PATTERN, r"#\1", html)


def _render_footnote_superscript(match: re.Match) -> str:
    preceding_window = match.string[max(0, match.start() - _PRECEDING_HTML_LENGTH) : match.start()]
    preceding_html = re.sub(_BLOCK_TAG_PATTERN, "\n", preceding_window, flags=re.IGNORECASE)
    preceding = re.sub(_HTML_TAG_PATTERN, "", preceding_html)
    if not preceding.strip() or preceding[-1].isspace():
        return match.group(0)
    # NOTE: the converter writes a space between closing emphasis and a digit outside a link, so that digit was never glued.
    if (
        re.search(_CLOSING_EMPHASIS_END_PATTERN, preceding_window, flags=re.IGNORECASE) is not None
        and re.search(_ANCHOR_TAG_PATTERN, match.group(0), flags=re.IGNORECASE) is None
    ):
        return match.group(0)
    if re.search(_EXPONENT_BASE_PATTERN, preceding) is not None:
        return match.group(0)
    marker = _OPENING_BRACKET + re.sub(_LIST_COMMA_PATTERN, ",", match.group(1)) + _CLOSING_BRACKET
    # NOTE: the marker replaces only the digits, so the converter treats the tags and spaces around it as it did before.
    return match.string[match.start() : match.start(1)] + marker + match.string[match.end(1) : match.end()]


def _mark_footnote_superscripts(html: str) -> str:
    return re.sub(_SUPERSCRIPT_FOOTNOTE_PATTERN, _render_footnote_superscript, html, flags=re.IGNORECASE)


def _move_space_into_anchor(html: str) -> str:
    # NOTE: html2text strips the space ending the first text inside emphasis, so "to <a>" glued as "toAppendix".
    return re.sub(_SPACE_BEFORE_ANCHOR_PATTERN, r"\2\1", html, flags=re.IGNORECASE)


def _mark_footnote_section(html: str) -> str:
    # NOTE: the rule is how the older report pages already set footnotes apart, so the speech parser reads both the same way.
    return re.sub(_FOOTNOTE_SECTION_PATTERN, r"<hr>\1", html)


def _unescape_text_characters(markdown: str) -> str:
    return re.sub(_ESCAPED_TEXT_CHARACTER_PATTERN, r"\1", markdown)


def _restore_lost_closing_quotes(markdown: str) -> str:
    # NOTE: SPRS sends "”" as "\ufffd?": its text went through cp1252, which has no character for the last byte 0x9D. After Chinese text the same pair is a lost CJK byte, so it stays.
    return re.sub(_LOST_CLOSING_QUOTE_PATTERN, _CLOSING_DOUBLE_QUOTE, markdown)


def _restore_lost_characters(markdown: str) -> str:
    for lost_word, word in _LOST_CHARACTER_WORDS.items():
        markdown = markdown.replace(lost_word, word)
    return re.sub(_LOST_POUND_SIGN_PATTERN, _POUND_SIGN, markdown)


def repair_source_characters(markdown: str) -> str:
    # NOTE: the mojibake fix runs first, because SPRS also sends a lost closing quote as "ï¿½?", the mojibake of "\ufffd?".
    markdown = _restore_lost_closing_quotes(fix_mojibake(markdown))
    # NOTE: an older-system report can carry a byte-order mark as an entity, which the HTML strip in _prepare_newer_system_html does not see.
    return _restore_lost_characters(markdown).replace(_BYTE_ORDER_MARK, "")


def _escape_bare_ampersand(match: re.Match) -> str:
    word = match.group(1)
    if word == "#" or word in html5 or f"{word};" in html5:
        return match.group(0)
    return _AMPERSAND_ENTITY + (word or "")


def _escape_bare_ampersands(html: str) -> str:
    return re.sub(_AMPERSAND_PATTERN, _escape_bare_ampersand, html)


def _keep_proc_text_blocks(html: str) -> str:
    # NOTE: only a tag that wraps a whole block is kept; one sharing its block with other text, or spanning blocks, often marks speech by mistake.
    html = re.sub(_PROC_TEXT_BLOCK_PATTERN, rf"\1{_PROC_TEXT_OPEN_SENTINEL}\3{_PROC_TEXT_CLOSE_SENTINEL}\4", html, flags=re.DOTALL)
    html = re.sub(_PROC_TEXT_PAIR_PATTERN, r"\1", html, flags=re.DOTALL)
    html = re.sub(_PROC_TEXT_LONE_PATTERN, "", html)
    return html.replace(_PROC_TEXT_OPEN_SENTINEL, PROC_TEXT_OPEN_TAG).replace(_PROC_TEXT_CLOSE_SENTINEL, PROC_TEXT_CLOSE_TAG)


def _escape_stray_head_tags(html: str) -> str:
    # NOTE: a page header printed as "<HEAD V - MINISTRY ..." reads as a head tag, and html2text then drops the body after it.
    return re.sub(_STRAY_HEAD_TAG_PATTERN, rf"{_ESCAPED_OPENING_ANGLE}\1", html, flags=re.IGNORECASE)


def _prepare_newer_system_html(html: str) -> str:
    html = re.sub(_EMPTY_EMPHASIS_PATTERN, " ", html)
    html = _keep_proc_text_blocks(html)
    html = re.sub(_DATA_IMAGE_PATTERN, "", html)
    return html.replace(_BYTE_ORDER_MARK, "")


def _mark_paragraph_page_breaks(html: str) -> str:
    return re.sub(_PARAGRAPH_MARKER_PATTERN, f"<p>{_PAGE_BREAK_SENTINEL}</p>", html)


def _remove_column_markers(html: str) -> str:
    return re.sub(_COLUMN_MARKER_PATTERN, "", html)


def _remove_page_text(html: str) -> str:
    return re.sub(_PAGE_TEXT_PATTERN, "", html)


def _strip_page_break_artifacts(markdown: str) -> str:
    markdown = re.sub(_PAGE_BREAK_ARTIFACT_PATTERN, " ", markdown)
    return re.sub(_TWO_SPACE_PAGE_BREAK_ARTIFACT_PATTERN, r"\1 ", markdown, flags=re.MULTILINE)


def _remove_empty_lines(markdown: str) -> str:
    return "\n".join(line for line in markdown.splitlines() if line)


def _has_unclosed_bracket(text: str) -> bool:
    return text.count(_OPENING_BRACKET) > text.count(_CLOSING_BRACKET)


def _is_proc_text_line(line: str) -> bool:
    return re.match(_PROC_TEXT_LINE_START_PATTERN, line) is not None


def _is_name_line(line: str) -> bool:
    return re.match(_PERSON_NAME_LINE_PATTERN, line.strip()) is not None and len(line.split()) <= _MAX_NAME_LINE_WORDS


def _should_join_across_page_break(before: str, after: str) -> bool:
    if not before.strip() or not after.strip():
        return False
    # NOTE: the source tags a whole block as procedural text, so it never joins the paragraph next to it.
    if _is_proc_text_line(before) or _is_proc_text_line(after):
        return False
    # NOTE: a list item ends in a semicolon or a comma and a roll name has no full stop, so the sentence-end test below would call both unfinished.
    if re.match(_LIST_ITEM_START_PATTERN, after):
        return False
    if _is_name_line(before) and _is_name_line(after):
        return False
    # NOTE: a marker inside a bracketed note cuts the note itself, whatever emphasis or stage-direction marks sit at the cut.
    if _has_unclosed_bracket(before) and re.match(_NON_SPEECH_BLOCK_PATTERN, after) is None:
        return True
    if re.match(_EMPHASIS_START_PATTERN, after) or re.match(_NON_SPEECH_BLOCK_PATTERN, after):
        return False
    if re.search(_STAGE_DIRECTION_END_PATTERN, before) or re.match(_COLUMN_RANGE_LINE_PATTERN, before):
        return False
    if re.fullmatch(_TIME_OF_DAY_LINE_PATTERN, before, flags=re.IGNORECASE) or re.fullmatch(_TIME_OF_DAY_LINE_PATTERN, after, flags=re.IGNORECASE):
        return False
    if re.match(_NON_SPEECH_BLOCK_PATTERN, before):
        return False
    if re.fullmatch(_BOLD_ONLY_LINE_PATTERN, before.strip()):
        return False
    return re.search(_SENTENCE_END_PATTERN, before) is None


def _get_page_break_separator(before: str, after: str) -> str:
    if re.search(_HYPHENATED_FRAGMENT_PATTERN, before) and after[:1].islower():
        return ""
    return " "


def _join_across_emphasis_pair(before: str, after: str) -> str:
    left = before[:-_EMPHASIS_MARKER_LENGTH]
    separator = "" if left[-1:].isspace() or left.endswith(_HYPHEN) else " "
    return left + separator + after[_EMPHASIS_MARKER_LENGTH:].lstrip()


def _join_paragraphs_across_page_breaks(markdown: str) -> str:
    lines = []
    is_after_page_break = False
    for line in markdown.splitlines():
        if line.strip() == _PAGE_BREAK_SENTINEL:
            is_after_page_break = True
            continue
        if is_after_page_break and lines and _should_join_across_page_break(lines[-1], line):
            before = lines[-1].rstrip()
            after = line.lstrip()
            if before.endswith(_EMPHASIS_MARK) and after.startswith(_EMPHASIS_MARK) and _has_unclosed_bracket(before):
                lines[-1] = _join_across_emphasis_pair(before, after)
            else:
                lines[-1] = before + _get_page_break_separator(before, after) + after
        else:
            lines.append(line)
        is_after_page_break = False
    return "\n".join(lines).replace(_PAGE_BREAK_SENTINEL, "")


def _get_line_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _is_preformatted_table(lines: list[str]) -> bool:
    if any(re.search(_TABLE_MARK_PATTERN, line.rstrip()) or re.search(_NUMBER_AFTER_GAP_PATTERN, line.rstrip()) for line in lines):
        return True
    gap_starts = Counter()
    gap_ends = Counter()
    for line in lines:
        for gap in re.finditer(_WIDE_GAP_PATTERN, line):
            gap_starts[gap.start()] += 1
            gap_ends[gap.end()] += 1
    return any(count > 1 for count in (*gap_starts.values(), *gap_ends.values()))


def _split_preformatted_paragraphs(lines: list[str]) -> list[list[int]]:
    content_indexes = [index for index, line in enumerate(lines) if line.strip()]
    blank_counts = [after - before - 1 for before, after in zip(content_indexes, content_indexes[1:])]
    single_blank_count = blank_counts.count(1)
    is_double_spaced = single_blank_count >= _MIN_DOUBLE_SPACED_GAPS and single_blank_count > blank_counts.count(0)
    paragraph_gap = _PARAGRAPH_GAP_DOUBLE_SPACED if is_double_spaced else _PARAGRAPH_GAP_SINGLE_SPACED
    paragraphs = []
    for position, index in enumerate(content_indexes):
        if position == 0 or blank_counts[position - 1] >= paragraph_gap:
            paragraphs.append([])
        paragraphs[-1].append(index)
    return paragraphs


def _should_join_preformatted_lines(before: str, after: str, longest_length: int) -> bool:
    if _get_line_indent(before) != _get_line_indent(after):
        return False
    if len(before.strip()) < max(_MIN_WRAPPED_LINE_LENGTH, _MIN_WRAPPED_LINE_RATIO * longest_length):
        return False
    if not after.strip()[:1].islower() or re.match(_LIST_ITEM_PATTERN, after.strip()):
        return False
    return _should_join_across_page_break(before.strip(), after.strip())


def _get_preformatted_join_separators(lines: list[str]) -> dict[int, str]:
    separators = {}
    for paragraph in _split_preformatted_paragraphs(lines):
        paragraph_lines = [lines[index] for index in paragraph]
        if _is_preformatted_table(paragraph_lines):
            continue
        longest_length = max(len(line.strip()) for line in paragraph_lines)
        for before_index, after_index in zip(paragraph, paragraph[1:]):
            if _should_join_preformatted_lines(lines[before_index], lines[after_index], longest_length):
                separators[after_index] = _get_page_break_separator(lines[before_index].strip(), lines[after_index].strip())
    return separators


def _join_preformatted_block(match: re.Match) -> str:
    opening, text, closing = match.groups()
    if _HTML_TAG_START in text:
        return match.group(0)
    lines = text.split("\n")
    separators = _get_preformatted_join_separators(lines)
    joined_lines = []
    pending_blank_lines = []
    for index, line in enumerate(lines):
        if index in separators:
            joined_lines[-1] = joined_lines[-1].rstrip() + separators[index] + line.lstrip()
            pending_blank_lines = []
            continue
        if not line.strip():
            pending_blank_lines.append(line)
            continue
        joined_lines.extend(pending_blank_lines)
        pending_blank_lines = []
        joined_lines.append(line)
    return opening + "\n".join(joined_lines + pending_blank_lines) + closing


def _join_wrapped_preformatted_lines(html: str) -> str:
    return re.sub(_PREFORMATTED_BLOCK_PATTERN, _join_preformatted_block, html, flags=re.DOTALL | re.IGNORECASE)


def _merge_consecutive_bold_only_lines(markdown: str) -> str:
    lines = []
    pending_bold_lines = []
    for line in markdown.splitlines():
        if re.fullmatch(_BOLD_ONLY_LINE_PATTERN, line.strip()):
            pending_bold_lines.append(line.strip()[_BOLD_MARKER_LENGTH:-_BOLD_MARKER_LENGTH])
            continue
        if pending_bold_lines:
            lines.append(f"{_BOLD_MARKER}{' '.join(pending_bold_lines)}{_BOLD_MARKER}")
            pending_bold_lines = []
        lines.append(line)
    if pending_bold_lines:
        lines.append(f"{_BOLD_MARKER}{' '.join(pending_bold_lines)}{_BOLD_MARKER}")

    return "\n".join(lines)


def _join_bold_label_split_across_lines(markdown: str) -> str:
    # NOTE: the source breaks a label inside its bracket, "(Dr Mohamad Maliki Bin" then "Osman)", and the bold run closes on the second line.
    return re.sub(_SPLIT_BOLD_LABEL_PATTERN, r"\1 \2**", markdown)


def _join_emphasised_lines(before: str, after: str) -> str:
    before = before.rstrip()
    after = after.lstrip()
    if before.endswith(_EMPHASIS_MARK) and after.startswith(_EMPHASIS_MARK):
        return before[:-_EMPHASIS_MARKER_LENGTH] + " " + after[_EMPHASIS_MARKER_LENGTH:]
    return before + " " + after


def _is_split_direction_open(line: str, next_line: str) -> bool:
    if re.search(_SENTENCE_END_PATTERN, line) is None:
        return True
    return re.search(_TIME_ABBREVIATION_END_PATTERN, line, re.IGNORECASE) is not None and next_line.lstrip(_EMPHASIS_MARK + " ")[:1].islower()


def _merge_split_direction_lines(markdown: str) -> str:
    # NOTE: right-aligned adjournment and suspension directions are split across several source blocks, each rendering as its own line.
    lines = markdown.splitlines()
    merged_lines = []
    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        if re.match(_SPLIT_DIRECTION_LINE_PATTERN, line.lstrip(), re.IGNORECASE):
            merges = 0
            while (
                merges < _MAX_ADJOURNMENT_CONTINUATIONS
                and line_index + 1 < len(lines)
                and _is_split_direction_open(line, lines[line_index + 1])
                and re.search(_ALPHANUMERIC_PATTERN, lines[line_index + 1])
                and not re.match(_BLOCK_START_PATTERN, lines[line_index + 1])
                and not re.match(_DIRECTION_START_PATTERN, lines[line_index + 1], re.IGNORECASE)
                and not _is_proc_text_line(lines[line_index + 1])
            ):
                line_index += 1
                merges += 1
                line = _join_emphasised_lines(line, lines[line_index])
        merged_lines.append(line)
        line_index += 1
    return "\n".join(merged_lines)


def _drop_paragraph_repeated_after_stray_tag(markdown: str) -> str:
    # NOTE: report 24516 prints one paragraph twice around a literal closing tag; only an exact repeat of the paragraph before the tag is dropped.
    lines = []
    for line in markdown.splitlines():
        before, tag, after = line.partition(_STRAY_CLOSING_TAG)
        repeated_text = after.strip()
        if not tag or not repeated_text or not before.rstrip().endswith(repeated_text):
            lines.append(line)
            continue
        label = before.rstrip()[: -len(repeated_text)].rstrip().removesuffix(_STRAY_OPENING_ANGLE).rstrip()
        lines.append(f"{label} {repeated_text}")
    return "\n".join(lines)


def _flatten_leading_nested_bold(markdown: str) -> str:
    return re.sub(_LEADING_NESTED_BOLD_PATTERN, r"**\1\2**", markdown, flags=re.MULTILINE)


def _preprocess_html(html: str) -> str:
    html = _replace_nbsp_only_emphasis_with_space(html)
    html = _replace_nbsp_with_space(html)
    html = _mark_footnote_superscripts(html)
    html = _escape_bare_ampersands(html)
    html = _mark_paragraph_page_breaks(html)
    html = _remove_column_markers(html)
    return _remove_page_text(html)


def _postprocess_markdown_base(markdown: str) -> str:
    markdown = _strip_page_break_artifacts(markdown)
    markdown = _remove_empty_lines(markdown)
    markdown = _join_paragraphs_across_page_breaks(markdown)
    return _merge_consecutive_bold_only_lines(markdown)


def get_cleaned_report_markdown(html: str, report_version: str) -> str:
    if report_version == ReportVersion.SPRS2:
        html = _escape_stray_head_tags(html)
    if report_version == ReportVersion.SPRS3:
        html = _prepare_newer_system_html(html)
    html = _join_wrapped_preformatted_lines(html)
    converter = _SourceCharacterConverter()
    converter.ignore_links = True
    markdown = _postprocess_markdown_base(converter.handle(_mark_footnote_section(_move_space_into_anchor(_preprocess_html(_glue_footnote_hash_markers(html))))))
    if report_version == ReportVersion.SPRS2:
        markdown = _join_bold_label_split_across_lines(markdown)
    markdown = _merge_split_direction_lines(markdown)
    markdown = _flatten_leading_nested_bold(markdown)
    markdown = _drop_paragraph_repeated_after_stray_tag(markdown)
    return repair_source_characters(_unescape_text_characters(markdown))


def _fix_sitting_concat_headers(html: str) -> str:
    # NOTE: modern (vol 79+) HTML stores "PARTIOF SECOND SESSION" and "VOLUME79" without spaces.
    html = re.sub(_CONCATENATED_PART_PATTERN, r"PART \1 OF", html)
    return re.sub(_CONCATENATED_VOLUME_PATTERN, r"VOLUME \1", html)


def _remove_sitting_orphan_bold_markers(markdown: str) -> str:
    # NOTE: runs after _fix_sitting_split_bold, so a standalone ** left over is an orphaned marker.
    return "\n".join(line for line in markdown.splitlines() if line.strip() != _BOLD_MARKER)


def _remove_sitting_empty_italic(markdown: str) -> str:
    # NOTE: empty italic tags in vol 38-70 render as __ between the date and meeting-time lines.
    return "\n".join(line for line in markdown.splitlines() if line.strip() != _EMPTY_ITALIC_LINE)


def _fix_sitting_split_bold(markdown: str) -> str:
    lines = markdown.splitlines()
    fixed_lines = []
    line_index = 0
    while line_index < len(lines):
        stripped = lines[line_index].strip()

        if (stripped.startswith(_BOLD_MARKER)
                and not stripped.endswith(_BOLD_MARKER)
                and len(stripped) > _BOLD_MARKER_LENGTH
                and line_index + 1 < len(lines)
                and lines[line_index + 1].strip() == _BOLD_MARKER):
            fixed_lines.append(stripped + _BOLD_MARKER)
            line_index += 2

        elif (stripped == _BOLD_MARKER
              and line_index + 2 < len(lines)
              and lines[line_index + 1].strip()
              and lines[line_index + 2].strip() == _BOLD_MARKER):
            fixed_lines.append(f"{_BOLD_MARKER}{lines[line_index + 1].strip()}{_BOLD_MARKER}")
            line_index += 3

        else:
            fixed_lines.append(lines[line_index])
            line_index += 1
    return "\n".join(fixed_lines)


def _remove_sitting_table_separators(markdown: str) -> str:
    # NOTE: html2text renders <hr> as "* * *", so a standalone "---" line is a one-column table artefact.
    return "\n".join(
        line for line in markdown.splitlines()
        if line.strip() != _ONE_COLUMN_TABLE_SEPARATOR_LINE and not re.fullmatch(_TABLE_SEPARATOR_LINE_PATTERN, line)
    )


def _remove_sitting_orphan_italic_markers(markdown: str) -> str:
    return "\n".join(line for line in markdown.splitlines() if line.strip() != _EMPHASIS_MARK)


def _remove_sitting_empty_bold(markdown: str) -> str:
    cleaned_lines = []
    for line in markdown.splitlines():
        if re.fullmatch(_ASTERISK_ONLY_LINE_PATTERN, line):
            continue
        line = re.sub(_LEADING_EMPTY_BOLD_PATTERN, "", line)
        line = re.sub(_TRAILING_EMPTY_BOLD_PATTERN, "", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _merge_sitting_adjournment_lines(markdown: str) -> str:
    # NOTE: the adjournment time is split across several right-aligned divs, each rendering as its own line.
    lines = markdown.splitlines()
    merged_lines = []
    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        if re.search(_ADJOURNMENT_LINE_PATTERN, line, re.IGNORECASE):
            merges = 0
            while (
                not line.rstrip().endswith(_PERIOD)
                and not line.rstrip().endswith(_PERIOD_THEN_EMPHASIS_MARK)
                and merges < _MAX_ADJOURNMENT_CONTINUATIONS
                and line_index + 1 < len(lines)
                and not re.match(_BLOCK_START_PATTERN, lines[line_index + 1])
            ):
                line_index += 1
                merges += 1
                line = line.rstrip() + " " + lines[line_index].lstrip()
        merged_lines.append(line)
        line_index += 1
    return "\n".join(merged_lines)


def get_cleaned_sitting_markdown(html: str) -> str:
    converter = _SourceCharacterConverter()
    preprocessed = _fix_sitting_concat_headers(_preprocess_html(html))
    markdown = _postprocess_markdown_base(converter.handle(preprocessed))
    markdown = _fix_sitting_split_bold(markdown)
    markdown = _remove_sitting_orphan_bold_markers(markdown)
    markdown = _remove_sitting_empty_bold(markdown)
    markdown = _remove_sitting_table_separators(markdown)
    markdown = _remove_sitting_orphan_italic_markers(markdown)
    markdown = _remove_sitting_empty_italic(markdown)
    return repair_source_characters(_merge_sitting_adjournment_lines(markdown))

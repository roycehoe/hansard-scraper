import re

import html2text

_MAX_ADJOURNMENT_CONTINUATIONS = 6
_BOLD_MARKER_LENGTH = 2
_COLUMN_MARKER_PATTERN = r"Column(?:\s+No)?\s*:\s*\d+"
_PAGE_TEXT_PATTERN = r"Page:\s*\d+"
_PAGE_BREAK_ARTIFACT_PATTERN = r"   \n  \n\*\*\*\*  \n  \n"
_BOLD_ONLY_LINE_PATTERN = r"\*\*[^\n*].*\*\*"
_CONCATENATED_PART_PATTERN = r"\bPART([IVX]+)OF\b"
_CONCATENATED_VOLUME_PATTERN = r"\bVOLUME(\d+)\b"
_TABLE_SEPARATOR_LINE_PATTERN = r"-{3}\s*"
_ASTERISK_ONLY_LINE_PATTERN = r"\*+\s*"
_LEADING_EMPTY_BOLD_PATTERN = r"^(\*{4})+"
_TRAILING_EMPTY_BOLD_PATTERN = r"(\*{4})+$"
_ADJOURNMENT_LINE_PATTERN = r"Adjourned accordingly at"
_BLOCK_START_PATTERN = r"^(\*\*|#{1,6}|\* \* \*)"


def _strip_nbsp(html: str) -> str:
    return html.replace("&nbsp;", "")


def _remove_column_markers(html: str) -> str:
    return re.sub(_COLUMN_MARKER_PATTERN, "", html)


def _remove_page_text(html: str) -> str:
    return re.sub(_PAGE_TEXT_PATTERN, "", html)


def _strip_page_break_artifacts(markdown: str) -> str:
    return re.sub(_PAGE_BREAK_ARTIFACT_PATTERN, " ", markdown)


def _remove_empty_lines(markdown: str) -> str:
    return "\n".join(line for line in markdown.splitlines() if line)


def _merge_consecutive_bold_only_lines(markdown: str) -> str:
    lines = []
    pending_bold_lines = []
    for line in markdown.splitlines():
        if re.fullmatch(_BOLD_ONLY_LINE_PATTERN, line.strip()):
            pending_bold_lines.append(line.strip()[_BOLD_MARKER_LENGTH:-_BOLD_MARKER_LENGTH])  # strip ** … **
            continue
        if pending_bold_lines:
            lines.append(f"**{' '.join(pending_bold_lines)}**")
            pending_bold_lines = []
        lines.append(line)
    if pending_bold_lines:
        lines.append(f"**{' '.join(pending_bold_lines)}**")

    return "\n".join(lines)


def _preprocess_html(html: str) -> str:
    html = _strip_nbsp(html)
    html = _remove_column_markers(html)
    return _remove_page_text(html)


def _postprocess_markdown_base(markdown: str) -> str:
    markdown = _strip_page_break_artifacts(markdown)
    markdown = _remove_empty_lines(markdown)
    return _merge_consecutive_bold_only_lines(markdown)


def get_cleaned_report_markdown(html: str) -> str:
    converter = html2text.HTML2Text(bodywidth=0)
    return _postprocess_markdown_base(converter.handle(_preprocess_html(html)))


def _fix_sitting_concat_headers(html: str) -> str:
    # Modern (vol 79+) HTML stores "PARTIOF SECOND SESSION" and "VOLUME79" in span text
    # without spaces. Fix before passing to html2text.
    html = re.sub(_CONCATENATED_PART_PATTERN, r"PART \1 OF", html)
    return re.sub(_CONCATENATED_VOLUME_PATTERN, r"VOLUME \1", html)


def _remove_sitting_orphan_bold_markers(markdown: str) -> str:
    # After _fix_sitting_split_bold has merged all fixable patterns, any remaining
    # standalone ** lines are orphaned opening/closing markers (from </span></div>
    # boundaries in the HTML). Strip them.
    return "\n".join(line for line in markdown.splitlines() if line.strip() != "**")


def _remove_sitting_empty_italic(markdown: str) -> str:
    # <i></i> or <em></em> empty italic tags render as __ (html2text).
    # These appear in vol 38-70 docs inside <div id="adjTime"> between the date and meeting-time lines.
    return "\n".join(line for line in markdown.splitlines() if line.strip() != "__")


def _fix_sitting_split_bold(markdown: str) -> str:
    # Fix patterns produced by modern (vol 79+) HTML where <b> tags wrap <P> elements.
    #
    # Pattern 1: **TITLE  \n**   → **TITLE**  (bold opens on title line, closes on next)
    # Pattern 2: **\nTITLE\n**  → **TITLE**  (open ** on own line, single title, close **)
    lines = markdown.splitlines()
    fixed_lines = []
    line_index = 0
    while line_index < len(lines):
        stripped = lines[line_index].strip()

        # Pattern 1: starts with **, has content, doesn't close with **, next line is **
        if (stripped.startswith("**")
                and not stripped.endswith("**")
                and len(stripped) > _BOLD_MARKER_LENGTH
                and line_index + 1 < len(lines)
                and lines[line_index + 1].strip() == "**"):
            fixed_lines.append(stripped + "**")
            line_index += 2

        # Pattern 2: standalone **, single plain content line, closing **
        elif (stripped == "**"
              and line_index + 2 < len(lines)
              and lines[line_index + 1].strip()
              and lines[line_index + 2].strip() == "**"):
            fixed_lines.append(f"**{lines[line_index + 1].strip()}**")
            line_index += 3

        else:
            fixed_lines.append(lines[line_index])
            line_index += 1
    return "\n".join(fixed_lines)


def _remove_sitting_table_separators(markdown: str) -> str:
    # Strip 2-column table separator (---|---) and 1-column table separator (--- with optional trailing spaces).
    # html2text renders <hr> as "* * *", so standalone "---" lines are always 1-column table artefacts.
    return "\n".join(
        line for line in markdown.splitlines()
        if line.strip() != "---|---" and not re.fullmatch(_TABLE_SEPARATOR_LINE_PATTERN, line)
    )


def _remove_sitting_orphan_italic_markers(markdown: str) -> str:
    return "\n".join(line for line in markdown.splitlines() if line.strip() != "_")


def _remove_sitting_empty_bold(markdown: str) -> str:
    cleaned_lines = []
    for line in markdown.splitlines():
        # Drop lines that are entirely asterisks (e.g. ****, ********, etc.)
        if re.fullmatch(_ASTERISK_ONLY_LINE_PATTERN, line):
            continue
        # Strip all leading/trailing **** empty-bold marker groups from content lines
        line = re.sub(_LEADING_EMPTY_BOLD_PATTERN, "", line)
        line = re.sub(_TRAILING_EMPTY_BOLD_PATTERN, "", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _merge_sitting_adjournment_lines(markdown: str) -> str:
    # The adjournment time is split across multiple <div align="right"> elements in the HTML,
    # each rendering as a separate line. Merge continuations until the sentence ends with a period.
    lines = markdown.splitlines()
    merged_lines = []
    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        if re.search(_ADJOURNMENT_LINE_PATTERN, line, re.IGNORECASE):
            merges = 0
            while (
                not line.rstrip().endswith(".")
                and not line.rstrip().endswith("._")
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
    converter = html2text.HTML2Text(bodywidth=0)
    preprocessed = _fix_sitting_concat_headers(_preprocess_html(html))
    markdown = _postprocess_markdown_base(converter.handle(preprocessed))
    markdown = _fix_sitting_split_bold(markdown)
    markdown = _remove_sitting_orphan_bold_markers(markdown)
    markdown = _remove_sitting_empty_bold(markdown)
    markdown = _remove_sitting_table_separators(markdown)
    markdown = _remove_sitting_orphan_italic_markers(markdown)
    markdown = _remove_sitting_empty_italic(markdown)
    return _merge_sitting_adjournment_lines(markdown)

import re

import html2text

from enums import ReportVersion

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
_BYTE_ORDER_MARK = "\ufeff"
_EMPTY_EMPHASIS_PATTERN = r"<(strong|em)[^>]*>(\s|&nbsp;|\ufeff)*</\1>"
_PROC_TEXT_PAIR_PATTERN = r"\[\s*\(proc text\)\s*(.*?)\s*\(proc text\)\s*\]"
_PROC_TEXT_LONE_PATTERN = r"\[?\s*\(proc text\)\s*\]?"
_DATA_IMAGE_PATTERN = r"<img[^>]*src=\"data:[^\"]*\"[^>]*>"


def _strip_nbsp(html: str) -> str:
    return html.replace("&nbsp;", "")


def _prepare_newer_system_html(html: str) -> str:
    html = re.sub(_EMPTY_EMPHASIS_PATTERN, "", html)
    html = re.sub(_PROC_TEXT_PAIR_PATTERN, r"\1", html, flags=re.DOTALL)
    html = re.sub(_PROC_TEXT_LONE_PATTERN, "", html)
    html = re.sub(_DATA_IMAGE_PATTERN, "", html)
    return html.replace("&nbsp;", " ").replace(_BYTE_ORDER_MARK, "")


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
            pending_bold_lines.append(line.strip()[_BOLD_MARKER_LENGTH:-_BOLD_MARKER_LENGTH])
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


def get_cleaned_report_markdown(html: str, report_version: str) -> str:
    if report_version == ReportVersion.SPRS3:
        html = _prepare_newer_system_html(html)
    converter = html2text.HTML2Text(bodywidth=0)
    return _postprocess_markdown_base(converter.handle(_preprocess_html(html)))


def _fix_sitting_concat_headers(html: str) -> str:
    # NOTE: modern (vol 79+) HTML stores "PARTIOF SECOND SESSION" and "VOLUME79" without spaces.
    html = re.sub(_CONCATENATED_PART_PATTERN, r"PART \1 OF", html)
    return re.sub(_CONCATENATED_VOLUME_PATTERN, r"VOLUME \1", html)


def _remove_sitting_orphan_bold_markers(markdown: str) -> str:
    # NOTE: runs after _fix_sitting_split_bold, so a standalone ** left over is an orphaned marker.
    return "\n".join(line for line in markdown.splitlines() if line.strip() != "**")


def _remove_sitting_empty_italic(markdown: str) -> str:
    # NOTE: empty italic tags in vol 38-70 render as __ between the date and meeting-time lines.
    return "\n".join(line for line in markdown.splitlines() if line.strip() != "__")


def _fix_sitting_split_bold(markdown: str) -> str:
    lines = markdown.splitlines()
    fixed_lines = []
    line_index = 0
    while line_index < len(lines):
        stripped = lines[line_index].strip()

        if (stripped.startswith("**")
                and not stripped.endswith("**")
                and len(stripped) > _BOLD_MARKER_LENGTH
                and line_index + 1 < len(lines)
                and lines[line_index + 1].strip() == "**"):
            fixed_lines.append(stripped + "**")
            line_index += 2

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
    # NOTE: html2text renders <hr> as "* * *", so a standalone "---" line is a one-column table artefact.
    return "\n".join(
        line for line in markdown.splitlines()
        if line.strip() != "---|---" and not re.fullmatch(_TABLE_SEPARATOR_LINE_PATTERN, line)
    )


def _remove_sitting_orphan_italic_markers(markdown: str) -> str:
    return "\n".join(line for line in markdown.splitlines() if line.strip() != "_")


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

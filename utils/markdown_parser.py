import re

import html2text

_MAX_ADJOURNMENT_CONTINUATIONS = 6


def _strip_nbsp(html: str) -> str:
    return html.replace("&nbsp;", "")


def _remove_column_markers(html: str) -> str:
    return re.sub(r"Column(?:\s+No)?\s*:\s*\d+", "", html)


def _remove_page_text(html: str) -> str:
    page_text_pattern = r"Page:\s*\d+"
    return re.sub(page_text_pattern, "", html)


def _strip_page_break_artifacts(md_file: str) -> str:
    page_text_pattern = r"   \n  \n\*\*\*\*  \n  \n"
    return re.sub(page_text_pattern, " ", md_file)


def _remove_empty_lines(md_file: str) -> str:
    return "\n".join(line for line in md_file.splitlines() if line)


def _merge_consecutive_bold_only_lines(md: str) -> str:
    lines = []
    buff = []
    for line in md.splitlines():
        if re.fullmatch(r"\*\*[^\n*].*\*\*", line.strip()):
            buff.append(line.strip()[2:-2])  # strip ** … **
            continue
        if buff:
            lines.append(f"**{' '.join(buff)}**")
            buff = []
        lines.append(line)
    if buff:
        lines.append(f"**{' '.join(buff)}**")

    return "\n".join(lines)


def _preprocess_html(html: str) -> str:
    html = _strip_nbsp(html)
    html = _remove_column_markers(html)
    return _remove_page_text(html)


def _postprocess_markdown_base(md: str) -> str:
    md = _strip_page_break_artifacts(md)
    md = _remove_empty_lines(md)
    return _merge_consecutive_bold_only_lines(md)


def get_cleaned_report_markdown(html: str) -> str:
    converter = html2text.HTML2Text(bodywidth=0)
    return _postprocess_markdown_base(converter.handle(_preprocess_html(html)))


def _fix_sitting_concat_headers(html: str) -> str:
    # Modern (vol 79+) HTML stores "PARTIOF SECOND SESSION" and "VOLUME79" in span text
    # without spaces. Fix before passing to html2text.
    html = re.sub(r"\bPART([IVX]+)OF\b", r"PART \1 OF", html)
    html = re.sub(r"\bVOLUME(\d+)\b", r"VOLUME \1", html)
    return html


def _remove_sitting_orphan_bold_markers(md: str) -> str:
    # After _fix_sitting_split_bold has merged all fixable patterns, any remaining
    # standalone ** lines are orphaned opening/closing markers (from </span></div>
    # boundaries in the HTML). Strip them.
    return "\n".join(line for line in md.splitlines() if line.strip() != "**")


def _remove_sitting_empty_italic(md: str) -> str:
    # <i></i> or <em></em> empty italic tags render as __ (html2text).
    # These appear in vol 38-70 docs inside <div id="adjTime"> between the date and meeting-time lines.
    return "\n".join(line for line in md.splitlines() if line.strip() != "__")


def _fix_sitting_split_bold(md: str) -> str:
    # Fix patterns produced by modern (vol 79+) HTML where <b> tags wrap <P> elements.
    #
    # Pattern 1: **TITLE  \n**   → **TITLE**  (bold opens on title line, closes on next)
    # Pattern 2: **\nTITLE\n**  → **TITLE**  (open ** on own line, single title, close **)
    lines = md.splitlines()
    result = []
    line_index = 0
    while line_index < len(lines):
        stripped = lines[line_index].strip()

        # Pattern 1: starts with **, has content, doesn't close with **, next line is **
        if (stripped.startswith("**")
                and not stripped.endswith("**")
                and len(stripped) > 2
                and line_index + 1 < len(lines)
                and lines[line_index + 1].strip() == "**"):
            result.append(stripped + "**")
            line_index += 2

        # Pattern 2: standalone **, single plain content line, closing **
        elif (stripped == "**"
              and line_index + 2 < len(lines)
              and lines[line_index + 1].strip()
              and lines[line_index + 2].strip() == "**"):
            result.append(f"**{lines[line_index + 1].strip()}**")
            line_index += 3

        else:
            result.append(lines[line_index])
            line_index += 1
    return "\n".join(result)


def _remove_sitting_table_separators(md: str) -> str:
    # Strip 2-column table separator (---|---) and 1-column table separator (--- with optional trailing spaces).
    # html2text renders <hr> as "* * *", so standalone "---" lines are always 1-column table artefacts.
    return "\n".join(
        line for line in md.splitlines()
        if line.strip() != "---|---" and not re.fullmatch(r"-{3}\s*", line)
    )


def _remove_sitting_orphan_italic_markers(md: str) -> str:
    return "\n".join(line for line in md.splitlines() if line.strip() != "_")


def _remove_sitting_empty_bold(md: str) -> str:
    result = []
    for line in md.splitlines():
        # Drop lines that are entirely asterisks (e.g. ****, ********, etc.)
        if re.fullmatch(r'\*+\s*', line):
            continue
        # Strip all leading/trailing **** empty-bold marker groups from content lines
        line = re.sub(r'^(\*{4})+', '', line)
        line = re.sub(r'(\*{4})+$', '', line)
        result.append(line)
    return "\n".join(result)


def _merge_sitting_adjournment_lines(md: str) -> str:
    # The adjournment time is split across multiple <div align="right"> elements in the HTML,
    # each rendering as a separate line. Merge continuations until the sentence ends with a period.
    lines = md.splitlines()
    result = []
    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        if re.search(r"Adjourned accordingly at", line, re.IGNORECASE):
            merges = 0
            while (
                not line.rstrip().endswith(".")
                and not line.rstrip().endswith("._")
                and merges < _MAX_ADJOURNMENT_CONTINUATIONS
                and line_index + 1 < len(lines)
                and not re.match(r"^(\*\*|#{1,6}|\* \* \*)", lines[line_index + 1])
            ):
                line_index += 1
                merges += 1
                line = line.rstrip() + " " + lines[line_index].lstrip()
        result.append(line)
        line_index += 1
    return "\n".join(result)


def get_cleaned_sitting_markdown(html: str) -> str:
    converter = html2text.HTML2Text(bodywidth=0)
    preprocessed = _fix_sitting_concat_headers(_preprocess_html(html))
    md = _postprocess_markdown_base(converter.handle(preprocessed))
    md = _fix_sitting_split_bold(md)
    md = _remove_sitting_orphan_bold_markers(md)
    md = _remove_sitting_empty_bold(md)
    md = _remove_sitting_table_separators(md)
    md = _remove_sitting_orphan_italic_markers(md)
    md = _remove_sitting_empty_italic(md)
    return _merge_sitting_adjournment_lines(md)

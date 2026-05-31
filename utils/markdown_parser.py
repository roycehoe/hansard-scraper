import re

import html2text


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


def get_cleaned_report_markdown(html: str) -> str:
    h = html2text.HTML2Text(bodywidth=0)

    html = _strip_nbsp(html)
    html = _remove_column_markers(html)
    html = _remove_page_text(html)

    md_file = h.handle(html)
    md_file = _strip_page_break_artifacts(md_file)
    md_file = _remove_empty_lines(md_file)
    md_file = _merge_consecutive_bold_only_lines(md_file)

    return md_file


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
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Pattern 1: starts with **, has content, doesn't close with **, next line is **
        if (stripped.startswith("**")
                and not stripped.endswith("**")
                and len(stripped) > 2
                and i + 1 < len(lines)
                and lines[i + 1].strip() == "**"):
            result.append(stripped + "**")
            i += 2

        # Pattern 2: standalone **, single plain content line, closing **
        elif (stripped == "**"
              and i + 2 < len(lines)
              and lines[i + 1].strip()
              and lines[i + 2].strip() == "**"):
            result.append(f"**{lines[i + 1].strip()}**")
            i += 3

        else:
            result.append(lines[i])
            i += 1
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
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.search(r"Adjourned accordingly at", line, re.IGNORECASE):
            merges = 0
            while (
                not line.rstrip().endswith(".")
                and not line.rstrip().endswith("._")
                and merges < 6
                and i + 1 < len(lines)
                and not re.match(r"^(\*\*|#{1,6}|\* \* \*)", lines[i + 1])
            ):
                i += 1
                merges += 1
                line = line.rstrip() + " " + lines[i].lstrip()
        result.append(line)
        i += 1
    return "\n".join(result)


def get_cleaned_sitting_markdown(html: str) -> str:
    h = html2text.HTML2Text(bodywidth=0)

    html = _strip_nbsp(html)
    html = _remove_column_markers(html)
    html = _remove_page_text(html)
    html = _fix_sitting_concat_headers(html)

    md_file = h.handle(html)
    md_file = _strip_page_break_artifacts(md_file)
    md_file = _remove_empty_lines(md_file)
    md_file = _merge_consecutive_bold_only_lines(md_file)
    md_file = _fix_sitting_split_bold(md_file)
    md_file = _remove_sitting_orphan_bold_markers(md_file)
    md_file = _remove_sitting_empty_bold(md_file)
    md_file = _remove_sitting_table_separators(md_file)
    md_file = _remove_sitting_orphan_italic_markers(md_file)
    md_file = _remove_sitting_empty_italic(md_file)
    md_file = _merge_sitting_adjournment_lines(md_file)

    return md_file

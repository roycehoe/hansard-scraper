import re

import html2text


def _remove_spaces(html: str) -> str:
    return html.replace("&nbsp;", "")


def _remove_column_text(html: str) -> str:
    column_pattern = r"Column:\s*\d+"
    return re.sub(column_pattern, "", html)


def _remove_column_no_text(html: str) -> str:
    column_pattern = r"Column No :\s*\d+"
    return re.sub(column_pattern, "", html)


def _remove_page_text(html: str) -> str:
    page_text_pattern = r"Page:\s*\d+"
    return re.sub(page_text_pattern, "", html)


def _remove_line_breaks(md_file: str) -> str:
    page_text_pattern = r"   \n  \n\*\*\*\*  \n  \n"
    return re.sub(page_text_pattern, " ", md_file)


def _remove_new_lines(md_file: str) -> str:
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


def get_cleaned_handsard_markdown(html: str) -> str:
    h = html2text.HTML2Text(bodywidth=0)

    html = _remove_spaces(html)
    html = _remove_column_text(html)
    html = _remove_column_no_text(html)
    html = _remove_page_text(html)

    md_file = h.handle(html)
    md_file = _remove_line_breaks(md_file)
    md_file = _remove_new_lines(md_file)
    md_file = _merge_consecutive_bold_only_lines(md_file)

    return md_file

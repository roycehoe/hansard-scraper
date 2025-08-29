import re

import html2text


def _remove_spaces(html: str) -> str:
    return html.replace("&nbsp;", "")


def _remove_column_text(html: str) -> str:
    column_pattern = r"Column:\s*\d+"
    return re.sub(f"{column_pattern}", "", html)


def _remove_column_no_text(html: str) -> str:
    column_pattern = r"Column No :\s*\d+"
    return re.sub(f"{column_pattern}", "", html)


def _remove_page_text(html: str) -> str:
    page_text_pattern = r"Page:\s*\d+"
    return re.sub(f"{page_text_pattern}", "", html)


def _remove_line_breaks(html: str) -> str:
    page_text_pattern = r"   \n  \n\*\*\*\*  \n  \n"
    return re.sub(page_text_pattern, " ", html)


def get_cleaned_handsard_markdown(html: str) -> str:
    h = html2text.HTML2Text(bodywidth=0)

    html = _remove_spaces(html)
    html = _remove_column_text(html)
    html = _remove_column_no_text(html)
    html = _remove_page_text(html)

    md_file = h.handle(html)
    md_file = _remove_line_breaks(md_file)

    return md_file

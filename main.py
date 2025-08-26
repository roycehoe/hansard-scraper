import json
import re
from datetime import datetime

import html2text
from sqlmodel import select

from database.init import get_session
from database.report import Report
from services import get_db_report_content_in


def remove_html_spaces(original_text: str) -> str:
    return original_text.replace("&nbsp;", "")


def remove_spaces(original_text: str) -> str:
    return original_text.strip()


def remove_column_text(original_text: str) -> str:
    column_pattern = r"Column:\s*\d+"
    return re.sub(f"{column_pattern}", "", original_text)


def remove_page_text(original_text: str) -> str:
    page_text_pattern = r"Page:\s*\d+"
    return re.sub(f"{page_text_pattern}", "", original_text)


def remove_line_breaks(original_text: str) -> str:
    page_text_pattern = r"   \n  \n\*\*\*\*  \n  \n"
    return re.sub(page_text_pattern, " ", original_text)


def get_cleaned_handsard_markdown(parliament_data: str) -> str:
    h = html2text.HTML2Text(bodywidth=0)

    parliament_data = remove_html_spaces(parliament_data)
    parliament_data = remove_column_text(parliament_data)
    parliament_data = remove_page_text(parliament_data)

    md_file = h.handle(parliament_data)
    md_file = remove_line_breaks(md_file)
    return md_file

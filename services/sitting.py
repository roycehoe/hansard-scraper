from typing import Optional

from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.sitting import Sitting
from utils.markdown_header import (
    SESSION_NUMBER_FIELD,
    SITTING_NUMBER_FIELD,
    get_header_number,
)
from utils.markdown_parser import get_cleaned_sitting_markdown


def _get_number(stored_number: Optional[int], markdown: Optional[str], field_name: str) -> Optional[int]:
    if stored_number is not None:
        return stored_number
    if markdown is None:
        return None
    return get_header_number(markdown, field_name)


def build_sitting(hansard_sitting_date_response: HansardSittingDateResponse) -> Sitting:
    # NOTE: some Optional[int] columns are stored as VARCHAR, so model_dump() returns "" for them;
    # it must become None before Pydantic coerces to int.
    column_to_value = {
        key: (None if value == "" else value)
        for key, value in hansard_sitting_date_response.model_dump(exclude={"id"}).items()
    }
    markdown = (
        get_cleaned_sitting_markdown(hansard_sitting_date_response.html_full_content)
        if hansard_sitting_date_response.html_full_content is not None
        else None
    )
    column_to_value["markdown_content"] = markdown
    # NOTE: the older-system response leaves these numbers out, so they are read from the header table its HTML prints.
    column_to_value["session_no"] = _get_number(column_to_value["session_no"], markdown, SESSION_NUMBER_FIELD)
    column_to_value["sitting_no"] = _get_number(column_to_value["sitting_no"], markdown, SITTING_NUMBER_FIELD)
    return Sitting.model_validate(column_to_value)

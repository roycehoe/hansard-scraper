import re
from typing import Optional

SITTING_NUMBER_FIELD = "Sitting No"
SESSION_NUMBER_FIELD = "Session No"


def get_header_number(markdown_content: str, field_name: str) -> Optional[int]:
    match = re.search(rf"^[ \t|]*{re.escape(field_name)}:[ \t]*\|[ \t]*(\d+)[ \t]*$", markdown_content, re.MULTILINE)
    if match is None:
        return None
    return int(match.group(1))

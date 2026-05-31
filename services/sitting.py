from database.handsard_sitting_date_response import HandsardSittingDateResponse
from database.sitting import Sitting
from utils.markdown_parser import get_cleaned_sitting_markdown


def _strip_nul(d: dict) -> dict:
    return {k: v.replace("\x00", "") if isinstance(v, str) else v for k, v in d.items()}


def build_sitting(response: HandsardSittingDateResponse) -> Sitting:
    markdown = (
        get_cleaned_sitting_markdown(response.html_full_content)
        if response.html_full_content is not None
        else None
    )
    fields = _strip_nul(response.model_dump(exclude={"id"}))
    return Sitting(
        **fields,
        markdown_content=markdown.replace("\x00", "") if markdown is not None else None,
    )

from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.sitting import Sitting
from utils.markdown_parser import get_cleaned_sitting_markdown


def build_sitting(hansard_sitting_date_response: HansardSittingDateResponse) -> Sitting:
    # NOTE: some Optional[int] columns are stored as VARCHAR, so model_dump() returns "" for them;
    # it must become None before Pydantic coerces to int.
    data = {
        key: (None if value == "" else value)
        for key, value in hansard_sitting_date_response.model_dump(exclude={"id"}).items()
    }
    markdown = (
        get_cleaned_sitting_markdown(hansard_sitting_date_response.html_full_content)
        if hansard_sitting_date_response.html_full_content is not None
        else None
    )
    data["markdown_content"] = markdown
    return Sitting.model_validate(data)

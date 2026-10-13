from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.sitting import Sitting
from utils.markdown_parser import get_cleaned_sitting_markdown


def build_sitting(hansard_sitting_date_response: HansardSittingDateResponse) -> Sitting:
    # hansardsittingdateresponse stores some Optional[int] fields as VARCHAR
    # (columns pre-date the int typing in the model).  model_dump() returns them
    # as strings; empty strings must become None before Pydantic coerces to int.
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

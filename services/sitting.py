from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.sitting import Sitting
from utils.markdown_parser import get_cleaned_sitting_markdown


def build_sitting(response: HansardSittingDateResponse) -> Sitting:
    # hansardsittingdateresponse stores some Optional[int] fields as VARCHAR
    # (columns pre-date the int typing in the model).  model_dump() returns them
    # as strings; empty strings must become None before Pydantic coerces to int.
    data = {
        k: (None if v == "" else v)
        for k, v in response.model_dump(exclude={"id"}).items()
    }
    markdown = (
        get_cleaned_sitting_markdown(response.html_full_content)
        if response.html_full_content is not None
        else None
    )
    data["markdown_content"] = markdown
    return Sitting.model_validate(data)

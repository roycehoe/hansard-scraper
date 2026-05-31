from database.handsard_sitting_date_response import HandsardSittingDateResponse
from database.sitting import Sitting
from utils.markdown_parser import get_cleaned_sitting_markdown


def build_sitting(response: HandsardSittingDateResponse) -> Sitting:
    return Sitting(
        **response.model_dump(exclude={"id"}),
        markdown_content=(
            get_cleaned_sitting_markdown(response.html_full_content)
            if response.html_full_content is not None
            else None
        ),
    )

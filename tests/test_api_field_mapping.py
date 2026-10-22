from schemas.hansard_report_response import HansardReportNewResponse
from schemas.hansard_search_result import HansardSearchResult
from schemas.hansard_topic_response import HansardTopicResponse
from scripts.validate_api_field_mapping import SYNTHETIC_NEW_FORMAT
from services.api_field_mapping import (
    get_search_result_field_losses,
    get_sitting_date_field_losses,
    get_topic_field_losses,
)
from services.hansard_sitting_date_response import (
    build_new_hansard_sitting_date_response,
)
from services.hansard_website import build_hansard_website_response

_TOPIC_HTML = "<p>x</p>"
_SITTING_DATE = "15-1-2024"


def test_search_result_keeps_every_mapped_field() -> None:
    hansard_search_result = HansardSearchResult.model_validate(
        {
            "volumeNo": "94",
            "reportType": "oral-answer",
            "reportVersion": "sprs3",
            "title": "Education Budget",
            "columnStart": "1",
            "parlNo": "14",
            "columnEnd": "5",
            "reportId": "oral-answer-123#",
            "sno": "1",
            "sittingDate": "15-01-2024",
        }
    )
    hansard_website_response = build_hansard_website_response(hansard_search_result, None)

    assert get_search_result_field_losses(hansard_search_result, hansard_website_response) == []


def test_topic_text_carried_into_the_mapped_field_is_no_loss() -> None:
    hansard_topic_response = HansardTopicResponse.model_validate({"resultHTML": {"content": _TOPIC_HTML}})

    assert get_topic_field_losses(hansard_topic_response, _TOPIC_HTML) == []


def test_topic_text_missing_from_the_mapped_field_is_one_loss() -> None:
    hansard_topic_response = HansardTopicResponse.model_validate({"resultHTML": {"content": _TOPIC_HTML}})

    assert len(get_topic_field_losses(hansard_topic_response, None)) == 1


def test_newer_system_text_moved_to_html_content_is_one_loss() -> None:
    hansard_topic_response = HansardTopicResponse.model_validate({"htmlContent": _TOPIC_HTML})

    assert len(get_topic_field_losses(hansard_topic_response, None)) == 1


def test_empty_topic_body_is_no_loss() -> None:
    assert get_topic_field_losses(HansardTopicResponse(), None) == []


def test_new_format_sitting_keeps_every_mapped_field() -> None:
    hansard_report_response = HansardReportNewResponse.model_validate(SYNTHETIC_NEW_FORMAT)
    hansard_sitting_date_response = build_new_hansard_sitting_date_response(hansard_report_response, _SITTING_DATE)

    assert get_sitting_date_field_losses(hansard_report_response, hansard_sitting_date_response) == []


def test_new_format_sitting_with_a_dropped_parliament_number_is_one_loss() -> None:
    hansard_report_response = HansardReportNewResponse.model_validate(SYNTHETIC_NEW_FORMAT)
    hansard_sitting_date_response = build_new_hansard_sitting_date_response(hansard_report_response, _SITTING_DATE)
    hansard_sitting_date_response.parlement_no = None

    field_losses = get_sitting_date_field_losses(hansard_report_response, hansard_sitting_date_response)

    assert len(field_losses) == 1
    assert "parlimentNO" in field_losses[0]

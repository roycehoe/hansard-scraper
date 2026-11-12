from typing import Optional

import pytest

from exceptions import HansardSittingReportError
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from services.hansard_sitting_date_response import (
    build_new_hansard_sitting_date_response,
    build_old_hansard_sitting_date_response,
)

_SITTING_DATE = "8-4-2009"


@pytest.mark.parametrize(
    ("wire_key", "field_name"),
    [
        ("parlNo", "parl_no"),
        ("sessionNo", "session_no"),
        ("volumeNo", "volume_no"),
        ("sittingNo", "sitting_no"),
    ],
)
def test_non_integer_number_raises_sitting_report_error_naming_field_value_and_date(
    wire_key: str, field_name: str
) -> None:
    hansard_report_response = HansardReportOldResponse.model_validate({wire_key: "abc"})

    with pytest.raises(HansardSittingReportError) as error_info:
        build_old_hansard_sitting_date_response(hansard_report_response, _SITTING_DATE)

    assert (
        str(error_info.value)
        == f"Sitting {_SITTING_DATE}: {field_name} 'abc' is not an integer"
    )


def test_integer_text_becomes_an_integer() -> None:
    hansard_report_response = HansardReportOldResponse.model_validate(
        {"parlNo": "12", "sessionNo": "2", "volumeNo": "85", "sittingNo": "9"}
    )

    hansard_sitting_date_response = build_old_hansard_sitting_date_response(
        hansard_report_response, _SITTING_DATE
    )

    assert (
        hansard_sitting_date_response.parlement_no,
        hansard_sitting_date_response.session_no,
        hansard_sitting_date_response.volume_no,
        hansard_sitting_date_response.sitting_no,
    ) == (12, 2, 85, 9)


@pytest.mark.parametrize("value", [None, ""])
def test_null_and_empty_number_stay_none(value: Optional[str]) -> None:
    hansard_report_response = HansardReportOldResponse.model_validate(
        {"parlNo": value, "sessionNo": value, "volumeNo": value, "sittingNo": value}
    )

    hansard_sitting_date_response = build_old_hansard_sitting_date_response(
        hansard_report_response, _SITTING_DATE
    )

    assert hansard_sitting_date_response.parlement_no is None
    assert hansard_sitting_date_response.session_no is None
    assert hansard_sitting_date_response.volume_no is None
    assert hansard_sitting_date_response.sitting_no is None


def test_error_body_still_builds() -> None:
    hansard_report_response = HansardReportOldResponse.model_validate(
        {"errorCode": "404", "description": "No report for this date"}
    )

    hansard_sitting_date_response = build_old_hansard_sitting_date_response(
        hansard_report_response, _SITTING_DATE
    )

    assert hansard_sitting_date_response.sitting_date == _SITTING_DATE
    assert hansard_sitting_date_response.parlement_no is None
    assert hansard_sitting_date_response.sitting_no is None


def test_new_format_sitting_keeps_the_four_nested_lists_as_json_text() -> None:
    hansard_report_response = HansardReportNewResponse.model_validate(
        {
            "takesSectionVOList": [{"title": "Prayers"}],
            "annexureList": [],
            "vernacularList": [{"vernacularID": 7}],
            "a2bList": [{"billTitle": "A Bill"}],
        }
    )

    hansard_sitting_date_response = build_new_hansard_sitting_date_response(
        hansard_report_response, _SITTING_DATE
    )

    assert (
        hansard_sitting_date_response.sections,
        hansard_sitting_date_response.annexures,
        hansard_sitting_date_response.vernaculars,
        hansard_sitting_date_response.a2b,
    ) == (
        '[{"title": "Prayers"}]',
        "[]",
        '[{"vernacularID": 7}]',
        '[{"billTitle": "A Bill"}]',
    )


def test_new_format_sitting_without_the_lists_leaves_the_four_columns_null() -> None:
    hansard_sitting_date_response = build_new_hansard_sitting_date_response(
        HansardReportNewResponse(), _SITTING_DATE
    )

    assert (
        hansard_sitting_date_response.sections,
        hansard_sitting_date_response.annexures,
        hansard_sitting_date_response.vernaculars,
        hansard_sitting_date_response.a2b,
    ) == (None, None, None, None)


def test_old_format_sitting_leaves_the_four_nested_list_columns_null() -> None:
    hansard_sitting_date_response = build_old_hansard_sitting_date_response(
        HansardReportOldResponse(), _SITTING_DATE
    )

    assert (
        hansard_sitting_date_response.sections,
        hansard_sitting_date_response.annexures,
        hansard_sitting_date_response.vernaculars,
        hansard_sitting_date_response.a2b,
    ) == (None, None, None, None)

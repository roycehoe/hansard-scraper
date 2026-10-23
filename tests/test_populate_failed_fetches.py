from collections.abc import Iterator
from datetime import date
from typing import Union

import httpx
import pytest
from sqlmodel import Session

import populate.hansard_response_contents as hansard_response_contents
import populate.hansard_responses as hansard_responses
import populate.hansard_sitting_dates as hansard_sitting_dates
import populate.sitting_details as sitting_details
from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from crud.hansard_website_response import CRUDHansardWebsiteResponse
from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.hansard_website_response import HansardWebsiteResponse
from database.sitting import Sitting
from exceptions import HansardGatewayError
from logs import logger
from populate.hansard_response_contents import populate_hansard_response_contents
from populate.hansard_responses import populate_hansard_responses
from populate.hansard_sitting_dates import populate_hansard_sitting_dates
from populate.sitting_details import populate_sitting_details
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from schemas.hansard_search_result import HansardSearchResult
from schemas.hansard_topic_response import HansardTopicResponse
from services.sitting import build_sitting
from tests.refresh_fixtures import FakeParliament, load_fixture

_TOPIC_CONTENT = "<p><strong>Mr Speaker:</strong> Order.</p>"
_SITTING_DATE = "9-9-2024"


@pytest.fixture
def messages() -> Iterator[list[str]]:
    logged_messages: list[str] = []
    sink_id = logger.add(logged_messages.append, format="{message}")
    yield logged_messages
    logger.remove(sink_id)


def _get_summary_line(messages: list[str], prefix: str) -> str:
    summary_lines = [message.strip() for message in messages if message.startswith(prefix)]
    assert len(summary_lines) == 1
    return summary_lines[0]


async def _fail_topic_fetch(topic_id: str, client: httpx.AsyncClient) -> HansardTopicResponse:
    raise HansardGatewayError(f"no topic {topic_id}")


async def _fetch_topic_with_text(topic_id: str, client: httpx.AsyncClient) -> HansardTopicResponse:
    return HansardTopicResponse.model_validate({"resultHTML": {"content": _TOPIC_CONTENT}})


async def _fetch_topic_without_text(topic_id: str, client: httpx.AsyncClient) -> HansardTopicResponse:
    return HansardTopicResponse.model_validate({"resultHTML": {}})


async def _fail_report_fetch(
    sitting_date: str, client: httpx.AsyncClient
) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
    raise HansardGatewayError(f"no sitting {sitting_date}")


async def _fetch_report(
    sitting_date: str, client: httpx.AsyncClient
) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
    return HansardReportNewResponse.model_validate(FakeParliament().stored_sitting)


def _fetch_search_results(from_date: date, to_date: date) -> list[HansardSearchResult]:
    return [HansardSearchResult.model_validate(load_fixture("new_sitting.json")["search_results"][0])]


def _seed_website_response_without_content(session: Session) -> None:
    website_response = load_fixture("stored_sitting.json")["website_responses"][0]
    session.add(HansardWebsiteResponse.model_validate({**website_response, "content": None}))
    session.commit()


def _seed_sitting_without_details(session: Session) -> Sitting:
    hansard_sitting_date_response = HansardSittingDateResponse.model_validate(
        load_fixture("stored_sitting.json")["sitting_date_response"]
    )
    sitting = build_sitting(hansard_sitting_date_response)
    session.add_all([hansard_sitting_date_response, sitting])
    session.commit()
    return sitting


def test_failed_topic_fetch_is_counted_in_the_contents_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_website_response_without_content(scratch_session)
    monkeypatch.setattr(hansard_response_contents, "get_hansard_topic_response_async", _fail_topic_fetch)

    populate_hansard_response_contents(scratch_session)

    assert (
        _get_summary_line(messages, "Hansard response contents:")
        == "Hansard response contents: 0 ids filled, 1 ids failed, 1 fetches failed"
    )
    assert [website_response.content for website_response in CRUDHansardWebsiteResponse(scratch_session).get_all()] == [None]


def test_working_topic_fetch_counts_no_failed_fetch_in_the_contents_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_website_response_without_content(scratch_session)
    monkeypatch.setattr(hansard_response_contents, "get_hansard_topic_response_async", _fetch_topic_with_text)

    populate_hansard_response_contents(scratch_session)

    assert (
        _get_summary_line(messages, "Hansard response contents:")
        == "Hansard response contents: 1 ids filled, 0 ids failed, 0 fetches failed"
    )


def test_topic_without_text_is_not_counted_as_a_failed_fetch_in_the_contents_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_website_response_without_content(scratch_session)
    monkeypatch.setattr(hansard_response_contents, "get_hansard_topic_response_async", _fetch_topic_without_text)

    populate_hansard_response_contents(scratch_session)

    assert (
        _get_summary_line(messages, "Hansard response contents:")
        == "Hansard response contents: 0 ids filled, 1 ids failed, 0 fetches failed"
    )


def test_failed_report_fetch_is_counted_in_the_sitting_details_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sitting = _seed_sitting_without_details(scratch_session)
    monkeypatch.setattr(sitting_details, "get_hansard_report_response_async", _fail_report_fetch)

    populate_sitting_details(scratch_session)

    assert (
        _get_summary_line(messages, "Sitting details:")
        == "Sitting details: 0 sittings filled, 1 sittings skipped, 1 fetches failed"
    )
    scratch_session.refresh(sitting)
    assert sitting.sections is None
    assert sitting.annexures is None
    assert sitting.vernaculars is None
    assert sitting.a2b is None
    assert sitting.html_full_content is None


def test_working_report_fetch_counts_no_failed_fetch_in_the_sitting_details_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_sitting_without_details(scratch_session)
    monkeypatch.setattr(sitting_details, "get_hansard_report_response_async", _fetch_report)

    populate_sitting_details(scratch_session)

    assert (
        _get_summary_line(messages, "Sitting details:")
        == "Sitting details: 1 sittings filled, 0 sittings skipped, 0 fetches failed"
    )


def test_failed_report_fetch_is_counted_in_the_sitting_dates_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_website_response_without_content(scratch_session)
    monkeypatch.setattr(hansard_sitting_dates, "get_hansard_report_response_async", _fail_report_fetch)

    populate_hansard_sitting_dates(scratch_session)

    assert (
        _get_summary_line(messages, "Hansard sitting dates:")
        == "Hansard sitting dates: 0 stored, 1 fetches failed"
    )
    assert CRUDHansardSittingDateResponse(scratch_session).get_sitting_dates_by_sitting_date_not_null() == set()


def test_working_report_fetch_counts_no_failed_fetch_in_the_sitting_dates_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_website_response_without_content(scratch_session)
    monkeypatch.setattr(hansard_sitting_dates, "get_hansard_report_response_async", _fetch_report)

    populate_hansard_sitting_dates(scratch_session)

    assert (
        _get_summary_line(messages, "Hansard sitting dates:")
        == "Hansard sitting dates: 1 stored, 0 fetches failed"
    )
    assert CRUDHansardSittingDateResponse(scratch_session).get_sitting_dates_by_sitting_date_not_null() == {_SITTING_DATE}


def test_failed_topic_fetch_is_counted_in_the_responses_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hansard_responses, "get_all_hansard_search_results", _fetch_search_results)
    monkeypatch.setattr(hansard_responses, "get_hansard_topic_response_async", _fail_topic_fetch)

    populate_hansard_responses(scratch_session)

    assert _get_summary_line(messages, "Hansard responses:") == "Hansard responses: 1 stored, 1 fetches failed"
    assert [website_response.content for website_response in CRUDHansardWebsiteResponse(scratch_session).get_all()] == [None]


def test_working_topic_fetch_counts_no_failed_fetch_in_the_responses_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hansard_responses, "get_all_hansard_search_results", _fetch_search_results)
    monkeypatch.setattr(hansard_responses, "get_hansard_topic_response_async", _fetch_topic_with_text)

    populate_hansard_responses(scratch_session)

    assert _get_summary_line(messages, "Hansard responses:") == "Hansard responses: 1 stored, 0 fetches failed"
    assert [website_response.content for website_response in CRUDHansardWebsiteResponse(scratch_session).get_all()] == [_TOPIC_CONTENT]


def test_topic_without_text_is_not_counted_as_a_failed_fetch_in_the_responses_summary(
    scratch_session: Session, messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hansard_responses, "get_all_hansard_search_results", _fetch_search_results)
    monkeypatch.setattr(hansard_responses, "get_hansard_topic_response_async", _fetch_topic_without_text)

    populate_hansard_responses(scratch_session)

    assert _get_summary_line(messages, "Hansard responses:") == "Hansard responses: 1 stored, 0 fetches failed"
    assert [website_response.content for website_response in CRUDHansardWebsiteResponse(scratch_session).get_all()] == [None]

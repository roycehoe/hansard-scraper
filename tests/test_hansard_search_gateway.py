from datetime import date
from typing import Optional

import pytest
import requests

from exceptions import HansardGatewayError, HansardSearchRangeError
from gateway import hansard_search
from gateway.hansard_search import (
    get_all_hansard_search_results,
    get_hansard_search_results,
    get_window_hansard_search_results,
)
from gateway.http import CRAWL_PACER
from schemas.hansard_search_result import HansardSearchResult

_FROM_DATE = date(2025, 4, 1)
_TO_DATE = date(2025, 4, 30)


class _FakeResponse:
    status_code = 200

    def __init__(self, body: object):
        self.body = body
        self.text = ""

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self.body


def _get_zero_time() -> float:
    return 0.0


def _skip_sleep(seconds: float) -> None:
    pass


async def _skip_async_sleep(seconds: float) -> None:
    pass


@pytest.fixture
def no_op_pacer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CRAWL_PACER, "clock", _get_zero_time)
    monkeypatch.setattr(CRAWL_PACER, "sleep", _skip_sleep)
    monkeypatch.setattr(CRAWL_PACER, "async_sleep", _skip_async_sleep)
    monkeypatch.setattr(CRAWL_PACER, "last_request_ended_at", None)


def _build_search_result(max_result: Optional[str]) -> HansardSearchResult:
    return HansardSearchResult(
        volume_no="95",
        report_type="oral-answer",
        report_version="sprs3",
        title="Example title",
        column_start="1",
        parl_no="14",
        column_end="2",
        report_id="oral-answer-1234",
        sno="1",
        sitting_date="1-4-2025",
        max_result=max_result,
    )


def _post_body(monkeypatch: pytest.MonkeyPatch, body: object) -> None:
    def fake_post(**kwargs: object) -> _FakeResponse:
        return _FakeResponse(body)

    monkeypatch.setattr(requests, "post", fake_post)


def _serve_first_page(monkeypatch: pytest.MonkeyPatch, max_result: Optional[str]) -> None:
    def fake_get_page(start_index: int, from_date: date, to_date: date) -> list[HansardSearchResult]:
        return [_build_search_result(max_result)]

    monkeypatch.setattr(hansard_search, "_get_page_with_retries", fake_get_page)


def test_hit_that_is_not_an_object_raises_gateway_error(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _post_body(monkeypatch, [1])

    with pytest.raises(HansardGatewayError):
        get_hansard_search_results(0, 19, _FROM_DATE, _TO_DATE)


def test_body_that_is_not_a_list_is_an_empty_page(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _post_body(monkeypatch, {})

    assert get_hansard_search_results(0, 19, _FROM_DATE, _TO_DATE) == []


def test_first_hit_without_a_total_raises_gateway_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve_first_page(monkeypatch, None)

    with pytest.raises(HansardGatewayError):
        get_window_hansard_search_results(_FROM_DATE, _TO_DATE)


def test_first_hit_with_a_total_that_is_not_a_number_raises_gateway_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve_first_page(monkeypatch, "many")

    with pytest.raises(HansardGatewayError):
        get_window_hansard_search_results(_FROM_DATE, _TO_DATE)


def test_range_that_starts_after_it_ends_raises_search_range_error() -> None:
    with pytest.raises(HansardSearchRangeError):
        get_all_hansard_search_results(_TO_DATE, _FROM_DATE)

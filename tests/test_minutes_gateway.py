from typing import Optional

import pytest
import requests

from exceptions import HansardGatewayError
from gateway.http import CRAWL_HEADERS, CRAWL_PACER
from gateway.minutes import (
    REQUEST_TIMEOUT_SECONDS,
    get_minutes_file_response,
    get_minutes_index_response,
)
from schemas.minutes_response import MinutesResponse
from settings import settings

_FILE_URL = "https://media.example/api/media/abc/VP-5Aug2026.pdf"
_INDEX_BODY = b"<html>"
_ACCEPTED_STATUS = 202
_NOT_FOUND_STATUS = 404
_OK_STATUS = 200


class _FakeResponse:
    def __init__(
        self, status_code: int, content: bytes, headers: Optional[dict[str, str]] = None
    ):
        self.status_code = status_code
        self.content = content
        self.text = ""
        self.headers = {} if headers is None else headers


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


def test_index_response_carries_status_and_bytes(
    monkeypatch: pytest.MonkeyPatch, no_op_pacer: None
) -> None:
    def fake_get(**kwargs: object) -> _FakeResponse:
        assert kwargs["url"] == settings.minutes_index_url
        assert kwargs["headers"] == CRAWL_HEADERS
        assert kwargs["timeout"] == REQUEST_TIMEOUT_SECONDS
        return _FakeResponse(_OK_STATUS, _INDEX_BODY)

    monkeypatch.setattr(requests, "get", fake_get)

    assert get_minutes_index_response() == MinutesResponse(
        url=settings.minutes_index_url, status_code=_OK_STATUS, content=_INDEX_BODY
    )


def test_index_response_carries_the_bot_filter_headers(
    monkeypatch: pytest.MonkeyPatch, no_op_pacer: None
) -> None:
    def fake_get(**kwargs: object) -> _FakeResponse:
        return _FakeResponse(
            _ACCEPTED_STATUS,
            b"",
            {"x-amzn-waf-action": "challenge", "x-cache": "Error from cloudfront"},
        )

    monkeypatch.setattr(requests, "get", fake_get)

    minutes_response = get_minutes_index_response()

    assert minutes_response.status_code == _ACCEPTED_STATUS
    assert minutes_response.waf_action == "challenge"
    assert minutes_response.cache_status == "Error from cloudfront"


def test_file_response_carries_a_non_200_status(
    monkeypatch: pytest.MonkeyPatch, no_op_pacer: None
) -> None:
    def fake_get(**kwargs: object) -> _FakeResponse:
        return _FakeResponse(_NOT_FOUND_STATUS, b"")

    monkeypatch.setattr(requests, "get", fake_get)

    minutes_response = get_minutes_file_response(_FILE_URL)

    assert minutes_response.status_code == _NOT_FOUND_STATUS
    assert minutes_response.url == _FILE_URL


def test_network_failure_raises_gateway_error_naming_the_url(
    monkeypatch: pytest.MonkeyPatch, no_op_pacer: None
) -> None:
    def fake_get(**kwargs: object) -> _FakeResponse:
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(HansardGatewayError, match=_FILE_URL):
        get_minutes_file_response(_FILE_URL)


def test_every_request_waits_on_the_crawl_pacer(
    monkeypatch: pytest.MonkeyPatch, no_op_pacer: None
) -> None:
    events: list[str] = []

    def record_sleep(seconds: float) -> None:
        events.append("sleep")

    def fake_get(**kwargs: object) -> _FakeResponse:
        events.append("get")
        return _FakeResponse(_OK_STATUS, _INDEX_BODY)

    monkeypatch.setattr(CRAWL_PACER, "sleep", record_sleep)
    monkeypatch.setattr(requests, "get", fake_get)

    get_minutes_file_response(_FILE_URL)

    assert events == ["sleep", "get"]

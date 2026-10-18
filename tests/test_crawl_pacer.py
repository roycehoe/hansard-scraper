import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from itertools import pairwise
from typing import Optional

import httpx
import pytest

import gateway.http
from gateway.http import (
    CRAWL_GAP_SECONDS,
    CRAWL_PACER,
    CRAWL_USER_AGENT,
    async_post_with_retry,
    paced_request,
)

_REQUEST_SECONDS = 0.25
_URL = "https://pacer.test/topic"
_HTTP_OK = 200
_HTTP_TOO_MANY_REQUESTS = 429
_GATHERED_REQUEST_COUNT = 5
_SYNC_REQUEST_COUNT = 3
_FIXED_JITTER_SECONDS = 0.5
_RETRY_STATUS_CODES = (_HTTP_TOO_MANY_REQUESTS, _HTTP_TOO_MANY_REQUESTS, _HTTP_OK)


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def get_time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    async def async_sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


@dataclass
class _RecordedRequest:
    started_at: float
    ended_at: float
    user_agent: Optional[str]


_AsyncHandler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    fake_clock = _FakeClock()
    monkeypatch.setattr(CRAWL_PACER, "clock", fake_clock.get_time)
    monkeypatch.setattr(CRAWL_PACER, "sleep", fake_clock.sleep)
    monkeypatch.setattr(CRAWL_PACER, "async_sleep", fake_clock.async_sleep)
    monkeypatch.setattr(CRAWL_PACER, "last_request_ended_at", None)
    return fake_clock


def _get_async_handler(fake_clock: _FakeClock, recorded_requests: list[_RecordedRequest], status_codes: list[int]) -> _AsyncHandler:
    async def handle_request(request: httpx.Request) -> httpx.Response:
        started_at = fake_clock.now
        fake_clock.sleep(_REQUEST_SECONDS)
        await asyncio.sleep(0)
        recorded_requests.append(_RecordedRequest(started_at, fake_clock.now, request.headers.get("User-Agent")))
        if len(status_codes) > 1:
            return httpx.Response(status_codes.pop(0))
        return httpx.Response(status_codes[0])

    return handle_request


def _get_fixed_jitter(low: float, high: float) -> float:
    return _FIXED_JITTER_SECONDS


async def _post_gathered_requests(handler: _AsyncHandler) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await asyncio.gather(*(async_post_with_retry(client, _URL, {}) for _ in range(_GATHERED_REQUEST_COUNT)))


async def _post_one_request(handler: _AsyncHandler) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await async_post_with_retry(client, _URL, {})


def _assert_paced(recorded_requests: list[_RecordedRequest]) -> None:
    for previous_request, next_request in pairwise(recorded_requests):
        assert next_request.started_at >= previous_request.ended_at
        assert next_request.started_at - previous_request.ended_at >= CRAWL_GAP_SECONDS


def test_gathered_requests_go_one_at_a_time_two_seconds_apart(fake_clock: _FakeClock) -> None:
    recorded_requests: list[_RecordedRequest] = []

    asyncio.run(_post_gathered_requests(_get_async_handler(fake_clock, recorded_requests, [_HTTP_OK])))

    assert len(recorded_requests) == _GATHERED_REQUEST_COUNT
    _assert_paced(recorded_requests)


def test_retries_are_paced(fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway.http, "_BASE_DELAY", 0.0)
    monkeypatch.setattr(gateway.http.random, "uniform", _get_fixed_jitter)
    recorded_requests: list[_RecordedRequest] = []

    response = asyncio.run(_post_one_request(_get_async_handler(fake_clock, recorded_requests, list(_RETRY_STATUS_CODES))))

    assert len(recorded_requests) == len(_RETRY_STATUS_CODES)
    _assert_paced(recorded_requests)
    assert response.status_code == _HTTP_OK


def test_sync_requests_are_paced(fake_clock: _FakeClock) -> None:
    recorded_requests: list[_RecordedRequest] = []

    for _ in range(_SYNC_REQUEST_COUNT):
        with paced_request():
            started_at = fake_clock.now
            fake_clock.sleep(_REQUEST_SECONDS)
            recorded_requests.append(_RecordedRequest(started_at, fake_clock.now, None))

    assert len(recorded_requests) == _SYNC_REQUEST_COUNT
    _assert_paced(recorded_requests)


def test_a_failed_request_still_counts_toward_the_gap(fake_clock: _FakeClock) -> None:
    with pytest.raises(ValueError):
        with paced_request():
            fake_clock.sleep(_REQUEST_SECONDS)
            raise ValueError("request failed")

    assert CRAWL_PACER.last_request_ended_at == _REQUEST_SECONDS
    with paced_request():
        started_at = fake_clock.now
    assert started_at - _REQUEST_SECONDS >= CRAWL_GAP_SECONDS


def test_async_requests_send_the_user_agent(fake_clock: _FakeClock) -> None:
    recorded_requests: list[_RecordedRequest] = []

    asyncio.run(_post_gathered_requests(_get_async_handler(fake_clock, recorded_requests, [_HTTP_OK])))

    assert len(recorded_requests) == _GATHERED_REQUEST_COUNT
    assert all(recorded_request.user_agent == CRAWL_USER_AGENT for recorded_request in recorded_requests)

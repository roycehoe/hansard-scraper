import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Optional

import httpx
import pytest
import requests

import gateway.http
from exceptions import HansardGatewayError
from gateway.hansard_report import get_hansard_report_response
from gateway.hansard_search import get_hansard_search_results
from gateway.hansard_topic import get_hansard_topic_response
from gateway.http import (
    CRAWL_PACER,
    CRAWL_USER_AGENT,
    async_post_with_retry,
    paced_request,
    send_with_retry,
)
from gateway.speakers_by_parliament import (
    get_all_speakers,
    get_speakers_by_parliament_number,
)
from settings import AppSettings, settings

_REQUEST_SECONDS = 0.25
_URL = "https://pacer.test/topic"
_HTTP_OK = 200
_HTTP_TOO_MANY_REQUESTS = 429
_GATHERED_REQUEST_COUNT = 5
_SYNC_REQUEST_COUNT = 3
_FIXED_JITTER_SECONDS = 0.5
_RETRY_STATUS_CODES = (_HTTP_TOO_MANY_REQUESTS, _HTTP_TOO_MANY_REQUESTS, _HTTP_OK)
_SEARCH_START_INDEX = 0
_SEARCH_END_INDEX = 19
_REPORT_ID = "x"
_SITTING_DATE = "8-4-2025"
_SYNC_GATEWAY_REQUEST_COUNT = 3
_SPEAKER_REQUEST_COUNT = 2
_SPEAKER_PARLIAMENT_NUMBER = 15
_MEMBER_LIST_PAGE_FILE = Path(__file__).parent / "fixtures" / "parliament_member_list_page.html"
_FAILED_SEND_COUNT = 2
_ASYNC_ATTEMPT_COUNT = 2


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


class _FakeSyncResponse:
    status_code = _HTTP_OK

    def __init__(self, body: object):
        self.body = body
        self.text = ""

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self.body


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
        assert next_request.started_at - previous_request.ended_at >= settings.crawl_gap_seconds


def test_gathered_requests_go_one_at_a_time_two_seconds_apart(fake_clock: _FakeClock) -> None:
    recorded_requests: list[_RecordedRequest] = []

    asyncio.run(_post_gathered_requests(_get_async_handler(fake_clock, recorded_requests, [_HTTP_OK])))

    assert len(recorded_requests) == _GATHERED_REQUEST_COUNT
    assert all(recorded_request.user_agent == CRAWL_USER_AGENT for recorded_request in recorded_requests)
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
    assert started_at - _REQUEST_SECONDS >= settings.crawl_gap_seconds


def test_sync_gateways_send_the_user_agent_and_are_paced(fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    recorded_requests: list[_RecordedRequest] = []

    def fake_post(url: str, json: object, headers: dict, **kwargs: object) -> _FakeSyncResponse:
        started_at = fake_clock.now
        fake_clock.sleep(_REQUEST_SECONDS)
        recorded_requests.append(_RecordedRequest(started_at, fake_clock.now, headers["User-Agent"]))
        if url == settings.hansard_search_url:
            return _FakeSyncResponse([])
        return _FakeSyncResponse({})

    monkeypatch.setattr(requests, "post", fake_post)

    get_hansard_search_results(_SEARCH_START_INDEX, _SEARCH_END_INDEX)
    get_hansard_topic_response(_REPORT_ID)
    get_hansard_report_response(_SITTING_DATE)

    assert len(recorded_requests) == _SYNC_GATEWAY_REQUEST_COUNT
    assert all(recorded_request.user_agent == CRAWL_USER_AGENT for recorded_request in recorded_requests)
    _assert_paced(recorded_requests)


def test_speaker_requests_send_the_user_agent_and_are_paced(fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    recorded_requests: list[_RecordedRequest] = []

    member_list_page = _MEMBER_LIST_PAGE_FILE.read_text()

    def fake_get(url: str, headers: dict, **kwargs: object) -> _FakeSyncResponse:
        started_at = fake_clock.now
        fake_clock.sleep(_REQUEST_SECONDS)
        recorded_requests.append(_RecordedRequest(started_at, fake_clock.now, headers["User-Agent"]))
        member_list_response = _FakeSyncResponse(None)
        member_list_response.text = member_list_page
        return member_list_response

    monkeypatch.setattr(requests, "get", fake_get)

    get_all_speakers()
    get_speakers_by_parliament_number(_SPEAKER_PARLIAMENT_NUMBER)

    assert len(recorded_requests) == _SPEAKER_REQUEST_COUNT
    assert all(recorded_request.user_agent == CRAWL_USER_AGENT for recorded_request in recorded_requests)
    _assert_paced(recorded_requests)


def _remove_backoff_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway.http, "_BASE_DELAY", 0.0)
    monkeypatch.setattr(gateway.http.random, "uniform", _get_fixed_jitter)


def test_sync_transport_error_is_retried_through_the_pacer(fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    _remove_backoff_delay(monkeypatch)
    recorded_requests: list[_RecordedRequest] = []
    sync_response = requests.Response()

    def fake_send() -> requests.Response:
        started_at = fake_clock.now
        fake_clock.sleep(_REQUEST_SECONDS)
        recorded_requests.append(_RecordedRequest(started_at, fake_clock.now, None))
        if len(recorded_requests) <= _FAILED_SEND_COUNT:
            raise requests.exceptions.ConnectionError("connection refused")
        return sync_response

    assert send_with_retry(fake_send) is sync_response
    assert len(recorded_requests) == _FAILED_SEND_COUNT + 1
    _assert_paced(recorded_requests)


def test_sync_transport_error_gives_up_after_the_last_attempt(fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    _remove_backoff_delay(monkeypatch)
    recorded_requests: list[_RecordedRequest] = []

    def fake_send() -> requests.Response:
        started_at = fake_clock.now
        fake_clock.sleep(_REQUEST_SECONDS)
        recorded_requests.append(_RecordedRequest(started_at, fake_clock.now, None))
        raise requests.exceptions.Timeout("timed out")

    def fake_post(**kwargs: object) -> requests.Response:
        raise requests.exceptions.ConnectionError("connection refused")

    with pytest.raises(requests.exceptions.Timeout):
        send_with_retry(fake_send)
    assert len(recorded_requests) == gateway.http._MAX_RETRIES + 1
    _assert_paced(recorded_requests)

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(HansardGatewayError):
        get_hansard_topic_response(_REPORT_ID)


def test_async_transport_error_is_retried_through_the_pacer(fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    _remove_backoff_delay(monkeypatch)
    recorded_requests: list[_RecordedRequest] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        started_at = fake_clock.now
        fake_clock.sleep(_REQUEST_SECONDS)
        await asyncio.sleep(0)
        recorded_requests.append(_RecordedRequest(started_at, fake_clock.now, request.headers.get("User-Agent")))
        if len(recorded_requests) == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(_HTTP_OK)

    response = asyncio.run(_post_one_request(handle_request))

    assert response.status_code == _HTTP_OK
    assert len(recorded_requests) == _ASYNC_ATTEMPT_COUNT
    _assert_paced(recorded_requests)


_LETTER_CRAWL_GAP_SECONDS = 2.0


def test_crawl_gap_defaults_to_the_gap_the_letter_promises() -> None:
    assert AppSettings.model_fields["crawl_gap_seconds"].default == _LETTER_CRAWL_GAP_SECONDS

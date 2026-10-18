import asyncio
import json

import httpx
import pytest
import requests

from exceptions import HansardGatewayError
from gateway.hansard_topic import (
    _REQUEST_TIMEOUT_SECONDS,
    get_hansard_topic_response,
    get_hansard_topic_response_async,
)
from gateway.http import CRAWL_PACER

_REPORT_ID = "oral-answer-1234"


class _FakeResponse:
    def __init__(self, body: object):
        self.body = body

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


@pytest.mark.parametrize("body", [None, []])
def test_body_that_is_not_an_object_raises_gateway_error(body: object, monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    def fake_post(**kwargs: object) -> _FakeResponse:
        assert kwargs["timeout"] == _REQUEST_TIMEOUT_SECONDS
        return _FakeResponse(body)

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(HansardGatewayError):
        get_hansard_topic_response(_REPORT_ID)


@pytest.mark.parametrize("body", [None, []])
def test_async_body_that_is_not_an_object_raises_gateway_error(body: object, no_op_pacer: None) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(body).encode())

    async def fetch() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await get_hansard_topic_response_async(_REPORT_ID, client)

    with pytest.raises(HansardGatewayError):
        asyncio.run(fetch())

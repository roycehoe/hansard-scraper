import pytest
import requests

from exceptions import HansardGatewayError
from gateway.hansard_report import REQUEST_TIMEOUT_SECONDS, get_hansard_report_response
from gateway.http import CRAWL_PACER, MAX_RETRIES

_SITTING_DATE = "8-4-2025"
_HTTP_INTERNAL_SERVER_ERROR = 500
_NO_SITTING_TEXT = '{"errorCode":500,"description":"Unable to process the request. Please try after sometime."}'


class _FakeResponse:
    status_code = 200

    def __init__(self, body: object):
        self.body = body
        self.text = ""

    def json(self) -> object:
        return self.body


class _FakeNoSittingResponse:
    status_code = _HTTP_INTERNAL_SERVER_ERROR
    text = _NO_SITTING_TEXT

    def raise_for_status(self) -> None:
        raise requests.HTTPError(f"{self.status_code} Server Error")


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
def test_body_that_is_not_an_object_raises_gateway_error(
    body: object, monkeypatch: pytest.MonkeyPatch, no_op_pacer: None
) -> None:
    def fake_post(**kwargs: object) -> _FakeResponse:
        assert kwargs["timeout"] == REQUEST_TIMEOUT_SECONDS
        return _FakeResponse(body)

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(HansardGatewayError):
        get_hansard_report_response(_SITTING_DATE)


@pytest.mark.parametrize(
    ("max_retries", "request_count"), [(0, 1), (MAX_RETRIES, MAX_RETRIES + 1)]
)
def test_no_sitting_answer_is_requested_once_plus_max_retries(
    max_retries: int,
    request_count: int,
    monkeypatch: pytest.MonkeyPatch,
    no_op_pacer: None,
) -> None:
    sent_requests: list[dict[str, object]] = []

    def fake_post(**kwargs: object) -> _FakeNoSittingResponse:
        sent_requests.append(kwargs)
        return _FakeNoSittingResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(HansardGatewayError):
        get_hansard_report_response(_SITTING_DATE, max_retries)
    assert len(sent_requests) == request_count

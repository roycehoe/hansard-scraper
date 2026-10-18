from collections.abc import Iterator
from contextlib import contextmanager

import pytest
import requests

import gateway.hansard_report
from exceptions import HansardGatewayError
from gateway.hansard_report import get_hansard_report_response

_SITTING_DATE = "8-4-2025"


class _FakeResponse:
    def __init__(self, body: object):
        self.body = body

    def json(self) -> object:
        return self.body


@contextmanager
def _skip_pacing() -> Iterator[None]:
    yield


@pytest.mark.parametrize("body", [None, []])
def test_body_that_is_not_an_object_raises_gateway_error(body: object, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, json: object, headers: object) -> _FakeResponse:
        return _FakeResponse(body)

    monkeypatch.setattr(gateway.hansard_report, "paced_request", _skip_pacing)
    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(HansardGatewayError):
        get_hansard_report_response(_SITTING_DATE)

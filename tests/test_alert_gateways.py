from dataclasses import dataclass, field

import pytest
import requests

import gateway.healthchecks
import gateway.telegram
from exceptions import HansardGatewayError
from gateway.healthchecks import send_healthchecks_ping
from gateway.telegram import send_telegram_message

_BOT_TOKEN = "TOKEN"
_SECRET_BOT_TOKEN = "SECRET"
_CHAT_ID = "12345"
_TEXT = "Hansard refresh halted."
_PING_URL = "https://hc-ping.test/check-key"
_TELEGRAM_PATH_END = "/botTOKEN/sendMessage"
_FAILED_TELEGRAM_URL = "https://api.telegram.org/botSECRET/sendMessage"
_FAILED_PING_URL = "https://hc-ping.test/SECRET"


class _FakeResponse:
    def raise_for_status(self) -> None:
        pass


@dataclass
class _RequestRecorder:
    urls: list[str] = field(default_factory=list)
    bodies: list[object] = field(default_factory=list)
    timeouts: list[object] = field(default_factory=list)

    def post(self, url: str, json: object, timeout: object) -> _FakeResponse:
        self.urls.append(url)
        self.bodies.append(json)
        self.timeouts.append(timeout)
        return _FakeResponse()

    def get(self, url: str, timeout: object) -> _FakeResponse:
        self.urls.append(url)
        self.timeouts.append(timeout)
        return _FakeResponse()


def _raise_telegram_connection_error(url: str, json: object, timeout: object) -> _FakeResponse:
    raise requests.exceptions.ConnectionError(_FAILED_TELEGRAM_URL)


def _raise_ping_connection_error(url: str, timeout: object) -> _FakeResponse:
    raise requests.exceptions.ConnectionError(_FAILED_PING_URL)


def test_telegram_message_posts_to_the_bot_url(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _RequestRecorder()
    monkeypatch.setattr(gateway.telegram.requests, "post", recorder.post)

    send_telegram_message(_BOT_TOKEN, _CHAT_ID, _TEXT)

    assert recorder.urls[0].endswith(_TELEGRAM_PATH_END)
    assert recorder.bodies == [{"chat_id": _CHAT_ID, "text": _TEXT}]
    assert recorder.timeouts[0] is not None


def test_healthchecks_ping_gets_the_ping_url(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _RequestRecorder()
    monkeypatch.setattr(gateway.healthchecks.requests, "get", recorder.get)

    send_healthchecks_ping(_PING_URL)

    assert recorder.urls == [_PING_URL]
    assert recorder.timeouts[0] is not None


def test_telegram_failure_hides_the_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway.telegram.requests, "post", _raise_telegram_connection_error)

    with pytest.raises(HansardGatewayError) as error_info:
        send_telegram_message(_SECRET_BOT_TOKEN, _CHAT_ID, _TEXT)

    assert _SECRET_BOT_TOKEN not in str(error_info.value)
    assert error_info.value.__cause__ is None
    assert error_info.value.__suppress_context__ is True


def test_healthchecks_failure_hides_the_ping_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway.healthchecks.requests, "get", _raise_ping_connection_error)

    with pytest.raises(HansardGatewayError) as error_info:
        send_healthchecks_ping(_FAILED_PING_URL)

    assert _SECRET_BOT_TOKEN not in str(error_info.value)
    assert error_info.value.__cause__ is None
    assert error_info.value.__suppress_context__ is True

import socket

import httpx
import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from settings import settings

_TEST_NET_ADDRESS = "192.0.2.1"
_RESERVED_HOST_NAME = "example.invalid"
_HTTP_PORT = 80
_TIMEOUT_SECONDS = 1
_SCRATCH_PORT = 5435
_SCRATCH_DATABASE = "hansard_launch"
_WRONG_DATABASE_URL = "postgresql://user:password@localhost:5435/hansard_guard_probe"
_WRONG_PORT_URL = "postgresql://user:password@localhost:5436/hansard_launch"
_WRONG_HOST_URL = "postgresql://user:password@192.0.2.1:5435/hansard_launch?connect_timeout=1"
_HOSTADDR_URL = "postgresql://user:password@localhost:5435/hansard_launch?hostaddr=192.0.2.1&connect_timeout=1"
_SCRATCH_URL_FOR_HOOK_TESTS = "postgresql://user:password@localhost:5435/hansard_launch"
_NO_PORT_URL = "postgresql://user:password@localhost/hansard_launch?connect_timeout=1"
_TEST_NET_DSN = "hostaddr=192.0.2.1 connect_timeout=1"


@pytest.fixture
def loadable_psycopg2() -> None:
    pytest.importorskip("psycopg2", reason="psycopg2 cannot load, so no test can open a database connection", exc_type=ImportError)


def _assert_connection_is_refused(database_url: str, message: str, connect_args: dict) -> None:
    engine = create_engine(database_url, connect_args=connect_args)
    with pytest.raises(RuntimeError, match=message):
        engine.connect()
    engine.dispose()


def test_a_tcp_connection_outside_loopback_is_refused() -> None:
    with pytest.raises(RuntimeError, match="Tests refuse"):
        socket.create_connection((_TEST_NET_ADDRESS, _HTTP_PORT), timeout=_TIMEOUT_SECONDS)


def test_a_socket_connect_outside_loopback_is_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_socket:
        test_socket.settimeout(_TIMEOUT_SECONDS)
        with pytest.raises(RuntimeError, match="Tests refuse"):
            test_socket.connect((_TEST_NET_ADDRESS, _HTTP_PORT))
        with pytest.raises(RuntimeError, match="Tests refuse"):
            test_socket.connect_ex((_TEST_NET_ADDRESS, _HTTP_PORT))


def test_an_address_lookup_outside_loopback_is_refused() -> None:
    with pytest.raises(RuntimeError, match="Tests refuse"):
        socket.getaddrinfo(_RESERVED_HOST_NAME, _HTTP_PORT)


def test_http_requests_outside_loopback_are_refused() -> None:
    with pytest.raises(RuntimeError, match="Tests refuse"):
        requests.get(f"http://{_TEST_NET_ADDRESS}/", timeout=_TIMEOUT_SECONDS)
    with pytest.raises(RuntimeError, match="Tests refuse"):
        httpx.get(f"http://{_TEST_NET_ADDRESS}/", timeout=_TIMEOUT_SECONDS)


@pytest.mark.usefixtures("loadable_psycopg2")
def test_a_database_other_than_the_scratch_one_is_refused() -> None:
    _assert_connection_is_refused(_WRONG_DATABASE_URL, "Tests refuse database hansard_guard_probe", {})


@pytest.mark.usefixtures("loadable_psycopg2")
def test_a_database_port_other_than_the_scratch_one_is_refused() -> None:
    _assert_connection_is_refused(_WRONG_PORT_URL, "Tests refuse database port 5436", {})


@pytest.mark.usefixtures("loadable_psycopg2")
def test_a_database_host_other_than_loopback_is_refused() -> None:
    _assert_connection_is_refused(_WRONG_HOST_URL, "Tests refuse database host 192.0.2.1", {})


@pytest.mark.usefixtures("loadable_psycopg2")
def test_a_database_hostaddr_is_refused() -> None:
    _assert_connection_is_refused(_HOSTADDR_URL, "Tests refuse a database hostaddr", {})


@pytest.mark.usefixtures("loadable_psycopg2")
def test_a_database_dsn_is_refused() -> None:
    _assert_connection_is_refused(_SCRATCH_URL_FOR_HOOK_TESTS, "Tests refuse a database dsn string", {"dsn": _TEST_NET_DSN})


@pytest.mark.usefixtures("loadable_psycopg2")
def test_a_database_connection_with_no_port_is_refused() -> None:
    _assert_connection_is_refused(_NO_PORT_URL, "Tests refuse a database connection with no port", {})


def test_no_proxy_is_used_for_parliament() -> None:
    assert requests.utils.get_environ_proxies(f"https://{_RESERVED_HOST_NAME}/") == {}


def test_settings_point_at_the_scratch_database() -> None:
    url = make_url(settings.database_url)

    assert url.port == _SCRATCH_PORT
    assert url.database == _SCRATCH_DATABASE

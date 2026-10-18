import os
import socket
from collections.abc import Callable
from typing import cast

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url

_SCRATCH_DATABASE_URL = "postgresql://user:password@localhost:5435/hansard_launch"
_ROUTING_ENV_VARS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
    "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE",
)

for routing_env_var in _ROUTING_ENV_VARS:
    os.environ.pop(routing_env_var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ["DATABASE_URL"] = _SCRATCH_DATABASE_URL

# NOTE: settings is imported below the assignment so it reads the scratch URL and never a .env URL
from settings import settings

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_SCRATCH_PORT = 5435
_SCRATCH_DATABASE = "hansard_launch"


class HansardTestGuardError(RuntimeError):
    pass


def _validate_can_use_database_url(database_url: str) -> None:
    url = make_url(database_url)
    if url.host not in _LOOPBACK_HOSTS:
        raise pytest.UsageError(f"Tests refuse database host {url.host}")
    if url.port != _SCRATCH_PORT:
        raise pytest.UsageError(f"Tests refuse database port {url.port}")
    if url.database != _SCRATCH_DATABASE:
        raise pytest.UsageError(f"Tests refuse database {url.database}")


_validate_can_use_database_url(settings.database_url)


@event.listens_for(Engine, "do_connect")
def _refuse_non_scratch_connection(dialect: object, connection_record: object, cargs: tuple, cparams: dict) -> None:
    if cargs:
        raise HansardTestGuardError("Tests refuse a positional database connection string")
    if cparams.get("host") not in _LOOPBACK_HOSTS:
        raise HansardTestGuardError(f"Tests refuse database host {cparams.get('host')}")
    if "hostaddr" in cparams:
        raise HansardTestGuardError("Tests refuse a database hostaddr")
    if "service" in cparams:
        raise HansardTestGuardError("Tests refuse a database service name")
    if "dsn" in cparams:
        raise HansardTestGuardError("Tests refuse a database dsn string")
    if cparams.get("port") is None:
        raise HansardTestGuardError("Tests refuse a database connection with no port")
    if int(cparams["port"]) != _SCRATCH_PORT:
        raise HansardTestGuardError(f"Tests refuse database port {cparams['port']}")
    if cparams.get("dbname") != _SCRATCH_DATABASE:
        raise HansardTestGuardError(f"Tests refuse database {cparams.get('dbname')}")


_ORIGINAL_SOCKET_CONNECT: Callable[..., None] = socket.socket.connect
_ORIGINAL_SOCKET_CONNECT_EX: Callable[..., int] = socket.socket.connect_ex
_ORIGINAL_CREATE_CONNECTION: Callable[..., socket.socket] = socket.create_connection
_ORIGINAL_GETADDRINFO: Callable[..., list] = socket.getaddrinfo


def _validate_can_connect_to_host(host: object) -> None:
    if host not in _LOOPBACK_HOSTS:
        raise HansardTestGuardError(f"Tests refuse a connection to {host}")


def _connect_to_loopback(self: socket.socket, address: object) -> None:
    if self.family != socket.AF_UNIX:
        _validate_can_connect_to_host(cast(tuple, address)[0])
    _ORIGINAL_SOCKET_CONNECT(self, address)


def _connect_ex_to_loopback(self: socket.socket, address: object) -> int:
    if self.family != socket.AF_UNIX:
        _validate_can_connect_to_host(cast(tuple, address)[0])
    return _ORIGINAL_SOCKET_CONNECT_EX(self, address)


def _create_loopback_connection(address: tuple, *args: object, **kwargs: object) -> socket.socket:
    _validate_can_connect_to_host(address[0])
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def _get_loopback_address_info(host: object, *args: object, **kwargs: object) -> list:
    _validate_can_connect_to_host(host)
    return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)


socket.socket.connect = _connect_to_loopback
socket.socket.connect_ex = _connect_ex_to_loopback
socket.create_connection = _create_loopback_connection
socket.getaddrinfo = _get_loopback_address_info

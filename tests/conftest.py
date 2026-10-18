import os
import socket
import uuid
from collections.abc import Callable, Iterator
from typing import cast

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlmodel import Session, SQLModel

from exceptions import HansardTestGuardError

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
import database.attendance  # noqa: F401 registers the table for create_all
import database.hansard_sitting_date_response  # noqa: F401 registers the table for create_all
import database.hansard_website_response  # noqa: F401 registers the table for create_all
import database.party_affiliation  # noqa: F401 registers the table for create_all
import database.person  # noqa: F401 registers the table for create_all
import database.refresh_run  # noqa: F401 registers the table for create_all
import database.report  # noqa: F401 registers the table for create_all
import database.sitting  # noqa: F401 registers the table for create_all
import database.speaker  # noqa: F401 registers the table for create_all
import database.speech  # noqa: F401 registers the table for create_all
from settings import settings

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_SCRATCH_PORT = 5435
_SCRATCH_DATABASE = "hansard_launch"
_TEST_SCHEMA_PREFIX = "test_"
_TEST_SCHEMA_SUFFIX_LENGTH = 12


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
def _refuse_non_scratch_connection(dialect: object, connection_record: object, connection_args: tuple, connection_params: dict) -> None:
    if connection_args:
        raise HansardTestGuardError("Tests refuse a positional database connection string")
    if connection_params.get("host") not in _LOOPBACK_HOSTS:
        raise HansardTestGuardError(f"Tests refuse database host {connection_params.get('host')}")
    if "hostaddr" in connection_params:
        raise HansardTestGuardError("Tests refuse a database hostaddr")
    if "service" in connection_params:
        raise HansardTestGuardError("Tests refuse a database service name")
    if "dsn" in connection_params:
        raise HansardTestGuardError("Tests refuse a database dsn string")
    if connection_params.get("port") is None:
        raise HansardTestGuardError("Tests refuse a database connection with no port")
    if int(connection_params["port"]) != _SCRATCH_PORT:
        raise HansardTestGuardError(f"Tests refuse database port {connection_params['port']}")
    if connection_params.get("dbname") != _SCRATCH_DATABASE:
        raise HansardTestGuardError(f"Tests refuse database {connection_params.get('dbname')}")


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


def _validate_can_use_test_schema(engine: Engine, schema: str) -> None:
    with engine.connect() as connection:
        statement = text("SELECT table_name FROM information_schema.tables WHERE table_schema = :schema")
        table_names = set(connection.execute(statement, {"schema": schema}).scalars())
    if table_names != {table.name for table in SQLModel.metadata.sorted_tables}:
        raise HansardTestGuardError(f"Test schema {schema} does not hold every table")


@pytest.fixture(scope="session")
def scratch_engine() -> Iterator[Engine]:
    schema = f"{_TEST_SCHEMA_PREFIX}{uuid.uuid4().hex[:_TEST_SCHEMA_SUFFIX_LENGTH]}"
    admin_engine = create_engine(_SCRATCH_DATABASE_URL)
    with admin_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS rum"))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(_SCRATCH_DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"})
    try:
        # NOTE: a checked create sees public's tables through the search path and would create nothing
        SQLModel.metadata.create_all(engine, checkfirst=False)
        _validate_can_use_test_schema(engine, schema)
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture
def scratch_session(scratch_engine: Engine) -> Iterator[Session]:
    with Session(scratch_engine) as session:
        yield session
    with scratch_engine.begin() as connection:
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        if not schema.startswith(_TEST_SCHEMA_PREFIX):
            raise HansardTestGuardError(f"Tests refuse to empty schema {schema}")
        table_names = ", ".join(f'"{schema}"."{table.name}"' for table in SQLModel.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))

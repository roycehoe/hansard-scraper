from database.init import build_read_only_engine, engine
from settings import settings


def test_engine_pings_a_pooled_connection_before_reuse() -> None:
    assert engine.pool._pre_ping is True


def test_engine_sends_tcp_keepalives() -> None:
    with engine.connect() as connection:
        dsn_parameters = connection.connection.dbapi_connection.get_dsn_parameters()
    assert dsn_parameters["keepalives"] == "1"
    assert dsn_parameters["keepalives_idle"] == "30"


def test_read_only_engine_sets_the_read_only_execution_option() -> None:
    read_only_engine = build_read_only_engine(settings.database_url)

    assert read_only_engine.get_execution_options()["postgresql_readonly"] is True


def test_read_only_engine_pings_a_pooled_connection_before_reuse() -> None:
    read_only_engine = build_read_only_engine(settings.database_url)

    assert read_only_engine.pool._pre_ping is True

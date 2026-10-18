from database.init import engine


def test_engine_pings_a_pooled_connection_before_reuse() -> None:
    assert engine.pool._pre_ping is True


def test_engine_sends_tcp_keepalives() -> None:
    with engine.connect() as connection:
        dsn_parameters = connection.connection.dbapi_connection.get_dsn_parameters()
    assert dsn_parameters["keepalives"] == "1"
    assert dsn_parameters["keepalives_idle"] == "30"

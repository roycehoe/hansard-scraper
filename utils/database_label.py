from sqlalchemy.engine import make_url


def get_database_label(database_url: str) -> str:
    url = make_url(database_url)
    return f"{url.host}:{url.port}/{url.database}"

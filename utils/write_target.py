from sqlalchemy.engine import make_url

from exceptions import HansardWriteTargetError

_PROTECTED_DATABASES = frozenset({"hansard_w3", "hansard_w4"})
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_PROTECTED_LOCAL_PORT = 5432


def validate_can_write(database_url: str) -> None:
    url = make_url(database_url)
    if url.database in _PROTECTED_DATABASES:
        raise HansardWriteTargetError(f"Refusing to write: database {url.database} is the loop's own copy")
    if (url.host is None or url.host in _LOCAL_HOSTS) and (url.port or _PROTECTED_LOCAL_PORT) == _PROTECTED_LOCAL_PORT:
        raise HansardWriteTargetError(f"Refusing to write: local port {_PROTECTED_LOCAL_PORT} belongs to another project")

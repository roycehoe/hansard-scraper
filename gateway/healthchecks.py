import requests

from exceptions import HansardGatewayError

_HEALTHCHECKS_TIMEOUT_SECONDS = 10
_FAILURE_PATH = "/fail"


def send_healthchecks_ping(ping_url: str) -> None:
    try:
        response = requests.get(url=ping_url, timeout=_HEALTHCHECKS_TIMEOUT_SECONDS)
        response.raise_for_status()
    # NOTE: from None, because the request error's text holds the ping URL and so the check's key
    except requests.exceptions.RequestException:
        raise HansardGatewayError("healthchecks.io ping failed") from None


def send_healthchecks_failure_ping(ping_url: str) -> None:
    try:
        response = requests.get(url=f"{ping_url.rstrip('/')}{_FAILURE_PATH}", timeout=_HEALTHCHECKS_TIMEOUT_SECONDS)
        response.raise_for_status()
    # NOTE: from None, because the request error's text holds the ping URL and so the check's key
    except requests.exceptions.RequestException:
        raise HansardGatewayError("healthchecks.io failure ping failed") from None

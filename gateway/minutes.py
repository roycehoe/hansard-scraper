from functools import partial

import requests

from exceptions import HansardGatewayError
from gateway.http import CRAWL_HEADERS, send_with_retry
from schemas.minutes_response import MinutesResponse
from settings import settings

REQUEST_TIMEOUT_SECONDS = 120


def _get_minutes_response(url: str) -> MinutesResponse:
    try:
        response = send_with_retry(
            partial(
                requests.get,
                url=url,
                headers=CRAWL_HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        )
        return MinutesResponse(
            url=url, status_code=response.status_code, content=response.content
        )
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError(f"Minutes request failed for {url}") from error


def get_minutes_index_response() -> MinutesResponse:
    return _get_minutes_response(settings.minutes_index_url)


def get_minutes_file_response(file_url: str) -> MinutesResponse:
    return _get_minutes_response(file_url)

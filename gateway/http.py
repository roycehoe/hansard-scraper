import asyncio
import random
from typing import Optional

import httpx

_MAX_RETRIES = 4
_BASE_DELAY = 2.0
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_BAD_REQUEST = 400
_HTTP_SERVER_ERROR_FLOOR = 500
_TRANSIENT_BAD_REQUEST_TEXT = "System error occured"


def _is_transient_failure(response: httpx.Response) -> bool:
    if response.status_code == _HTTP_TOO_MANY_REQUESTS:
        return True
    if response.status_code >= _HTTP_SERVER_ERROR_FLOOR:
        return True
    return response.status_code == _HTTP_BAD_REQUEST and _TRANSIENT_BAD_REQUEST_TEXT in response.text


async def async_post_with_retry(client: httpx.AsyncClient, url: str, json: Optional[dict] = None) -> httpx.Response:
    for attempt in range(_MAX_RETRIES + 1):
        response = await client.post(url, json=json)
        if not _is_transient_failure(response):
            return response
        if attempt == _MAX_RETRIES:
            response.raise_for_status()
        delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
        await asyncio.sleep(delay)

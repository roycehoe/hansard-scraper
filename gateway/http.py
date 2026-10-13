import asyncio
import random
from typing import Optional

import httpx

_MAX_RETRIES = 3
_BASE_DELAY = 1.0
_HTTP_TOO_MANY_REQUESTS = 429


async def async_post_with_retry(client: httpx.AsyncClient, url: str, json: Optional[dict] = None) -> httpx.Response:
    for attempt in range(_MAX_RETRIES + 1):
        response = await client.post(url, json=json)
        if response.status_code != _HTTP_TOO_MANY_REQUESTS:
            return response
        if attempt == _MAX_RETRIES:
            response.raise_for_status()
        delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
        await asyncio.sleep(delay)

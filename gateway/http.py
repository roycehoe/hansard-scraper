import asyncio
import random

import httpx

_MAX_RETRIES = 3
_BASE_DELAY = 1.0


async def async_post_with_retry(client: httpx.AsyncClient, url: str) -> httpx.Response:
    for attempt in range(_MAX_RETRIES + 1):
        response = await client.post(url)
        if response.status_code != 429:
            return response
        if attempt == _MAX_RETRIES:
            response.raise_for_status()
        delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
        await asyncio.sleep(delay)

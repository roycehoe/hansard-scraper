import asyncio
import random
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Optional, Union

import httpx
import requests

from settings import settings

CRAWL_USER_AGENT = "hansard-scraper (+royceinbox@hotmail.com)"
CRAWL_HEADERS = {"User-Agent": CRAWL_USER_AGENT}

MAX_RETRIES = 4
_BASE_DELAY = 2.0
_BACKOFF_BASE = 2
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_BAD_REQUEST = 400
_HTTP_SERVER_ERROR_FLOOR = 500
_TRANSIENT_BAD_REQUEST_TEXT = "System error occured"
NO_RESULTS_TEXT = "No Results Found"


# NOTE: the sync and async locks are separate because no code path sends sync and async Parliament requests at once
class CrawlPacer:
    def __init__(
        self,
        clock: Callable[[], float],
        sleep: Callable[[float], None],
        async_sleep: Callable[[float], Awaitable[None]],
    ):
        self.clock = clock
        self.sleep = sleep
        self.async_sleep = async_sleep
        self.sync_lock = threading.Lock()
        self.async_lock = asyncio.Lock()
        self.async_lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self.last_request_ended_at: Optional[float] = None

    def get_wait_seconds(self) -> float:
        if self.last_request_ended_at is None:
            return 0.0
        return max(0.0, settings.crawl_gap_seconds - (self.clock() - self.last_request_ended_at))

    # NOTE: each asyncio.run starts a new loop, and an asyncio.Lock cannot be shared across loops
    def get_async_lock(self) -> asyncio.Lock:
        running_loop = asyncio.get_running_loop()
        if self.async_lock_loop is not running_loop:
            self.async_lock = asyncio.Lock()
            self.async_lock_loop = running_loop
        return self.async_lock

    def record_request_end(self) -> None:
        self.last_request_ended_at = self.clock()


CRAWL_PACER = CrawlPacer(time.monotonic, time.sleep, asyncio.sleep)


@contextmanager
def paced_request() -> Iterator[None]:
    with CRAWL_PACER.sync_lock:
        CRAWL_PACER.sleep(CRAWL_PACER.get_wait_seconds())
        try:
            yield
        finally:
            CRAWL_PACER.record_request_end()


@asynccontextmanager
async def paced_request_async() -> AsyncIterator[None]:
    async with CRAWL_PACER.get_async_lock():
        await CRAWL_PACER.async_sleep(CRAWL_PACER.get_wait_seconds())
        try:
            yield
        finally:
            CRAWL_PACER.record_request_end()


def _is_transient_failure(response: Union[httpx.Response, requests.Response]) -> bool:
    if response.status_code == _HTTP_TOO_MANY_REQUESTS:
        return True
    if response.status_code >= _HTTP_SERVER_ERROR_FLOOR:
        return NO_RESULTS_TEXT not in response.text
    return response.status_code == _HTTP_BAD_REQUEST and _TRANSIENT_BAD_REQUEST_TEXT in response.text


def _get_backoff_seconds(attempt: int) -> float:
    return _BASE_DELAY * (_BACKOFF_BASE ** attempt) + random.uniform(0, 1)


async def async_post_with_retry(client: httpx.AsyncClient, url: str, json: Optional[dict] = None) -> httpx.Response:
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with paced_request_async():
                response = await client.post(url, json=json, headers=CRAWL_HEADERS)
        except httpx.TransportError:
            if attempt == MAX_RETRIES:
                raise
            await CRAWL_PACER.async_sleep(_get_backoff_seconds(attempt))
            continue
        if not _is_transient_failure(response):
            return response
        if attempt == MAX_RETRIES:
            response.raise_for_status()
        await CRAWL_PACER.async_sleep(_get_backoff_seconds(attempt))


def send_with_retry(send_request: Callable[[], requests.Response]) -> requests.Response:
    for attempt in range(MAX_RETRIES + 1):
        try:
            with paced_request():
                response = send_request()
        except requests.exceptions.ConnectionError:
            if attempt == MAX_RETRIES:
                raise
            CRAWL_PACER.sleep(_get_backoff_seconds(attempt))
            continue
        except requests.exceptions.Timeout:
            if attempt == MAX_RETRIES:
                raise
            CRAWL_PACER.sleep(_get_backoff_seconds(attempt))
            continue
        if not _is_transient_failure(response):
            return response
        if attempt == MAX_RETRIES:
            response.raise_for_status()
        CRAWL_PACER.sleep(_get_backoff_seconds(attempt))

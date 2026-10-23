import time
from datetime import date
from functools import partial
from typing import Optional

import requests

from exceptions import HansardGatewayError, HansardSearchRangeError
from gateway.http import CRAWL_HEADERS, NO_RESULTS_TEXT, send_with_retry
from logs import logger
from schemas.hansard_search_result import HansardSearchResult
from settings import settings
from utils.sitting_dates import get_month_windows

_MAX_RETRIES = 3
_BASE_DELAY = 1.0
_BACKOFF_BASE = 2
_MAX_PASSES = 25
_HTTP_BAD_REQUEST = 400
_HTTP_INTERNAL_SERVER_ERROR = 500
_REQUEST_TIMEOUT_SECONDS = 60


def get_hansard_search_results(
    start_index: int,
    end_index: int,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[HansardSearchResult]:
    from_date = settings.search_from_date if from_date is None else from_date
    to_date = settings.search_to_date if to_date is None else to_date
    query_dict = {
        "keyword": "undefined",
        "fromday": f"{from_date.day:02d}",
        "frommonth": f"{from_date.month:02d}",
        "fromyear": str(from_date.year),
        "today": f"{to_date.day:02d}",
        "tomonth": f"{to_date.month:02d}",
        "toyear": str(to_date.year),
        "dateRange": "custom",
        "reportContent": "with all the words",
        "parliamentNo": "",
        "selectedSort": "date_dt desc",
        "portfolio": [],
        "mpName": "",
        "rsSelected": "",
        "lang": "",
        "startIndex": f"{start_index}",
        "endIndex": f"{end_index}",
        "titleChecked": "false",
        "footNoteChecked": "false",
        "ministrySelected": [],
    }
    page = start_index // settings.search_page_size + 1
    try:
        response = send_with_retry(
            partial(
                requests.post,
                url=settings.hansard_search_url,
                json=query_dict,
                headers=CRAWL_HEADERS,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        )
        if (
            response.status_code == _HTTP_BAD_REQUEST or response.status_code == _HTTP_INTERNAL_SERVER_ERROR
        ) and NO_RESULTS_TEXT in response.text:
            return []
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, list):
            return []
        return [HansardSearchResult(**hit) for hit in body]
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError(f"Search request failed for page {page}") from error
    except ValueError as error:
        raise HansardGatewayError(f"Search request failed for page {page}") from error
    except TypeError as error:
        raise HansardGatewayError(f"Search request failed for page {page}") from error


def _get_page_with_retries(start_index: int, from_date: date, to_date: date) -> list[HansardSearchResult]:
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return get_hansard_search_results(start_index, start_index + settings.search_page_size - 1, from_date, to_date)
        except HansardGatewayError as error:
            if attempt == _MAX_RETRIES:
                raise
            logger.warning(f"{from_date:%Y-%m} start {start_index}: {error}, retry {attempt + 1}/{_MAX_RETRIES}")
            time.sleep(_BASE_DELAY * (_BACKOFF_BASE ** attempt))


def get_window_hansard_search_results(from_date: date, to_date: date) -> list[HansardSearchResult]:
    # NOTE: hits with equal sort keys come back in a different order on each request, so one pass can repeat
    # some hits and skip others. Pages are re-requested until the distinct report ids reach the engine total.
    first_page = _get_page_with_retries(0, from_date, to_date)
    if not first_page:
        return []
    try:
        total = int(first_page[0].max_result)
    except TypeError as error:
        raise HansardGatewayError(f"Search window {from_date} to {to_date} reports no total") from error
    except ValueError as error:
        raise HansardGatewayError(f"Search window {from_date} to {to_date} reports a total that is not a number") from error
    report_id_to_hit = {hit.report_id: hit for hit in first_page}
    for _ in range(_MAX_PASSES):
        for start_index in range(0, total, settings.search_page_size):
            page = _get_page_with_retries(start_index, from_date, to_date)
            for hit in page:
                report_id_to_hit.setdefault(hit.report_id, hit)
        if len(report_id_to_hit) >= total:
            break
    if len(report_id_to_hit) < total:
        logger.warning(
            f"Window {from_date} to {to_date}: engine total {total}, "
            f"fetched {len(report_id_to_hit)} distinct, short by {total - len(report_id_to_hit)}"
        )
    return list(report_id_to_hit.values())


def get_all_hansard_search_results(from_date: date, to_date: date) -> list[HansardSearchResult]:
    if from_date > to_date:
        raise HansardSearchRangeError(f"Search range {from_date} to {to_date} starts after it ends")
    all_hansard_search_results = []
    for month_window in get_month_windows(from_date, to_date):
        window_hansard_search_results = get_window_hansard_search_results(month_window.first_date, month_window.last_date)
        all_hansard_search_results.extend(window_hansard_search_results)
        logger.info(f"Fetched {month_window.first_date:%Y-%m}: {len(window_hansard_search_results)} distinct hits")
    logger.info(f"Search done: {len(all_hansard_search_results)} distinct hits")
    return all_hansard_search_results

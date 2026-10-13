import calendar
import time
from datetime import date

import requests

from exceptions import HansardGatewayError
from logs import logger
from settings import settings

_MAX_RETRIES = 3
_BASE_DELAY = 1.0
_MAX_PASSES = 25


def get_hansard_search_results(
    start_index: int,
    end_index: int,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict | list:
    from_date = from_date or settings.search_from_date
    to_date = to_date or settings.search_to_date
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
    page = start_index // 20 + 1
    try:
        response = requests.post(url=settings.hansard_search_url, json=query_dict)
        if response.status_code in (400, 500) and "No Results Found" in response.text:
            return {"errorCode": 0, "description": "No Results Found"}
        response.raise_for_status()
        return response.json()
    except (requests.exceptions.RequestException, ValueError) as error:
        raise HansardGatewayError(f"Search request failed for page {page}") from error


def _get_page_with_retries(start_index: int, from_date: date, to_date: date):
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return get_hansard_search_results(start_index, start_index + 19, from_date, to_date)
        except HansardGatewayError as error:
            if attempt == _MAX_RETRIES:
                raise
            logger.warning(f"{from_date:%Y-%m} start {start_index}: {error}, retry {attempt + 1}/{_MAX_RETRIES}")
            time.sleep(_BASE_DELAY * (2 ** attempt))


def _months(first: date, last: date):
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        yield (
            max(first, date(year, month, 1)),
            min(last, date(year, month, calendar.monthrange(year, month)[1])),
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def get_window_hansard_search_results(from_date: date, to_date: date) -> list[dict]:
    """Hits with equal sort keys come back in a different order on each request, so one
    pass over the pages can repeat some hits and skip others. Re-request the pages until
    the distinct report ids reach the engine total, then give up with a warning."""
    first_page = _get_page_with_retries(0, from_date, to_date)
    if not isinstance(first_page, list) or not first_page:
        return []
    total = int(first_page[0]["maxResult"])
    hit_by_report_id = {hit["reportId"]: hit for hit in first_page}
    for _ in range(_MAX_PASSES):
        for start_index in range(0, total, 20):
            page = _get_page_with_retries(start_index, from_date, to_date)
            if isinstance(page, list):
                for hit in page:
                    hit_by_report_id.setdefault(hit["reportId"], hit)
        if len(hit_by_report_id) >= total:
            break
    if len(hit_by_report_id) < total:
        logger.warning(
            f"Window {from_date} to {to_date}: engine total {total}, "
            f"fetched {len(hit_by_report_id)} distinct, short by {total - len(hit_by_report_id)}"
        )
    return list(hit_by_report_id.values())


def get_all_hansard_search_results() -> list[dict]:
    all_hansard_search_results = []
    for from_date, to_date in _months(settings.search_from_date, settings.search_to_date):
        window_results = get_window_hansard_search_results(from_date, to_date)
        all_hansard_search_results.extend(window_results)
        logger.info(f"Fetched {from_date:%Y-%m}: {len(window_results)} distinct hits")
    logger.info(f"Search done: {len(all_hansard_search_results)} distinct hits")
    return all_hansard_search_results

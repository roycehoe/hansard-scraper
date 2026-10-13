import time

import requests

from exceptions import HansardGatewayError
from logs import logger
from settings import settings

_MAX_RETRIES = 3
_BASE_DELAY = 1.0


def get_hansard_search_results(start_index: int, end_index: int) -> dict:
    query_dict = {
        "keyword": "undefined",
        "fromday": f"{settings.search_from_date.day:02d}",
        "frommonth": f"{settings.search_from_date.month:02d}",
        "fromyear": str(settings.search_from_date.year),
        "today": f"{settings.search_to_date.day:02d}",
        "tomonth": f"{settings.search_to_date.month:02d}",
        "toyear": str(settings.search_to_date.year),
        "dateRange": "* TO NOW",
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
    try:
        response = requests.post(url=settings.hansard_search_url, json=query_dict)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HansardGatewayError(f"Search request failed for page {start_index // 20 + 1}") from e
    except ValueError as e:
        raise HansardGatewayError(f"Search request failed for page {start_index // 20 + 1}") from e


def _get_page_with_retries(start_index: int, end_index: int, seen_ids: set[str]):
    page = start_index // 20 + 1
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = get_hansard_search_results(start_index, end_index)
            if not isinstance(response, list):
                return response
            repeated = sum(1 for hit in response if hit.get("reportId") in seen_ids)
            if repeated == 0:
                return response
            problem = f"{repeated} reportIds already seen on earlier pages"
        except HansardGatewayError as e:
            problem = str(e)
        if attempt == _MAX_RETRIES:
            raise HansardGatewayError(
                f"Page {page} still bad after {_MAX_RETRIES} retries: {problem}"
            )
        logger.warning(f"Page {page}: {problem}, retry {attempt + 1}/{_MAX_RETRIES}")
        time.sleep(_BASE_DELAY * (2 ** attempt))


def get_all_hansard_search_results() -> list[dict]:
    all_hansard_search_results = []
    seen_ids: set[str] = set()
    start_index = 0
    end_index = 19

    while True:
        response = _get_page_with_retries(start_index, end_index, seen_ids)
        if not isinstance(response, list) or not response:
            break
        all_hansard_search_results.extend(response)
        seen_ids.update(hit["reportId"] for hit in response if "reportId" in hit)
        start_index += 20
        end_index += 20
        logger.info(f"Fetched page {start_index // 20}")

    max_result = (
        all_hansard_search_results[0].get("maxResult")
        if all_hansard_search_results
        else None
    )
    if isinstance(max_result, str) and max_result.isdigit() and int(max_result) != len(seen_ids):
        raise HansardGatewayError(
            f"Search reported {max_result} results but {len(seen_ids)} distinct reportIds were collected"
        )
    logger.info(
        f"Search done: {start_index // 20} pages, "
        f"{len(all_hansard_search_results)} hits, {len(seen_ids)} distinct ids"
    )
    return all_hansard_search_results

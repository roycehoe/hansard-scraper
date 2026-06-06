import requests

from exceptions import HansardGatewayError
from logs import logger
from settings import settings


def get_handsard_search_results(start_index: int, end_index: int) -> dict:
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
        response = requests.post(url=settings.handsard_search_url, json=query_dict)
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HansardGatewayError(f"Search request failed for page {start_index // 20 + 1}") from e
    except ValueError as e:
        raise HansardGatewayError(f"Search request failed for page {start_index // 20 + 1}") from e


def get_all_handsard_search_results() -> list[dict]:
    all_handsard_search_results = []
    start_index = 0
    end_index = 19

    while True:
        try:
            response = get_handsard_search_results(start_index, end_index)
        except HansardGatewayError as e:
            logger.error(f"Failed to fetch page {start_index // 20 + 1}: {e}, skipping")
            start_index += 20
            end_index += 20
            continue
        if not isinstance(response, list):
            break
        all_handsard_search_results.extend(response)
        start_index += 20
        end_index += 20
        logger.info(f"Fetched page {start_index // 20}")

    return all_handsard_search_results

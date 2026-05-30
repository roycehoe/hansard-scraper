import requests

from logs import logger
from settings import settings


def get_handsard_search_results(start_index: int, end_index: int) -> dict:
    query_dict = {
        "keyword": "undefined",
        "fromday": settings.search_from_day,
        "frommonth": settings.search_from_month,
        "fromyear": settings.search_from_year,
        "today": settings.search_to_day,
        "tomonth": settings.search_to_month,
        "toyear": settings.search_to_year,
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
    response = requests.post(url=settings.handsard_search_url, json=query_dict)
    return response.json()


def get_all_handsard_search_results() -> list[dict]:
    all_handsard_search_results = []
    start_index = 0
    end_index = 19

    while True:
        try:
            response = get_handsard_search_results(start_index, end_index)
        except Exception as e:
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

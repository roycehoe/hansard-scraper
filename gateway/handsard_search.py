import requests

HANDSARD_SEARCH_URL = "https://sprs.parl.gov.sg/search/searchResult"


def get_handsard_search_results(
    start_index: int, end_index: int, url: str = HANDSARD_SEARCH_URL
) -> dict:
    query_dict = {
        "keyword": "undefined",
        "fromday": "24",
        "frommonth": "08",
        "fromyear": "2025",
        "today": "24",
        "tomonth": "08",
        "toyear": "2025",
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
    response = requests.post(
        url=url,
        json=query_dict,
    )
    return response.json()


def _has_results(handsard_search_results: dict | list) -> bool:
    if isinstance(handsard_search_results, list):
        return True
    return False


def get_all_handsard_search_results() -> list[dict]:
    all_handsard_search_results = []
    start_index = 0
    end_index = 19
    counter = 0

    while True:
        response = get_handsard_search_results(start_index, end_index)
        if not _has_results(response):
            break
        all_handsard_search_results = [
            *all_handsard_search_results,
            *response,
        ]
        start_index += 20
        end_index += 20
        counter += 1
        print(f"Handsard search results: {counter}/{41837 / 20}")

    return all_handsard_search_results

import json

import requests

PARLIAMENT_DEBATES_SEARCH_URL = "https://sprs.parl.gov.sg/search/searchResult"


def get_parliament_debates_search_results(
    start_index: int, end_index: int, url: str = PARLIAMENT_DEBATES_SEARCH_URL
):
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


def _has_results(parliament_debates_search_results: dict | list) -> bool:
    if isinstance(parliament_debates_search_results, list):
        return True
    return False


def get_all_parliament_debates_search_results():
    all_parliament_debates_search_results = []
    start_index = 0
    end_index = 19
    counter = 0

    while True:
        response = get_parliament_debates_search_results(start_index, end_index)
        print(response)
        if not _has_results(response):
            break
        all_parliament_debates_search_results = [
            *all_parliament_debates_search_results,
            *response,
        ]
        start_index += 20
        end_index += 20
        counter += 1
        print(f"{counter}/{41837/20}")

    return all_parliament_debates_search_results


parliament_debates_search_results = get_all_parliament_debates_search_results()
with open("parliament_data.json", "w") as data:
    json.dump(parliament_debates_search_results, data)

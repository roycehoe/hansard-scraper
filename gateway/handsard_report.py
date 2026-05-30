from typing import Optional

import requests

HANDSARD_REPORT_URL = "https://sprs.parl.gov.sg/search/getHansardReport/"


def get_handsard_report_response(sitting_date: str) -> Optional[dict]:
    try:
        response = requests.post(url=f"{HANDSARD_REPORT_URL}?sittingDate={sitting_date}")
        return response.json()
    except Exception as e:
        print(f"Failed to fetch sitting date {sitting_date}: {e}, skipping")
        return None

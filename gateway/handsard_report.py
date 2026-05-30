from typing import Optional

import requests

from settings import settings


def get_handsard_report_response(sitting_date: str) -> Optional[dict]:
    try:
        response = requests.post(url=f"{settings.handsard_report_url}?sittingDate={sitting_date}")
        return response.json()
    except Exception as e:
        print(f"Failed to fetch sitting date {sitting_date}: {e}, skipping")
        return None

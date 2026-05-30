import requests

HANDSARD_REPORT_URL = "https://sprs.parl.gov.sg/search/getHansardReport/"


def get_handsard_report_response(sitting_date: str) -> dict:
    response = requests.post(url=f"{HANDSARD_REPORT_URL}?sittingDate={sitting_date}")
    return response.json()

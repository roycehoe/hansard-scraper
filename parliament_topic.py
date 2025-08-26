import requests

HANDSARD_TOPIC_URL = "https://sprs.parl.gov.sg/search/getHansardTopic"


def get_handsard_topic_response(report_id: str) -> dict:
    response = requests.post(url=f"{HANDSARD_TOPIC_URL}/?id={report_id}")
    return response.json()

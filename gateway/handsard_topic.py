import requests

from settings import settings


def get_handsard_topic_response(report_id: str) -> dict:
    response = requests.post(url=f"{settings.handsard_topic_url}/?id={report_id}")
    return response.json()

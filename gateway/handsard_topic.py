import requests

from exceptions import HansardGatewayError
from settings import settings


def get_handsard_topic_response(report_id: str) -> dict:
    try:
        response = requests.post(url=f"{settings.handsard_topic_url}/?id={report_id}")
        return response.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from e

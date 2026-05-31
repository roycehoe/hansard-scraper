import httpx
import requests

from exceptions import HansardGatewayError
from settings import settings


def get_handsard_report_response(sitting_date: str) -> dict:
    try:
        response = requests.post(url=f"{settings.handsard_report_url}?sittingDate={sitting_date}")
        return response.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from e


async def get_handsard_report_response_async(sitting_date: str, client: httpx.AsyncClient) -> dict:
    try:
        response = await client.post(url=f"{settings.handsard_report_url}?sittingDate={sitting_date}")
        return response.json()
    except (httpx.RequestError, ValueError) as e:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from e

import httpx
import requests

from exceptions import HansardGatewayError
from gateway.http import async_post_with_retry
from settings import settings


def get_hansard_report_response(sitting_date: str) -> dict:
    try:
        response = requests.post(url=f"{settings.hansard_report_url}?sittingDate={sitting_date}")
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from e
    except ValueError as e:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from e


async def get_hansard_report_response_async(sitting_date: str, client: httpx.AsyncClient) -> dict:
    try:
        response = await async_post_with_retry(client, f"{settings.hansard_report_url}?sittingDate={sitting_date}")
        return response.json()
    except httpx.RequestError as e:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from e
    except ValueError as e:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from e

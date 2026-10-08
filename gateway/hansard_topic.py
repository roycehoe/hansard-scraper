import httpx
import requests

from exceptions import HansardGatewayError
from gateway.http import async_post_with_retry
from settings import settings


def get_hansard_topic_response(report_id: str) -> dict:
    try:
        response = requests.post(url=f"{settings.hansard_topic_url}/?id={report_id}")
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from e
    except ValueError as e:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from e


async def get_hansard_topic_response_async(report_id: str, client: httpx.AsyncClient) -> dict:
    try:
        response = await async_post_with_retry(client, f"{settings.hansard_topic_url}/?id={report_id}")
        return response.json()
    except httpx.RequestError as e:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from e
    except ValueError as e:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from e

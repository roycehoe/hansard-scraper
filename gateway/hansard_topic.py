import httpx
import requests

from exceptions import HansardGatewayError
from gateway.http import CRAWL_HEADERS, async_post_with_retry, paced_request
from schemas.hansard_topic_response import HansardTopicResponse
from settings import settings


def get_hansard_topic_response(report_id: str) -> HansardTopicResponse:
    try:
        with paced_request():
            response = requests.post(url=settings.hansard_topic_url, json={"id": report_id}, headers=CRAWL_HEADERS)
        return HansardTopicResponse(**response.json())
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from error
    except ValueError as error:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from error


async def get_hansard_topic_response_async(report_id: str, client: httpx.AsyncClient) -> HansardTopicResponse:
    try:
        response = await async_post_with_retry(client, settings.hansard_topic_url, {"id": report_id})
        return HansardTopicResponse(**response.json())
    except httpx.RequestError as error:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from error
    except httpx.HTTPStatusError as error:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from error
    except ValueError as error:
        raise HansardGatewayError(f"Topic request failed for {report_id}") from error

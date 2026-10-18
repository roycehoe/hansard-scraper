from typing import Union

import httpx
import requests

from exceptions import HansardGatewayError
from gateway.http import CRAWL_HEADERS, async_post_with_retry, paced_request
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from settings import settings
from utils.sitting_dates import get_zero_padded_sitting_date
from utils.text import strip_nul

_NEW_FORMAT_KEY = "metadata"


def _build_hansard_report_response(body: object) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
    body = strip_nul(body)
    if isinstance(body, dict) and _NEW_FORMAT_KEY in body:
        return HansardReportNewResponse(**body)
    return HansardReportOldResponse(**body)


def get_hansard_report_response(sitting_date: str) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
    request_body = {"sittingDate": get_zero_padded_sitting_date(sitting_date)}
    try:
        with paced_request():
            response = requests.post(url=settings.hansard_report_url, json=request_body, headers=CRAWL_HEADERS)
        return _build_hansard_report_response(response.json())
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from error
    except ValueError as error:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from error


async def get_hansard_report_response_async(
    sitting_date: str, client: httpx.AsyncClient
) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
    request_body = {"sittingDate": get_zero_padded_sitting_date(sitting_date)}
    try:
        response = await async_post_with_retry(client, settings.hansard_report_url, request_body)
        return _build_hansard_report_response(response.json())
    except httpx.RequestError as error:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from error
    except httpx.HTTPStatusError as error:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from error
    except ValueError as error:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from error

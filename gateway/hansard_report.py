from typing import Union

import httpx
import requests

from exceptions import HansardGatewayError
from gateway.http import async_post_with_retry
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from settings import settings
from utils.sitting_dates import is_new_sitting_date_format
from utils.text import strip_nul


def get_hansard_report_response(sitting_date: str) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
    response_schema = HansardReportNewResponse if is_new_sitting_date_format(sitting_date) else HansardReportOldResponse
    try:
        response = requests.post(url=f"{settings.hansard_report_url}?sittingDate={sitting_date}")
        return response_schema(**strip_nul(response.json()))
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from error
    except ValueError as error:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from error


async def get_hansard_report_response_async(
    sitting_date: str, client: httpx.AsyncClient
) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
    response_schema = HansardReportNewResponse if is_new_sitting_date_format(sitting_date) else HansardReportOldResponse
    try:
        response = await async_post_with_retry(client, f"{settings.hansard_report_url}?sittingDate={sitting_date}")
        return response_schema(**strip_nul(response.json()))
    except httpx.RequestError as error:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from error
    except ValueError as error:
        raise HansardGatewayError(f"Report request failed for {sitting_date}") from error

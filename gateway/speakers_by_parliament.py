import json
import re
from functools import partial

import requests

from exceptions import HansardGatewayError
from gateway.http import CRAWL_HEADERS, send_with_retry
from schemas.parliament_member_list_response import ParliamentMemberListResponse
from settings import settings

_SPEAKERS_TIMEOUT_SECONDS = 15
_FLIGHT_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_MEMBER_LIST_MARKER = '{"mps":'


def get_parliament_member_list_response() -> ParliamentMemberListResponse:
    try:
        response = send_with_retry(
            partial(
                requests.get,
                url=settings.parliament_speakers_url,
                headers=CRAWL_HEADERS,
                timeout=_SPEAKERS_TIMEOUT_SECONDS,
            )
        )
        response.raise_for_status()
        flight_data = "".join(json.loads(chunk) for chunk in _FLIGHT_CHUNK_RE.findall(response.text))
        member_list, _ = json.JSONDecoder().raw_decode(flight_data, flight_data.index(_MEMBER_LIST_MARKER))
        parliament_member_list_response = ParliamentMemberListResponse.model_validate(member_list)
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError("Member list request failed") from error
    except ValueError as error:
        raise HansardGatewayError("Member list page holds no readable member data") from error
    member_count = len(parliament_member_list_response.mps.data)
    if member_count != parliament_member_list_response.mps.meta.filter_count:
        raise HansardGatewayError(
            f"Member list holds {member_count} of {parliament_member_list_response.mps.meta.filter_count} members"
        )
    return parliament_member_list_response

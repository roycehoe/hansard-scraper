from urllib.parse import quote

import requests

from exceptions import HansardGatewayError
from gateway.http import CRAWL_HEADERS, paced_request
from schemas.sprs_file_response import SprsFileResponse

_SPRS_DOWNLOAD_URL = "https://sprs.parl.gov.sg/search/search/download?value="
_FIRST_KILOBYTE_RANGE = "bytes=0-1023"
_FIRST_CHUNK_BYTES = 1_024
_PATH_SAFE_CHARACTERS = "/"
REQUEST_TIMEOUT_SECONDS = 120


def get_sprs_file_response(download_value: str) -> SprsFileResponse:
    url = f"{_SPRS_DOWNLOAD_URL}{quote(download_value, safe=_PATH_SAFE_CHARACTERS)}"
    try:
        with (
            paced_request(),
            requests.get(
                url=url,
                headers={**CRAWL_HEADERS, "Range": _FIRST_KILOBYTE_RANGE},
                timeout=REQUEST_TIMEOUT_SECONDS,
                stream=True,
            ) as response,
        ):
            first_chunk = next(
                response.iter_content(chunk_size=_FIRST_CHUNK_BYTES), b""
            )
            return SprsFileResponse(
                url=url,
                status_code=response.status_code,
                content_type=response.headers.get("content-type"),
                content_disposition=response.headers.get("content-disposition"),
                is_body_empty=first_chunk == b"",
            )
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError(f"SPRS file request failed for {url}") from error

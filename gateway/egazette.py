from functools import partial

import requests

from enums import EgazetteSupplementKind
from exceptions import HansardGatewayError
from gateway.http import CRAWL_HEADERS, send_with_retry
from schemas.egazette_supplement_response import EgazetteSupplementResponse
from settings import settings

REQUEST_TIMEOUT_SECONDS = 120
_SUPPLEMENTS_PATH = "Legislative%20Supplements"
_SUPPLEMENT_KIND_TO_PATH = {
    EgazetteSupplementKind.BILLS: "Bills%20Supplement",
    EgazetteSupplementKind.ACTS: "Acts%20Supplement",
}
_FILE_NUMBER_WIDTH = 2


def get_egazette_supplement_url(
    year: int, supplement_kind: EgazetteSupplementKind, number: int
) -> str:
    return (
        f"{settings.egazette_assets_url}/{year}/{_SUPPLEMENTS_PATH}/"
        f"{_SUPPLEMENT_KIND_TO_PATH[supplement_kind]}/{number:0{_FILE_NUMBER_WIDTH}d}.pdf"
    )


def get_egazette_supplement_response(
    year: int, supplement_kind: EgazetteSupplementKind, number: int
) -> EgazetteSupplementResponse:
    url = get_egazette_supplement_url(year, supplement_kind, number)
    try:
        response = send_with_retry(
            partial(
                requests.get,
                url=url,
                headers=CRAWL_HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        )
        return EgazetteSupplementResponse(
            url=url, status_code=response.status_code, content=response.content
        )
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError(f"eGazette request failed for {url}") from error

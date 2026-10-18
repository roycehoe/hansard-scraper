import re

import requests
from bs4 import BeautifulSoup

from exceptions import HansardGatewayError
from gateway.http import CRAWL_HEADERS, paced_request
from schemas.speaker import SpeakerResult
from settings import settings

_ANTIFORGERY_TIMEOUT_SECONDS = 10
_SPEAKERS_TIMEOUT_SECONDS = 15
_PARLIAMENT_NUMBER_TO_PAGE_ID = {
    1: 1, 2: 2, 3: 5, 4: 8, 5: 11, 6: 13, 7: 16,
    8: 20, 9: 23, 10: 26, 11: 29, 12: 32, 13: 35, 14: 38, 15: 41,
}


def _get_antiforgery_token(session: requests.Session) -> str:
    try:
        with paced_request():
            response = session.get(
                settings.parliament_anticsrf_url,
                headers={"X-SF-ANTIFORGERY-REQUEST": "true"},
                timeout=_ANTIFORGERY_TIMEOUT_SECONDS,
            )
        response.raise_for_status()
        return response.json()["Value"]
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError("Failed to fetch antiforgery token") from error
    except ValueError as error:
        raise HansardGatewayError("Failed to fetch antiforgery token") from error
    except KeyError as error:
        raise HansardGatewayError("Failed to fetch antiforgery token") from error


def _parse_speakers(html: str, parliament_number: int) -> list[SpeakerResult]:
    soup = BeautifulSoup(html, "html.parser")
    speaker_results = []
    for list_item in soup.select("ul.list > li"):
        name_element = list_item.select_one(".mp-sort-name.name")
        party_element = list_item.select_one(".mp-sort.party")
        legislative_assembly_element = list_item.select_one(".formermp-legislative")
        if name_element is None:
            continue
        if party_element is None:
            continue
        full_name = name_element.get_text(strip=True)
        match = re.match(r"^(.*?)\s*\((.+)\)\s*$", full_name)
        name = full_name if match is None else match.group(1).strip()
        comments = None if match is None else match.group(2).strip()
        speaker_results.append(SpeakerResult(
            name=name,
            party=party_element.get_text(strip=True),
            is_legislative_assembly=legislative_assembly_element is not None and legislative_assembly_element.get_text(strip=True) != "",
            parliament_number=parliament_number,
            comments=comments,
        ))
    return speaker_results


def get_all_speakers() -> list[SpeakerResult]:
    session = requests.Session()
    session.headers.update(CRAWL_HEADERS)
    try:
        with paced_request():
            session.get(settings.parliament_speakers_url, timeout=_SPEAKERS_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError("Failed to establish parliament session") from error

    antiforgery_token = _get_antiforgery_token(session)
    all_speakers = []
    for parliament_number, parliament_page_id in _PARLIAMENT_NUMBER_TO_PAGE_ID.items():
        try:
            with paced_request():
                response = session.post(
                    settings.parliament_speakers_url,
                    data={"Parliament": parliament_page_id, "sf_antiforgery": antiforgery_token},
                    headers={"X-SF-ANTIFORGERY-REQUEST": antiforgery_token},
                    timeout=_SPEAKERS_TIMEOUT_SECONDS,
                )
            response.raise_for_status()
        except requests.exceptions.RequestException as error:
            raise HansardGatewayError(f"Failed to fetch speakers for parliament {parliament_number}") from error
        all_speakers.extend(_parse_speakers(response.text, parliament_number))
    return all_speakers

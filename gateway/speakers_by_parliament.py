import re
import time

import requests
from bs4 import BeautifulSoup

from exceptions import HansardGatewayError
from schemas.speaker import SpeakerResult
from settings import settings

_PARLIAMENT_NUMBER_TO_PAGE_ID = {
    1: 1, 2: 2, 3: 5, 4: 8, 5: 11, 6: 13, 7: 16,
    8: 20, 9: 23, 10: 26, 11: 29, 12: 32, 13: 35, 14: 38, 15: 41,
}


def _get_antiforgery_token(session: requests.Session) -> str:
    try:
        response = session.get(
            settings.parliament_anticsrf_url,
            headers={"X-SF-ANTIFORGERY-REQUEST": "true"},
            timeout=10,
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
    results = []
    for list_item in soup.select("ul.list > li"):
        name_element = list_item.select_one(".mp-sort-name.name")
        party_element = list_item.select_one(".mp-sort.party")
        legislative_assembly_element = list_item.select_one(".formermp-legislative")
        if not name_element or not party_element:
            continue
        full_name = name_element.get_text(strip=True)
        match = re.match(r"^(.*?)\s*\((.+)\)\s*$", full_name)
        if match:
            name, comments = match.group(1).strip(), match.group(2).strip()
        else:
            name, comments = full_name, None
        results.append(SpeakerResult(
            name=name,
            party=party_element.get_text(strip=True),
            is_legislative_assembly=bool(legislative_assembly_element and legislative_assembly_element.get_text(strip=True)),
            parliament_number=parliament_number,
            comments=comments,
        ))
    return results


def get_all_speakers() -> list[SpeakerResult]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        session.get(settings.parliament_speakers_url, timeout=15)
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError("Failed to establish parliament session") from error

    token = _get_antiforgery_token(session)
    all_speakers = []
    for parliament_number, parliament_page_id in _PARLIAMENT_NUMBER_TO_PAGE_ID.items():
        try:
            response = session.post(
                settings.parliament_speakers_url,
                data={"Parliament": parliament_page_id, "sf_antiforgery": token},
                headers={"X-SF-ANTIFORGERY-REQUEST": token},
                timeout=15,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as error:
            raise HansardGatewayError(f"Failed to fetch speakers for parliament {parliament_number}") from error
        all_speakers.extend(_parse_speakers(response.text, parliament_number))
        time.sleep(0.5)
    return all_speakers

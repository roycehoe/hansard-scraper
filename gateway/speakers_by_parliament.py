import re
import time

import requests
from bs4 import BeautifulSoup

from exceptions import HansardGatewayError
from schemas.speaker import SpeakerResult
from settings import settings

PARLIAMENT_IDS = {
    1: 1, 2: 2, 3: 5, 4: 8, 5: 11, 6: 13, 7: 16,
    8: 20, 9: 23, 10: 26, 11: 29, 12: 32, 13: 35, 14: 38, 15: 41,
}


def _get_antiforgery_token(session: requests.Session) -> str:
    try:
        resp = session.get(
            settings.parliament_anticsrf_url,
            headers={"X-SF-ANTIFORGERY-REQUEST": "true"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["Value"]
    except requests.exceptions.RequestException as e:
        raise HansardGatewayError("Failed to fetch antiforgery token") from e
    except ValueError as e:
        raise HansardGatewayError("Failed to fetch antiforgery token") from e
    except KeyError as e:
        raise HansardGatewayError("Failed to fetch antiforgery token") from e


def _parse_speakers(html: str, parliament_number: int) -> list[SpeakerResult]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for li in soup.select("ul.list > li"):
        name_el = li.select_one(".mp-sort-name.name")
        party_el = li.select_one(".mp-sort.party")
        leg_assembly_el = li.select_one(".formermp-legislative")
        if not name_el or not party_el:
            continue
        full_name = name_el.get_text(strip=True)
        match = re.match(r"^(.*?)\s*\((.+)\)\s*$", full_name)
        if match:
            name, comments = match.group(1).strip(), match.group(2).strip()
        else:
            name, comments = full_name, None
        results.append(SpeakerResult(
            name=name,
            party=party_el.get_text(strip=True),
            is_legislative_assembly=bool(leg_assembly_el and leg_assembly_el.get_text(strip=True)),
            parliament_number=parliament_number,
            comments=comments,
        ))
    return results


def get_all_speakers() -> list[SpeakerResult]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        session.get(settings.parliament_speakers_url, timeout=15)
    except requests.exceptions.RequestException as e:
        raise HansardGatewayError("Failed to establish parliament session") from e

    token = _get_antiforgery_token(session)
    all_speakers = []
    for parl_num, parl_id in PARLIAMENT_IDS.items():
        try:
            resp = session.post(
                settings.parliament_speakers_url,
                data={"Parliament": parl_id, "sf_antiforgery": token},
                headers={"X-SF-ANTIFORGERY-REQUEST": token},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise HansardGatewayError(f"Failed to fetch speakers for parliament {parl_num}") from e
        all_speakers.extend(_parse_speakers(resp.text, parl_num))
        time.sleep(0.5)
    return all_speakers

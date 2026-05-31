import json
import re
import time

import requests
from bs4 import BeautifulSoup

URL = "https://www.parliament.gov.sg/history/list-of-mps-by-parliament"

# Internal Sitefinity IDs for each parliament number (1-15)
PARLIAMENT_IDS = {
    1: 1, 2: 2, 3: 5, 4: 8, 5: 11, 6: 13, 7: 16,
    8: 20, 9: 23, 10: 26, 11: 29, 12: 32, 13: 35, 14: 38, 15: 41,
}


def get_antiforgery_token(session: requests.Session) -> str:
    # Sitefinity requires X-SF-ANTIFORGERY-REQUEST: true to issue a token
    resp = session.get(
        "https://www.parliament.gov.sg/sitefinity/anticsrf",
        headers={"X-SF-ANTIFORGERY-REQUEST": "true"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["Value"]


def parse_mps(html: str, parliament_number: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for li in soup.select("ul.list > li"):
        name = li.select_one(".mp-sort-name.name")
        party = li.select_one(".mp-sort.party")
        leg_assembly = li.select_one(".formermp-legislative")
        if not name or not party:
            continue
        results.append({
            "name": name.get_text(strip=True),
            "party": party.get_text(strip=True),
            "is_legislative_assembly": bool(leg_assembly and leg_assembly.get_text(strip=True)),
            "parliament_number": parliament_number,
        })
    return results


def scrape() -> list[dict]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    print("Fetching page to establish session...")
    session.get(URL, timeout=15)
    token = get_antiforgery_token(session)
    print(f"CSRF token: {token[:12]}...")

    all_mps = []
    for parl_num, parl_id in PARLIAMENT_IDS.items():
        print(f"Fetching Parliament {parl_num} (id={parl_id})...")
        payload = {"Parliament": parl_id, "sf_antiforgery": token}
        headers = {"X-SF-ANTIFORGERY-REQUEST": token} if token else {}
        resp = session.post(URL, data=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        mps = parse_mps(resp.text, parl_num)
        print(f"  → {len(mps)} MPs")
        all_mps.extend(mps)
        time.sleep(0.5)

    return all_mps


if __name__ == "__main__":
    mps = scrape()
    out_path = "mps_by_parliament.json"
    with open(out_path, "w") as f:
        json.dump(mps, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(mps)} records to {out_path}")

import re
from datetime import date, datetime
from typing import Optional

from exceptions import HansardRepealedActsListingError
from schemas.repealed_acts_plan import PlannedRepealedActEntry
from utils.sso_listing import ActListingRow

_LINK_PATTERN = re.compile(
    r"/Act/([^/?]+)/Repealed/(\d{8})\?DocDate=(\d{8})(?:\d{6})?(?:\D|$)"
)
_ENACTMENT_YEAR_PATTERN = re.compile(r"(\d{4})$")
_DATE_FORMAT = "%Y%m%d"


def _match_link(link: str) -> re.Match[str]:
    match = _LINK_PATTERN.search(link)
    if match is None:
        raise HansardRepealedActsListingError(
            f"The link {link} is not '/Act/CODE/Repealed/YYYYMMDD?DocDate=YYYYMMDD'"
        )
    return match


def _read_date(digits: str, link: str) -> date:
    try:
        return datetime.strptime(digits, _DATE_FORMAT).date()
    except ValueError as error:
        raise HansardRepealedActsListingError(
            f"The link {link} holds an impossible date"
        ) from error


def get_sso_code(link: str) -> str:
    return _match_link(link).group(1)


def get_repeal_date(link: str) -> date:
    return _read_date(_match_link(link).group(2), link)


def get_last_version_date(link: str) -> date:
    return _read_date(_match_link(link).group(3), link)


def get_enactment_year(sso_code: str) -> Optional[int]:
    match = _ENACTMENT_YEAR_PATTERN.search(sso_code)
    if match is None:
        return None
    return int(match.group(1))


def build_planned_entry(
    act_listing_row: ActListingRow, capture_url: str
) -> PlannedRepealedActEntry:
    sso_code = get_sso_code(act_listing_row.link)
    return PlannedRepealedActEntry(
        printed_title=act_listing_row.printed_title,
        printed_chapter=act_listing_row.printed_chapter,
        link=act_listing_row.link,
        sso_code=sso_code,
        enactment_year=get_enactment_year(sso_code),
        repeal_date=get_repeal_date(act_listing_row.link),
        last_version_date=get_last_version_date(act_listing_row.link),
        capture_url=capture_url,
    )


def get_first_planned_entries(
    planned_entries: list[PlannedRepealedActEntry],
) -> list[PlannedRepealedActEntry]:
    sso_code_to_entry: dict[str, PlannedRepealedActEntry] = {}
    for planned_entry in planned_entries:
        sso_code_to_entry.setdefault(planned_entry.sso_code, planned_entry)
    return list(sso_code_to_entry.values())

import re
from datetime import date, datetime

from exceptions import HansardActsSupplementError
from schemas.acts_supplement_plan import PlannedActsSupplementEntry
from utils.sso_listing import ListingRow

_PRINTED_NUMBER_PATTERN = re.compile(r"Act (\d+) of (\d{4})")
_PUBLICATION_DATE_PATTERN = re.compile(r"[?&]DocDate=(\d{8})(?:\d{6})?(?:\D|$)")
_PUBLICATION_DATE_FORMAT = "%Y%m%d"


def get_act_number(printed_number: str) -> str:
    match = _PRINTED_NUMBER_PATTERN.fullmatch(printed_number)
    if match is None:
        raise HansardActsSupplementError(
            f"The printed number {printed_number!r} is not 'Act N of YYYY'"
        )
    return f"{match.group(1)}/{match.group(2)}"


def get_publication_date(link: str) -> date:
    match = _PUBLICATION_DATE_PATTERN.search(link)
    if match is None:
        raise HansardActsSupplementError(f"The link {link} holds no publication date")
    try:
        return datetime.strptime(match.group(1), _PUBLICATION_DATE_FORMAT).date()
    except ValueError as error:
        raise HansardActsSupplementError(
            f"The link {link} holds an impossible publication date"
        ) from error


def build_planned_entry(
    listing_row: ListingRow, capture_url: str
) -> PlannedActsSupplementEntry:
    return PlannedActsSupplementEntry(
        printed_title=listing_row.printed_title,
        printed_number=listing_row.printed_number,
        link=listing_row.link,
        pdf_link=listing_row.pdf_link,
        pdf_size=listing_row.pdf_size,
        act_number=get_act_number(listing_row.printed_number),
        publication_date=get_publication_date(listing_row.link),
        capture_url=capture_url,
    )


def get_first_planned_entries(
    planned_entries: list[PlannedActsSupplementEntry],
) -> list[PlannedActsSupplementEntry]:
    act_number_and_link_to_entry: dict[tuple[str, str], PlannedActsSupplementEntry] = {}
    for planned_entry in planned_entries:
        act_number_and_link_to_entry.setdefault(
            (planned_entry.act_number, planned_entry.link), planned_entry
        )
    return list(act_number_and_link_to_entry.values())

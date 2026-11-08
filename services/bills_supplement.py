import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup
from bs4.element import Tag

from exceptions import HansardBillsSupplementError
from schemas.bills_supplement_plan import PlannedEntry

_PRINTED_NUMBER_PATTERN = re.compile(r"Bill (\d+) of (\d{4})")
_PUBLICATION_DATE_PATTERN = re.compile(r"/Published/(\d{8})(?:\D|$)")
_PUBLICATION_DATE_FORMAT = "%Y%m%d"
_PDF_SIZE_PATTERN = re.compile(r"\((.+)\)")


@dataclass(frozen=True)
class ListingRow:
    printed_title: str
    printed_number: str
    link: str
    pdf_link: Optional[str]
    pdf_size: Optional[str]


def _read_listing_row(table_row: Tag) -> ListingRow:
    title_anchor = table_row.select_one("a.non-ajax")
    if title_anchor is None:
        raise HansardBillsSupplementError("A listing row holds no title link")
    link = title_anchor.get("href")
    if not isinstance(link, str):
        raise HansardBillsSupplementError("A listing row's title link has no href")
    number_cell = table_row.select_one("td.col-no")
    if number_cell is None:
        raise HansardBillsSupplementError(f"The listing row of {link} has no number")
    pdf_anchor = table_row.select_one("a.file-download")
    if pdf_anchor is None:
        return ListingRow(
            printed_title=title_anchor.get_text().strip(),
            printed_number=number_cell.get_text().strip(),
            link=link,
            pdf_link=None,
            pdf_size=None,
        )
    pdf_link = pdf_anchor.get("href")
    if not isinstance(pdf_link, str):
        raise HansardBillsSupplementError(f"The PDF link of {link} has no href")
    pdf_size_match = _PDF_SIZE_PATTERN.search(str(pdf_anchor.get("data-size", "")))
    if pdf_size_match is None:
        raise HansardBillsSupplementError(f"The PDF link of {link} has no size")
    return ListingRow(
        printed_title=title_anchor.get_text().strip(),
        printed_number=number_cell.get_text().strip(),
        link=link,
        pdf_link=pdf_link,
        pdf_size=pdf_size_match.group(1),
    )


def parse_bills_supplement_listing(html: str) -> list[ListingRow]:
    soup = BeautifulSoup(html, "html.parser")
    return [
        _read_listing_row(table_row)
        for table_row in soup.select("tr[data-toggle=popover]")
    ]


def get_bill_number(printed_number: str) -> str:
    match = _PRINTED_NUMBER_PATTERN.fullmatch(printed_number)
    if match is None:
        raise HansardBillsSupplementError(
            f"The printed number {printed_number!r} is not 'Bill N of YYYY'"
        )
    return f"{match.group(1)}/{match.group(2)}"


def get_publication_date(link: str) -> date:
    match = _PUBLICATION_DATE_PATTERN.search(link)
    if match is None:
        raise HansardBillsSupplementError(f"The link {link} holds no publication date")
    try:
        return datetime.strptime(match.group(1), _PUBLICATION_DATE_FORMAT).date()
    except ValueError as error:
        raise HansardBillsSupplementError(
            f"The link {link} holds an impossible publication date"
        ) from error


def build_planned_entry(listing_row: ListingRow, capture_url: str) -> PlannedEntry:
    return PlannedEntry(
        printed_title=listing_row.printed_title,
        printed_number=listing_row.printed_number,
        link=listing_row.link,
        pdf_link=listing_row.pdf_link,
        pdf_size=listing_row.pdf_size,
        bill_number=get_bill_number(listing_row.printed_number),
        publication_date=get_publication_date(listing_row.link),
        capture_url=capture_url,
    )


def get_first_planned_entries(
    planned_entries: list[PlannedEntry],
) -> list[PlannedEntry]:
    bill_number_and_link_to_entry: dict[tuple[str, str], PlannedEntry] = {}
    for planned_entry in planned_entries:
        bill_number_and_link_to_entry.setdefault(
            (planned_entry.bill_number, planned_entry.link), planned_entry
        )
    return list(bill_number_and_link_to_entry.values())

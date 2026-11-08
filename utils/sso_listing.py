import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup
from bs4.element import Tag

from exceptions import HansardSsoListingError

_PDF_SIZE_PATTERN = re.compile(r"\((.+)\)")


@dataclass(frozen=True)
class ListingRow:
    printed_title: str
    printed_number: str
    link: str
    pdf_link: Optional[str]
    pdf_size: Optional[str]


@dataclass(frozen=True)
class ActListingRow:
    printed_title: str
    link: str
    printed_chapter: Optional[str]


@dataclass(frozen=True)
class _TitleLink:
    printed_title: str
    link: str


def _read_title_link(table_row: Tag) -> _TitleLink:
    title_anchor = table_row.select_one("a.non-ajax")
    if title_anchor is None:
        raise HansardSsoListingError("A listing row holds no title link")
    link = title_anchor.get("href")
    if not isinstance(link, str):
        raise HansardSsoListingError("A listing row's title link has no href")
    return _TitleLink(printed_title=title_anchor.get_text().strip(), link=link)


def _read_listing_row(table_row: Tag) -> ListingRow:
    title_link = _read_title_link(table_row)
    link = title_link.link
    number_cell = table_row.select_one("td.col-no")
    if number_cell is None:
        raise HansardSsoListingError(f"The listing row of {link} has no number")
    pdf_anchor = table_row.select_one("a.file-download")
    if pdf_anchor is None:
        return ListingRow(
            printed_title=title_link.printed_title,
            printed_number=number_cell.get_text().strip(),
            link=link,
            pdf_link=None,
            pdf_size=None,
        )
    pdf_link = pdf_anchor.get("href")
    if not isinstance(pdf_link, str):
        raise HansardSsoListingError(f"The PDF link of {link} has no href")
    pdf_size_match = _PDF_SIZE_PATTERN.search(str(pdf_anchor.get("data-size", "")))
    if pdf_size_match is None:
        raise HansardSsoListingError(f"The PDF link of {link} has no size")
    return ListingRow(
        printed_title=title_link.printed_title,
        printed_number=number_cell.get_text().strip(),
        link=link,
        pdf_link=pdf_link,
        pdf_size=pdf_size_match.group(1),
    )


def parse_sso_listing(html: str) -> list[ListingRow]:
    soup = BeautifulSoup(html, "html.parser")
    return [
        _read_listing_row(table_row)
        for table_row in soup.select("tr[data-toggle=popover]")
    ]


def _read_act_listing_row(table_row: Tag) -> ActListingRow:
    title_link = _read_title_link(table_row)
    chapter_cell = table_row.select_one("td.col-no")
    return ActListingRow(
        printed_title=title_link.printed_title,
        link=title_link.link,
        printed_chapter=None
        if chapter_cell is None
        else chapter_cell.get_text().strip(),
    )


def parse_sso_act_listing(html: str) -> list[ActListingRow]:
    soup = BeautifulSoup(html, "html.parser")
    return [
        _read_act_listing_row(table_row)
        for table_row in soup.select("tr[data-toggle=popover]")
    ]

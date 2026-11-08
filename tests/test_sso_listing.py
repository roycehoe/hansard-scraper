import pytest

from exceptions import HansardSsoListingError
from utils.sso_listing import (
    ActListingRow,
    ListingRow,
    parse_sso_act_listing,
    parse_sso_listing,
)

_ALL_YEARS_ROW = """
<table><tbody>
<tr class="" data-toggle="popover" data-trigger="hover" data-placement="bottom">
  <td class="hidden-xs">2016</td>
  <td>
    <a class="non-ajax" href="/Bills-Supp/19-2016/Published/20160711?DocDate=20160711" rel="">Singapore Workforce Development Agency  (Amendment) Bill</a>
    <div class="visible-xs">
      <div class="col-4">Bill 19 of 2016</div>
      <a href="/Bills-Supp/19-2016/Published/20160711?DocDate=20160711&amp;ViewType=Pdf&amp;_=20230823222022" class="dropdown-item non-ajax file-download" data-size=" (222.1 KB)">Download</a>
    </div>
  </td>
  <td class="hidden-xs col-no">
    Bill 19 of 2016
  </td>
  <td class="hidden-xs">
    <a href="/Bills-Supp/19-2016/Published/20160711?DocDate=20160711&amp;ViewType=Pdf&amp;_=20230823222022" class="non-ajax file-download" data-size=" (222.1 KB)"></a>
  </td>
</tr>
</tbody></table>
"""
_YEAR_PAGE_ROW = """
<table><tbody>
<tr class="alternate" data-toggle="popover" data-trigger="hover" data-placement="bottom">
  <td>
    <a class="non-ajax" href="/Bills-Supp/2-2026/Published/20260203?DocDate=20260203" rel="">Coastal Protection &amp; Other Amendments Bill</a>
  </td>
  <td class="hidden-xs col-no">Bill 2 of 2026</td>
</tr>
</tbody></table>
"""


def test_parse_reads_a_row_of_the_all_years_page() -> None:
    assert parse_sso_listing(_ALL_YEARS_ROW) == [
        ListingRow(
            printed_title="Singapore Workforce Development Agency  (Amendment) Bill",
            printed_number="Bill 19 of 2016",
            link="/Bills-Supp/19-2016/Published/20160711?DocDate=20160711",
            pdf_link="/Bills-Supp/19-2016/Published/20160711?DocDate=20160711&ViewType=Pdf&_=20230823222022",
            pdf_size="222.1 KB",
        )
    ]


def test_parse_reads_a_row_of_a_year_page_without_a_pdf() -> None:
    assert parse_sso_listing(_YEAR_PAGE_ROW) == [
        ListingRow(
            printed_title="Coastal Protection & Other Amendments Bill",
            printed_number="Bill 2 of 2026",
            link="/Bills-Supp/2-2026/Published/20260203?DocDate=20260203",
            pdf_link=None,
            pdf_size=None,
        )
    ]


def test_parse_of_a_page_without_rows_is_empty() -> None:
    assert parse_sso_listing("<html></html>") == []


def test_parse_raises_on_a_row_without_a_title_link() -> None:
    html = '<tr data-toggle="popover"><td class="col-no">Bill 2 of 2026</td></tr>'

    with pytest.raises(HansardSsoListingError, match="no title link"):
        parse_sso_listing(html)


def test_parse_raises_on_a_row_without_a_number() -> None:
    html = '<tr data-toggle="popover"><td><a class="non-ajax" href="/x">T</a></td></tr>'

    with pytest.raises(HansardSsoListingError, match="has no number"):
        parse_sso_listing(html)


_REPEALED_ROW_WITH_CHAPTER = """
<table><tbody>
<tr class="" data-toggle="popover" data-trigger="hover" data-placement="bottom">
  <td><a class="non-ajax" href="/Act/AA1987/Repealed/20040401?DocDate=20011231" rel="">Accountants Act (Repealed)</a>
    <div class="visible-xs"><div class="row"><div class="col-xs-4 no-side-padding">Cap. 2</div></div></div></td>
  <td class="hidden-xs col-no">Cap. 2</td>
  <td class="hidden-xs">&nbsp;</td>
</tr>
</tbody></table>
"""
_REPEALED_ROW_WITHOUT_CHAPTER = """
<table><tbody>
<tr class="alternate" data-toggle="popover" data-trigger="hover" data-placement="bottom">
  <td><a class="non-ajax" href="/Act/SA1994/Repealed/20240101?DocDate=20231231" rel="">Supply Act 1994 (Spent)</a></td>
  <td class="hidden-xs">&nbsp;</td>
</tr>
</tbody></table>
"""


def test_parse_act_listing_reads_a_row_with_a_chapter() -> None:
    assert parse_sso_act_listing(_REPEALED_ROW_WITH_CHAPTER) == [
        ActListingRow(
            printed_title="Accountants Act (Repealed)",
            link="/Act/AA1987/Repealed/20040401?DocDate=20011231",
            printed_chapter="Cap. 2",
        )
    ]


def test_parse_act_listing_reads_a_spent_row_without_a_chapter() -> None:
    assert parse_sso_act_listing(_REPEALED_ROW_WITHOUT_CHAPTER) == [
        ActListingRow(
            printed_title="Supply Act 1994 (Spent)",
            link="/Act/SA1994/Repealed/20240101?DocDate=20231231",
            printed_chapter=None,
        )
    ]


def test_parse_act_listing_raises_on_a_row_without_a_title_link() -> None:
    html = '<tr data-toggle="popover"><td class="col-no">Cap. 2</td></tr>'

    with pytest.raises(HansardSsoListingError, match="no title link"):
        parse_sso_act_listing(html)

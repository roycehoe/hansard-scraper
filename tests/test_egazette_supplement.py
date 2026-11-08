from datetime import date
from pathlib import Path

import pytest

from enums import EgazetteSupplementKind
from exceptions import HansardEgazetteSupplementError
from services.egazette_supplement import (
    ParsedEgazetteSupplement,
    get_bill_number,
    parse_egazette_supplement_text,
)

_FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "egazette_supplement"


def _read_fixture(name: str) -> str:
    return (_FIXTURE_DIRECTORY / name).read_text(encoding="utf8")


def test_a_bills_supplement_is_parsed_from_its_cover_and_first_page() -> None:
    parsed_supplement = parse_egazette_supplement_text(
        _read_fixture("bills_2024_01.txt"), EgazetteSupplementKind.BILLS
    )

    assert parsed_supplement == ParsedEgazetteSupplement(
        printed_title="Enlistment and Other Matters (Amendment) Bill",
        printed_bill_number="1/2024",
        bill_number="1/2024",
        first_reading_date=date(2024, 1, 9),
        passing_date=None,
        printed_act_number=None,
    )


def test_an_acts_supplement_with_an_act_number_reads_the_passing_date_and_number() -> (
    None
):
    parsed_supplement = parse_egazette_supplement_text(
        _read_fixture("acts_2026_01.txt"), EgazetteSupplementKind.ACTS
    )

    assert parsed_supplement == ParsedEgazetteSupplement(
        printed_title="Electronic Conveyancing and Other Matters Bill",
        printed_bill_number="11/2025",
        bill_number="11/2025",
        first_reading_date=date(2025, 9, 25),
        passing_date=date(2025, 10, 15),
        printed_act_number="20 of 2025",
    )


def test_an_acts_supplement_that_prints_no_act_number_keeps_it_empty() -> None:
    parsed_supplement = parse_egazette_supplement_text(
        _read_fixture("acts_2025_01.txt"), EgazetteSupplementKind.ACTS
    )

    assert parsed_supplement.printed_title == "FoodSafetyandSecurityBill"
    assert parsed_supplement.printed_bill_number == "49/2024"
    assert parsed_supplement.first_reading_date == date(2024, 11, 12)
    assert parsed_supplement.passing_date == date(2025, 1, 8)
    assert parsed_supplement.printed_act_number is None


def test_an_ordinal_day_and_a_two_digit_year_are_read() -> None:
    text = "Companies Bill\nBill No. 1/99.\nRead the first time on 20th January 1999.\n"

    parsed_supplement = parse_egazette_supplement_text(
        text, EgazetteSupplementKind.BILLS
    )

    assert parsed_supplement.printed_bill_number == "1/99"
    assert parsed_supplement.bill_number == "1/1999"
    assert parsed_supplement.first_reading_date == date(1999, 1, 20)


def test_an_urgent_bill_suffix_and_dropped_spaces_are_read() -> None:
    text = "Insurance (Amendment) Bill\nBillNo.40/2024 [Urgent Bill].\nReadthefirsttimeon14October2024.\n"

    parsed_supplement = parse_egazette_supplement_text(
        text, EgazetteSupplementKind.BILLS
    )

    assert parsed_supplement.bill_number == "40/2024"
    assert parsed_supplement.first_reading_date == date(2024, 10, 14)


@pytest.mark.parametrize(
    ("printed_bill_number", "bill_number"),
    [
        ("1/99", "1/1999"),
        ("2/50", "2/1950"),
        ("3/49", "3/2049"),
        ("4/05", "4/2005"),
        ("11/2025", "11/2025"),
    ],
)
def test_a_two_digit_year_of_50_or_more_is_19yy_and_below_50_is_20yy(
    printed_bill_number: str, bill_number: str
) -> None:
    assert get_bill_number(printed_bill_number) == bill_number


def test_a_text_with_no_bill_number_raises() -> None:
    with pytest.raises(HansardEgazetteSupplementError, match="No Bill No. line"):
        parse_egazette_supplement_text(
            "Some Bill\nRead the first time on 9 January 2024.\n",
            EgazetteSupplementKind.BILLS,
        )


def test_a_text_with_no_first_reading_date_raises() -> None:
    with pytest.raises(HansardEgazetteSupplementError, match="No first reading date"):
        parse_egazette_supplement_text(
            "Some Bill\nBill No. 1/2024.\nA BILL\n", EgazetteSupplementKind.BILLS
        )


def test_a_text_with_no_title_raises() -> None:
    with pytest.raises(HansardEgazetteSupplementError, match="No title"):
        parse_egazette_supplement_text(
            "Bill No. 1/2024.\nRead the first time on 9 January 2024.\n",
            EgazetteSupplementKind.BILLS,
        )

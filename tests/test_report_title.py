import pytest

from services.report import build_report_header


@pytest.mark.parametrize(
    ("raw_title", "title", "subtitle"),
    [
        ("PENAL CODE (AMENDMENT) BILL,PENAL CODE (AMENDMENT) BILL", "PENAL CODE (AMENDMENT) BILL", None),
        ("\tBUDGET, MINISTRY OF LABOUR", "BUDGET, MINISTRY OF LABOUR", None),
        ("MARTIAL ARTS INSTRUCTION (REPEAL) BILL<br>\r ", "MARTIAL ARTS INSTRUCTION (REPEAL) BILL", None),
        ("Committee of Supply – Head S (Ministry of Manpower) ", "Committee of Supply – Head S", "(Ministry of Manpower)"),
        ("HDB FLATS (Repossession),HDB FLATS (Concessionary interest rate)", "HDB FLATS", "(Concessionary interest rate)"),
        ("CYBER/GAMING CAFES,CYBER/GAMING CAFES (Measures)", "CYBER/GAMING CAFES", "(Measures)"),
        ("ORAL ANSWERS,WRITTEN ANSWERS", "ORAL ANSWERS,WRITTEN ANSWERS", None),
    ],
)
def test_title_is_trimmed_untagged_and_collapsed(raw_title: str, title: str, subtitle: str) -> None:
    report_header = build_report_header(raw_title)

    assert (report_header.title, report_header.subtitle) == (title, subtitle)

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
        ("SAFETY AT WORKPLACES (Motion),SAFETY AT WORKPLACES", "SAFETY AT WORKPLACES", "(Motion)"),
        (
            "FOREIGN WORKERS (Rental of HDB flats),FOREIGN WORKERS (Rental of flats in Jurong, Boon Lay and Woodlands)",
            "FOREIGN WORKERS",
            "(Rental of flats in Jurong, Boon Lay and Woodlands)",
        ),
        ("SUPPLEMENTARY SUPPLY (No. 2) BILL (Business Motion)", "SUPPLEMENTARY SUPPLY (No. 2) BILL", "(Business Motion)"),
        ("MALAYANISATION (Public Service) (Statement by the Chief Minister)", "MALAYANISATION (Public Service)", "(Statement by the Chief Minister)"),
        ("CONSTITUTION OF THE REPUBLIC OF SINGAPORE (Article 5(2A))", "CONSTITUTION OF THE REPUBLIC OF SINGAPORE", "(Article 5(2A))"),
        ("SUSPENSION OF STANDING ORDER 31 (7) AND (8)", "SUSPENSION OF STANDING ORDER 31 (7) AND (8)", None),
        ("MERGER (SINGAPORE/FEDERATION OF MALAYA (White Paper)", "MERGER (SINGAPORE/FEDERATION OF MALAYA", "(White Paper)"),
    ],
)
def test_title_is_trimmed_untagged_and_collapsed(raw_title: str, title: str, subtitle: str) -> None:
    report_header = build_report_header(raw_title)

    assert (report_header.title, report_header.subtitle) == (title, subtitle)

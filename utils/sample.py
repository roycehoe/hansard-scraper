from datetime import datetime

from sqlmodel import Session

from crud.report import CRUDReport
from database.init import engine
from database.report import Report
from enums import ReportType


def get_strata_sample() -> list[Report]:
    MAX_PARLIAMENT_NUMBER = 12
    strata_sample: list[Report] = []
    with Session(engine) as session:
        crud = CRUDReport(session)
        for parliament_number in range(1, MAX_PARLIAMENT_NUMBER + 1):
            for report_type_enum in ReportType:
                sample = crud.get_first_filtered(
                    sitting_date_before=datetime(2012, 9, 10),
                    parliament_number=parliament_number,
                    report_type=report_type_enum.value,
                    has_content=True,
                )
                if sample is None:
                    continue
                strata_sample.append(sample)
    return strata_sample

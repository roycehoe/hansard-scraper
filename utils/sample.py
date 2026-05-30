from datetime import datetime

from sqlmodel import Session, select

from database.init import engine
from database.report import Report
from enums import ReportType


def get_strata_sample() -> list[Report]:
    MAX_PARLIAMENT_NUMBER = 12
    strata_sample: list[Report] = []
    with Session(engine) as session:
        for parliament_number in range(1, MAX_PARLIAMENT_NUMBER + 1):
            for report_type_enum in ReportType:
                sample = session.exec(
                    select(Report)
                    .where(Report.sitting_date < datetime(2012, 9, 10, 0, 0, 0, 0))
                    .where(Report.content != None)
                    .where(Report.report_type == report_type_enum.value)
                    .where(Report.parliament_number == parliament_number)
                ).first()
                if sample is None:
                    continue
                strata_sample.append(sample)
    return strata_sample

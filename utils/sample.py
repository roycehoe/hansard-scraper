from datetime import datetime

from sqlmodel import select

from database.init import get_session
from database.report import Report
from enums import ReportType



def get_strata_sample() -> list[Report]:
    session = next(get_session())
    strata_sample: list[Report] = []
    MAX_PARLIAMENT_NUMBER = 12
    for parliament_number in range(MAX_PARLIAMENT_NUMBER):
        for report_type_enum in ReportType:
            sample = session.exec(
                select(Report)
                .where(Report.sitting_date < datetime(2012, 9, 10, 0, 0, 0, 0))
                .where(Report.content != None)
                .where(Report.report_type == report_type_enum.value)
                .where(Report.sitting_number == parliament_number)
            ).first()
            if sample is None:
                continue
            strata_sample.append(sample)
    return strata_sample
from datetime import datetime

from database.report import Report
from schemas import HandsardSearchResult


def get_db_report_in(handsard_search_result: HandsardSearchResult) -> Report:
    sitting_date = datetime.strptime(handsard_search_result.sittingDate, "%d-%m-%Y")
    return Report(
        volumeNo=int(handsard_search_result.volumeNo),
        parlNo=int(handsard_search_result.parlNo),
        sittingNo=(
            handsard_search_result.sittingNo
            if handsard_search_result.sittingNo is None
            else int(handsard_search_result.sittingNo)
        ),
        sittingDate=sitting_date,
        sno=int(handsard_search_result.sno),
        title=handsard_search_result.title,
        subtitle=(
            handsard_search_result.subtitle
            if handsard_search_result.subtitle is None
            else handsard_search_result.subtitle
        ),
        reportId=handsard_search_result.reportId,
        reportType=handsard_search_result.reportType,
        columnStart=(
            handsard_search_result.columnStart
            if handsard_search_result.columnStart is None
            else handsard_search_result.columnStart
        ),
        columnEnd=(
            handsard_search_result.columnEnd
            if handsard_search_result.columnEnd is None
            else handsard_search_result.columnEnd
        ),
        htmlFileName=(
            handsard_search_result.htmlFileName
            if handsard_search_result.htmlFileName is None
            else handsard_search_result.htmlFileName
        ),
        content=None,
        reportVersion=handsard_search_result.reportVersion,
    )

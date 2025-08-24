UNUSED_FIELDS = {
    "questionCount",
    "fullContentFlag",
    "footNoteQuestion",
    "ptbaTo",
    "clarificationTitle",
    "content",
    "footNote",
    "onlinePDFFileName",
    "verPdf",
    "ptbaFrom",
    "memberId",
    "ptbaList",
    "footNoteQuestions",
    "htmlContent",
    "attendanceList",
    "htmlFullContent",
    "memberName",
    "mpNames",
    "reportEndCol",
    "reportStartCol",
    "sessionNo",
    "clarificationText",
    "clarificationSubTitle",
    "score",
    "footNotes",
    "pdfNodes",
    "portfolio",
    "atbpList",
    "reportContent",
}


def get_parliament_reports_without_report_content(parliament_reports: list[dict]):
    parliament_reports_without_report_content = []
    for parliament_report in parliament_reports:
        parliament_reports_without_report_content.append(
            {**parliament_report, "reportContent": ""}
        )
    return parliament_reports_without_report_content


def get_parliament_reports_without_unused_fields(
    parliament_reports: list[dict], unused_fields: set[str] = UNUSED_FIELDS
):
    parliament_reports_without_unused_fields = []
    for parliament_report in parliament_reports:
        parliament_reports_without_unused_fields.append(
            {k: v for k, v in parliament_report.items() if k not in unused_fields}
        )
    return parliament_reports_without_unused_fields


def get_unused_fields(parliament_reports: list[dict]):
    parliament_reports_key_usage_count = {}
    for key in parliament_reports[0].keys():
        parliament_reports_key_usage_count[key] = 0

    for parliament_report in parliament_reports:
        for key in parliament_reports_key_usage_count:
            if parliament_report[key] is None:
                continue
            if isinstance(parliament_report[key], list):
                if not parliament_report[key]:
                    continue
            if isinstance(parliament_report[key], str):
                if parliament_report[key] == "":
                    continue
            parliament_reports_key_usage_count[key] += 1
    return {
        field
        for field, value in parliament_reports_key_usage_count.items()
        if value == 0
    }

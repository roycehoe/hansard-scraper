import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.hansard_website_response import HansardWebsiteResponse
from services.report import build_report
from services.sitting import build_sitting

_HEADER_TABLE = (
    '<table width="100%" border="0" cellpadding="0" cellspacing="0">'
    '<tr valign="top"><td width="15%"><font size="2">Parliament No:</font></td><td width="85%"><font size="2">11</font></td></tr>'
    '<tr valign="top"><td width="15%"><font size="2">Session No:</font></td><td width="85%"><font size="2">1</font></td></tr>'
    '<tr valign="top"><td width="15%"><font size="2">Volume No:</font></td><td width="85%"><font size="2">83</font></td></tr>'
    '<tr valign="top"><td width="15%"><font size="2">Sitting No:</font></td><td width="85%"><font size="2">14</font></td></tr>'
    '<tr valign="top"><td width="15%"><font size="2">Sitting Date:</font></td><td width="85%"><font size="2">22-10-2007</font></td></tr>'
    "</table>"
)
_HEADER_SESSION_NUMBER = 1
_HEADER_SITTING_NUMBER = 14
_SEARCH_SITTING_NUMBER = 4


def test_report_without_a_search_sitting_number_takes_the_header_one() -> None:
    hansard_website_response = HansardWebsiteResponse(
        volumeNo="83", parlNo="11", sittingNo=None, sittingDate="22-10-2007", sno="1", title="PENAL CODE (AMENDMENT) BILL",
        reportId="00075611-WA.00072393-ZZ_1##", reportType="bill", htmlFileName="012_20071022_S0003_T0002",
        content=f"<html><body>{_HEADER_TABLE}<p>Text</p></body></html>", reportVersion="sprs2",
    )

    assert build_report(hansard_website_response).sitting_number == _HEADER_SITTING_NUMBER


def test_report_keeps_the_search_sitting_number() -> None:
    hansard_website_response = HansardWebsiteResponse(
        volumeNo="83", parlNo="11", sittingNo=str(_SEARCH_SITTING_NUMBER), sittingDate="22-10-2007", sno="1", title="PENAL CODE (AMENDMENT) BILL",
        reportId="00075611-WA.00072393-ZZ_1##", reportType="bill", htmlFileName="012_20071022_S0003_T0002",
        content=f"<html><body>{_HEADER_TABLE}<p>Text</p></body></html>", reportVersion="sprs2",
    )

    assert build_report(hansard_website_response).sitting_number == _SEARCH_SITTING_NUMBER


def test_older_system_sitting_takes_session_and_sitting_numbers_from_its_header() -> None:
    hansard_sitting_date_response = HansardSittingDateResponse(
        volume_no=83, sitting_date="22-10-2007", html_full_content=f"<html><body>{_HEADER_TABLE}<p>PRESENT:</p></body></html>",
    )

    sitting = build_sitting(hansard_sitting_date_response)

    assert (sitting.session_no, sitting.sitting_no) == (_HEADER_SESSION_NUMBER, _HEADER_SITTING_NUMBER)

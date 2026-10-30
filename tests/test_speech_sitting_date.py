from datetime import datetime

from database.report import Report
from enums import ReportType, SpeechKind
from services.speech import ParsedSpeech, build_speeches

_REPORT_ID = 4039
_SITTING_DATE = datetime(1965, 12, 8)
_REPORT_TYPE = ReportType.MOTION


def test_stage_4_rows_carry_the_report_date_and_type_and_number_from_one() -> None:
    report = Report(id=_REPORT_ID, sitting_date=_SITTING_DATE, report_type=_REPORT_TYPE)
    parsed_speeches = [
        ParsedSpeech(speaker="Mr Speaker", transcript="Order, order.", kind=SpeechKind.SPEECH),
        ParsedSpeech(speaker=None, transcript="Question put, and agreed to.", kind=SpeechKind.PROCEDURAL),
    ]

    speeches = build_speeches(report, parsed_speeches)

    assert [(speech.ordinal, speech.speaker, speech.kind, speech.report_id, speech.sitting_date, speech.report_type) for speech in speeches] == [
        (1, "Mr Speaker", SpeechKind.SPEECH, _REPORT_ID, _SITTING_DATE, _REPORT_TYPE),
        (2, None, SpeechKind.PROCEDURAL, _REPORT_ID, _SITTING_DATE, _REPORT_TYPE),
    ]

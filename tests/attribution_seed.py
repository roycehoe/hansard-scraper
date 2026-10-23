from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from database.report import Report
from database.speaker import Speaker
from database.speech import Speech
from enums import ReportType, ReportVersion

_SPEAKER_NAME = "Tan Ah Kow"
_SPEAKER_PARTY = "PAP"
_SPEECH_NUMBER = 1
_REPORT_CONTENT = "<p>Stored text</p>"
_PARLIAMENT_TO_SITTING_DATE = {
    10: datetime(2004, 3, 1),
    12: datetime(2013, 1, 14),
    13: datetime(2017, 1, 9),
    14: datetime(2021, 1, 4),
}
_PARLIAMENT_TO_REPORT_VERSION = {
    10: ReportVersion.SPRS2,
    12: ReportVersion.SPRS3,
    13: ReportVersion.SPRS3,
    14: ReportVersion.SPRS3,
}


@dataclass(frozen=True)
class _SeedSpeech:
    speaker: Optional[str]
    is_linked: bool
    transcript: str


@dataclass(frozen=True)
class _SeedReport:
    report_id: str
    parliament_number: int
    report_type: ReportType
    title: str
    markdown_content: str
    speeches: tuple[_SeedSpeech, ...]


_SEED_REPORTS = (
    _SeedReport(
        report_id="headline-oral-answer",
        parliament_number=10,
        report_type=ReportType.ORAL_ANSWER,
        title="Public Housing Grants",
        markdown_content=(
            "**Public Housing Grants**\n\n"
            "**Mr Speaker:** Order. Question No 1.\n\n"
            "**Mr Tan Ah Kow (Bishan):** asked the Minister for National Development how many grants were paid last year.\n\n"
            "---\n\n"
            "**Mr Lim Boon Heng:** Sir, the Ministry paid 4,210 grants last year.\n\n"
            "**hon. Members:** Hear, hear.\n\n"
            "Question put, and agreed to.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow (Bishan)", True, "asked the Minister for National Development how many grants were paid last year."),
            _SeedSpeech("Mr Lim Boon Heng", False, "Sir, the Ministry paid 4,210 grants last year."),
            _SeedSpeech("hon. Members", False, "Hear, hear."),
            _SeedSpeech(None, False, "Question put, and agreed to."),
        ),
    ),
    _SeedReport(
        report_id="headline-motion",
        parliament_number=10,
        report_type=ReportType.MOTION,
        title="Transport Fares",
        markdown_content=(
            "**Transport Fares**\n\n"
            "**Mr Tan Ah Kow (Bishan):** Sir, I beg to move that this House calls for a review of transport fares.\n\n"
            "**(In Mandarin) Mr Lim Boon Heng:** The fares rose twice in two years.\n\n"
            "**Mr Lim Boon Heng:** I support the motion.\n\n"
            "Question put, and agreed to.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow (Bishan)", True, "Sir, I beg to move that this House calls for a review of transport fares."),
            _SeedSpeech("(In Mandarin) Mr Lim Boon Heng", False, "The fares rose twice in two years."),
            _SeedSpeech("Mr Lim Boon Heng", False, "I support the motion."),
            _SeedSpeech(None, False, "Question put, and agreed to."),
        ),
    ),
    _SeedReport(
        report_id="headline-written-answer",
        parliament_number=10,
        report_type=ReportType.WRITTEN_ANSWER,
        title="Water Prices",
        markdown_content="**Water Prices**\n\n**Mr Tan Ah Kow (Bishan):** The tariff stays at its present level until 2006.\n",
        speeches=(),
    ),
    _SeedReport(
        report_id="headline-header-row",
        parliament_number=10,
        report_type=ReportType.MOTION,
        title="Recess",
        markdown_content=(
            "Parliament No:| 10\n"
            "Title:| Recess\n"
            "Sitting Date:| 1-3-2004\n\n"
            "Mr Tan Ah Kow moved that the House do now adjourn.\n\n"
            "The House adjourned at 6.30 pm.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow", True, "moved that the House do now adjourn."),
            _SeedSpeech(None, False, "The House adjourned at 6.30 pm."),
        ),
    ),
    _SeedReport(
        report_id="parliament-12-oral-answer",
        parliament_number=12,
        report_type=ReportType.ORAL_ANSWER,
        title="Hospital Waiting Times",
        markdown_content=(
            "**Hospital Waiting Times**\n\n"
            "**Mr Tan Ah Kow (Bishan-Toa Payoh):** asked the Minister for Health what the median waiting time is at polyclinics.\n\n"
            "**The Minister for Health (Mr Lim Boon Heng):** The median waiting time is 40 minutes.\n\n"
            "**Hon Members:** Hear, hear.\n\n"
            "Question No 2 was deferred.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow (Bishan-Toa Payoh)", True, "asked the Minister for Health what the median waiting time is at polyclinics."),
            _SeedSpeech("The Minister for Health (Mr Lim Boon Heng)", False, "The median waiting time is 40 minutes."),
            _SeedSpeech("Hon Members", False, "Hear, hear."),
            _SeedSpeech(None, False, "Question No 2 was deferred."),
        ),
    ),
    _SeedReport(
        report_id="parliament-12-motion",
        parliament_number=12,
        report_type=ReportType.MOTION,
        title="Ageing Population",
        markdown_content=(
            "**Ageing Population**\n\n"
            "**Mr Tan Ah Kow (Bishan-Toa Payoh):** Madam, I beg to move that this House supports the plan for successful ageing.\n\n"
            "**(In Malay) Mr Lim Boon Heng:** The plan needs more day care centres.\n\n"
            "**Mr Lim Boon Heng:** I support the motion with one reservation.\n\n"
            "Resolved, that this House supports the plan.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow (Bishan-Toa Payoh)", True, "Madam, I beg to move that this House supports the plan for successful ageing."),
            _SeedSpeech("(In Malay) Mr Lim Boon Heng", False, "The plan needs more day care centres."),
            _SeedSpeech("Mr Lim Boon Heng", False, "I support the motion with one reservation."),
            _SeedSpeech(None, False, "Resolved, that this House supports the plan."),
        ),
    ),
    _SeedReport(
        report_id="parliament-12-written-answer",
        parliament_number=12,
        report_type=ReportType.WRITTEN_ANSWER,
        title="School Bus Fares",
        markdown_content=(
            "MPs Speaking:| Mr Tan Ah Kow\n\n"
            "The Ministry reviews school bus fares each year with the operators and the schools.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow", True, "The Ministry reviews school bus fares each year with the operators and the schools."),
        ),
    ),
    _SeedReport(
        report_id="parliament-13-oral-answer",
        parliament_number=13,
        report_type=ReportType.ORAL_ANSWER,
        title="Cycling Paths",
        markdown_content=(
            "**Cycling Paths**\n\n"
            "**Mr Tan Ah Kow (Bishan-Toa Payoh):** asked the Minister for Transport how many kilometres of cycling paths will be built by 2020.\n\n"
            "**Mr Lim Boon Heng:** About 700 kilometres.\n\n"
            "**Hon Members:** Hear, hear.\n\n"
            "The Minister for Transport tabled the answer.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow (Bishan-Toa Payoh)", True, "asked the Minister for Transport how many kilometres of cycling paths will be built by 2020."),
            _SeedSpeech("Mr Lim Boon Heng", False, "About 700 kilometres."),
            _SeedSpeech("Hon Members", False, "Hear, hear."),
            _SeedSpeech(None, False, "The Minister for Transport tabled the answer."),
        ),
    ),
    _SeedReport(
        report_id="parliament-13-motion",
        parliament_number=13,
        report_type=ReportType.MOTION,
        title="Future Economy",
        markdown_content=(
            "**Future Economy**\n\n"
            "**Mr Tan Ah Kow (Bishan-Toa Payoh):** Mr Speaker, I beg to move the motion standing in my name.\n\n"
            "**(In Tamil) Mr Lim Boon Heng:** Workers need help to retrain.\n\n"
            "**Mr Lim Boon Heng:** Sir, the motion has my support, and I will say why in three parts.\n\n"
            "Question put, and agreed to.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow (Bishan-Toa Payoh)", True, "Mr Speaker, I beg to move the motion standing in my name."),
            _SeedSpeech("(In Tamil) Mr Lim Boon Heng", False, "Workers need help to retrain."),
            _SeedSpeech("Mr Lim Boon Heng", False, "Sir, the motion has my support, and I will say why in three parts."),
            _SeedSpeech(None, False, "Question put, and agreed to."),
        ),
    ),
    _SeedReport(
        report_id="parliament-14-oral-answer",
        parliament_number=14,
        report_type=ReportType.ORAL_ANSWER,
        title="Vaccination Rates",
        markdown_content=(
            "**Vaccination Rates**\n\n"
            "**Mr Tan Ah Kow (Bishan-Toa Payoh):** asked the Minister for Health what share of seniors are vaccinated.\n\n"
            "**Mr Lim Boon Heng:** Nine in ten seniors are vaccinated.\n\n"
            "**Hon Members:** Hear, hear.\n\n"
            "Question No 5 was answered in writing.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow (Bishan-Toa Payoh)", True, "asked the Minister for Health what share of seniors are vaccinated."),
            _SeedSpeech("Mr Lim Boon Heng", False, "Nine in ten seniors are vaccinated."),
            _SeedSpeech("Hon Members", False, "Hear, hear."),
            _SeedSpeech(None, False, "Question No 5 was answered in writing."),
        ),
    ),
    _SeedReport(
        report_id="parliament-14-motion",
        parliament_number=14,
        report_type=ReportType.MOTION,
        title="Climate Action",
        markdown_content=(
            "**Climate Action**\n\n"
            "**Mr Tan Ah Kow (Bishan-Toa Payoh):** Mr Speaker, I beg to move that this House calls for faster climate action.\n\n"
            "**(In Mandarin) Mr Lim Boon Heng:** Sea levels will rise.\n\n"
            "**Mr Lim Boon Heng:** I support the motion.\n\n"
            "Question put, and agreed to.\n"
        ),
        speeches=(
            _SeedSpeech("Mr Tan Ah Kow (Bishan-Toa Payoh)", True, "Mr Speaker, I beg to move that this House calls for faster climate action."),
            _SeedSpeech("(In Mandarin) Mr Lim Boon Heng", False, "Sea levels will rise."),
            _SeedSpeech("Mr Lim Boon Heng", False, "I support the motion."),
            _SeedSpeech(None, False, "Question put, and agreed to."),
        ),
    ),
)


def _build_report(seed_report: _SeedReport) -> Report:
    return Report(
        volumeNo=seed_report.parliament_number,
        parlNo=seed_report.parliament_number,
        sittingNo=None,
        sittingDate=_PARLIAMENT_TO_SITTING_DATE[seed_report.parliament_number],
        sno=_SPEECH_NUMBER,
        original_title=seed_report.title,
        title=seed_report.title,
        reportId=seed_report.report_id,
        reportType=seed_report.report_type,
        content=_REPORT_CONTENT,
        markdown_content=seed_report.markdown_content,
        htmlFileName=None,
        reportVersion=_PARLIAMENT_TO_REPORT_VERSION[seed_report.parliament_number],
    )


def _build_speech(report: Report, ordinal: int, seed_speech: _SeedSpeech, speaker_id: Optional[int]) -> Speech:
    assert report.id is not None
    return Speech(
        ordinal=ordinal,
        speaker=seed_speech.speaker,
        transcript=seed_speech.transcript,
        sitting_date=report.sitting_date,
        report_id=report.id,
        speaker_id=speaker_id if seed_speech.is_linked else None,
    )


def seed_attribution_rows(session: Session) -> None:
    parliament_to_speaker = {
        parliament_number: Speaker(name=_SPEAKER_NAME, party=_SPEAKER_PARTY, is_legislative_assembly=False, parliament_number=parliament_number)
        for parliament_number in _PARLIAMENT_TO_SITTING_DATE
    }
    reports = [_build_report(seed_report) for seed_report in _SEED_REPORTS]
    session.add_all([*parliament_to_speaker.values(), *reports])
    session.flush()

    speeches = [
        _build_speech(report, ordinal, seed_speech, parliament_to_speaker[seed_report.parliament_number].id)
        for seed_report, report in zip(_SEED_REPORTS, reports)
        for ordinal, seed_speech in enumerate(seed_report.speeches, start=1)
    ]
    session.add_all(speeches)
    session.commit()

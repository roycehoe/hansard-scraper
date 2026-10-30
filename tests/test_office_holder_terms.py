from datetime import date, datetime

from sqlmodel import Session, select

from database.report import Report
from database.speaker import Speaker
from database.speech import Speech
from enums import ReportType, ReportVersion
from populate.speaker_links import link_speakers_by_report_ids_and_sitting_ids
from utils.data_files import get_heads_of_state
from utils.speaker_resolution_constants import DATED_ROLE_TERMS, HEAD_OF_STATE_TERMS

_PARLIAMENT_NUMBER = 15
_PREVIOUS_PARLIAMENT_NUMBER = 14
_PRIME_MINISTER = "Lawrence Wong"
_PRESIDENT = "Tharman Shanmugaratnam"
_SPEECH_NUMBER = 1
_ORDINAL = 1


def _get_holder_on(terms: tuple[tuple[date, date, str], ...], day: date) -> list[str]:
    return [name for first, last, name in terms if first <= day <= last]


def _build_report(report_id: str, title: str, report_type: ReportType, sitting_date: datetime) -> Report:
    return Report(
        volumeNo=_PARLIAMENT_NUMBER,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=sitting_date,
        sno=_SPEECH_NUMBER,
        original_title=title,
        title=title,
        reportId=report_id,
        reportType=report_type,
        content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _seed_one_speech(scratch_session: Session, speaker: Speaker, report: Report, label: str) -> int:
    scratch_session.add_all([speaker, report])
    scratch_session.flush()
    assert report.id is not None
    speech = Speech(ordinal=_ORDINAL, speaker=label, transcript="Text", sitting_date=report.sitting_date, report_type=report.report_type, report_id=report.id)
    scratch_session.add(speech)
    scratch_session.commit()
    speech_id = speech.id
    assert speech_id is not None
    return speech_id


def test_prime_minister_after_14_may_2024_is_lawrence_wong() -> None:
    terms = DATED_ROLE_TERMS["The Prime Minister"]

    assert _get_holder_on(terms, date(2025, 9, 22)) == [_PRIME_MINISTER]
    assert _get_holder_on(terms, date(2024, 5, 14)) == ["Lee Hsien Loong"]


def test_president_after_13_september_2023_is_tharman() -> None:
    terms = HEAD_OF_STATE_TERMS["The President"]

    assert _get_holder_on(terms, date(2025, 9, 22)) == [_PRESIDENT]
    assert _get_holder_on(terms, date(2023, 9, 13)) == ["Halimah Yacob"]


def test_bare_prime_minister_in_parliament_15_links(scratch_session: Session) -> None:
    speaker = Speaker(name=_PRIME_MINISTER, party="PAP", is_legislative_assembly=False, parliament_number=_PARLIAMENT_NUMBER)
    report = _build_report("prime-minister-report", "MOTION", ReportType.MOTION, datetime(2025, 9, 22))

    speech_id = _seed_one_speech(scratch_session, speaker, report, "The Prime Minister")
    report_id = report.id
    speaker_id = speaker.id
    assert report_id is not None

    link_speakers_by_report_ids_and_sitting_ids(scratch_session, [report_id], [])

    assert scratch_session.exec(select(Speech.speaker_id).where(Speech.id == speech_id)).one() == speaker_id


def test_president_in_the_parliament_15_address_links(scratch_session: Session) -> None:
    speaker = Speaker(
        name=_PRESIDENT,
        party="Non-partisan",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
        is_member=False,
    )
    report = _build_report("president-address-report", "PRESIDENT'S ADDRESS", ReportType.PRESIDENT_ADDRESS, datetime(2025, 9, 5))

    speech_id = _seed_one_speech(scratch_session, speaker, report, "The President")
    report_id = report.id
    speaker_id = speaker.id
    assert report_id is not None

    link_speakers_by_report_ids_and_sitting_ids(scratch_session, [report_id], [])

    assert scratch_session.exec(select(Speech.speaker_id).where(Speech.id == speech_id)).one() == speaker_id


def test_heads_of_state_file_has_the_parliament_15_president() -> None:
    heads_of_state = get_heads_of_state()

    presidents = [head_of_state for head_of_state in heads_of_state if head_of_state.name == _PRESIDENT]

    assert [president.parliament_number for president in presidents].count(_PARLIAMENT_NUMBER) == 1
    assert [president.parliament_number for president in presidents].count(_PREVIOUS_PARLIAMENT_NUMBER) == 0

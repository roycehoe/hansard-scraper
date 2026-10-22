from datetime import datetime

from sqlmodel import Session, select

from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from crud.speech import CRUDSpeech
from database.report import Report
from database.sitting import Sitting
from database.speech import Speech
from enums import ReportType, ReportVersion
from utils.text import TextChange

_PARLIAMENT_NUMBER = 14
_REPORT_ID = "text-change-report"
_SITTING_DATE = datetime(2020, 1, 6)
_SITTING_DATE_KEY = "6-1-2020"
_SPEECH_NUMBER = 1
_BEFORE_TEXT = "Mr TanÃ©"
_AFTER_TEXT = "Mr Tané"
_OTHER_TEXT = "Question put, and agreed to."


def _build_report(markdown_content: str) -> Report:
    return Report(
        volumeNo=_PARLIAMENT_NUMBER,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=_SPEECH_NUMBER,
        original_title=_REPORT_ID,
        title=_REPORT_ID,
        reportId=_REPORT_ID,
        reportType=ReportType.MOTION,
        content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
        markdown_content=markdown_content,
    )


def _build_speech(report_id: int, speaker: str, transcript: str) -> Speech:
    return Speech(ordinal=_SPEECH_NUMBER, speaker=speaker, transcript=transcript, sitting_date=_SITTING_DATE, report_id=report_id)


def test_report_markdown_write_skips_a_row_no_longer_holding_the_before_text(scratch_session: Session) -> None:
    report = _build_report(_BEFORE_TEXT)
    scratch_session.add(report)
    scratch_session.flush()
    text_changes = [TextChange(report.id, _BEFORE_TEXT, _AFTER_TEXT)]

    assert CRUDReport(scratch_session).set_markdown_contents_bulk_by_markdown_content(text_changes) == 1
    assert scratch_session.exec(select(Report.markdown_content)).all() == [_AFTER_TEXT]
    assert CRUDReport(scratch_session).set_markdown_contents_bulk_by_markdown_content(text_changes) == 0
    assert scratch_session.exec(select(Report.markdown_content)).all() == [_AFTER_TEXT]
    assert CRUDReport(scratch_session).set_markdown_contents_bulk_by_markdown_content([]) == 0


def test_sitting_markdown_write_skips_a_row_no_longer_holding_the_before_text(scratch_session: Session) -> None:
    sitting = Sitting(sitting_date=_SITTING_DATE_KEY, markdown_content=_BEFORE_TEXT)
    scratch_session.add(sitting)
    scratch_session.flush()
    text_changes = [TextChange(sitting.id, _BEFORE_TEXT, _AFTER_TEXT)]

    assert CRUDSitting(scratch_session).set_markdown_contents_bulk_by_markdown_content(text_changes) == 1
    assert scratch_session.exec(select(Sitting.markdown_content)).all() == [_AFTER_TEXT]
    assert CRUDSitting(scratch_session).set_markdown_contents_bulk_by_markdown_content(text_changes) == 0
    assert scratch_session.exec(select(Sitting.markdown_content)).all() == [_AFTER_TEXT]
    assert CRUDSitting(scratch_session).set_markdown_contents_bulk_by_markdown_content([]) == 0


def test_speech_label_write_skips_a_row_no_longer_holding_the_before_text(scratch_session: Session) -> None:
    report = _build_report(_OTHER_TEXT)
    scratch_session.add(report)
    scratch_session.flush()
    speech = _build_speech(report.id, _BEFORE_TEXT, _OTHER_TEXT)
    scratch_session.add(speech)
    scratch_session.flush()
    text_changes = [TextChange(speech.id, _BEFORE_TEXT, _AFTER_TEXT)]

    assert CRUDSpeech(scratch_session).set_speakers_bulk_by_speaker(text_changes) == 1
    assert scratch_session.exec(select(Speech.speaker)).all() == [_AFTER_TEXT]
    assert CRUDSpeech(scratch_session).set_speakers_bulk_by_speaker(text_changes) == 0
    assert scratch_session.exec(select(Speech.speaker)).all() == [_AFTER_TEXT]
    assert CRUDSpeech(scratch_session).set_speakers_bulk_by_speaker([]) == 0


def test_speech_transcript_write_skips_a_row_no_longer_holding_the_before_text(scratch_session: Session) -> None:
    report = _build_report(_OTHER_TEXT)
    scratch_session.add(report)
    scratch_session.flush()
    speech = _build_speech(report.id, _OTHER_TEXT, _BEFORE_TEXT)
    scratch_session.add(speech)
    scratch_session.flush()
    text_changes = [TextChange(speech.id, _BEFORE_TEXT, _AFTER_TEXT)]

    assert CRUDSpeech(scratch_session).set_transcripts_bulk_by_transcript(text_changes) == 1
    assert scratch_session.exec(select(Speech.transcript)).all() == [_AFTER_TEXT]
    assert CRUDSpeech(scratch_session).set_transcripts_bulk_by_transcript(text_changes) == 0
    assert scratch_session.exec(select(Speech.transcript)).all() == [_AFTER_TEXT]
    assert CRUDSpeech(scratch_session).set_transcripts_bulk_by_transcript([]) == 0

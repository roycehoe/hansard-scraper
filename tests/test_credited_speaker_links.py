import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import populate.speaker_links as speaker_links_module
import scripts.apply_fresh_parse as apply_fresh_parse_script
import scripts.apply_speaker_links as apply_speaker_links_script
from database.report import Report
from database.speaker import Speaker
from database.speech import Speech
from enums import ReportType, ReportVersion, SpeechKind
from exceptions import HansardUnlabelledSpeechError
from populate.speaker_links import link_speakers_by_report_ids_and_sitting_ids
from schemas.unlabelled_speech import UnlabelledSpeechRange
from services.speech import build_report_speeches
from utils.data_files import get_unlabelled_speech_ranges
from utils.markdown_parser import get_cleaned_report_markdown

_PARLIAMENT_NUMBER = 14
_SITTING_DATE = datetime(2025, 4, 2)
_CHAIR_NAME = "Pritam Singh"
_CHAIR_LABEL = "Mr Pritam Singh"
_CREDITED_NAME = "Louis Chua"
_OPENING_SPEECH_REPORT_ID = 24248
_OPENING_SPEECH_PARLIAMENT_NUMBER = 10
_OPENING_SPEECH_CREDITED_NAME = "Gan Kim Yong"
_RESUMPTION_START = "[_Please refer to Vernacular Speech_.] We have"
_RESUMPTION_END = "Healthy living"
_RESUMPTION_HTML = (
    f"<h6>3.00 pm</h6><p><strong>{_CHAIR_LABEL}</strong>:&nbsp;Please do.</p>"
    "<p>(<em>In Malay</em>)<em>: </em>[<em>Please refer to Vernacular Speech</em>.] "
    "We have been working hard.</p>"
    "<p>Healthy living starts with you and me.</p>"
    f"<p><strong>{_CHAIR_LABEL}</strong>:&nbsp;Thank you.</p>"
)
_RESUMED_ORDINALS = (2, 3)


def _build_speaker(name: str, parliament_number: int = _PARLIAMENT_NUMBER) -> Speaker:
    return Speaker(
        name=name,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=parliament_number,
    )


def _build_report(
    parliament_number: int = _PARLIAMENT_NUMBER, html: Optional[str] = None
) -> Report:
    return Report(
        volumeNo=parliament_number,
        parlNo=parliament_number,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title="report",
        title="report",
        reportId="report",
        reportType=ReportType.MOTION,
        content=html,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
        markdown_content=(
            None
            if html is None
            else get_cleaned_report_markdown(html, ReportVersion.SPRS3)
        ),
    )


def _build_range(
    report: Report,
    *,
    speaker: Optional[str],
    credited_speaker_name: str,
    first_transcript_start: str,
    last_transcript_start: str,
) -> UnlabelledSpeechRange:
    assert report.id is not None
    return UnlabelledSpeechRange(
        report_id=report.id,
        speaker=speaker,
        credited_speaker_name=credited_speaker_name,
        first_transcript_start=first_transcript_start,
        last_transcript_start=last_transcript_start,
        reason="",
    )


def _use_ranges(
    monkeypatch: pytest.MonkeyPatch, speech_ranges: list[UnlabelledSpeechRange]
) -> None:
    monkeypatch.setattr(
        speaker_links_module, "get_unlabelled_speech_ranges", lambda: speech_ranges
    )


def _add_speech(
    scratch_session: Session,
    report: Report,
    ordinal: int,
    transcript: str,
    *,
    kind: SpeechKind = SpeechKind.SPEECH,
    speaker: Optional[str] = None,
) -> None:
    assert report.id is not None
    scratch_session.add(
        Speech(
            ordinal=ordinal,
            speaker=speaker,
            transcript=transcript,
            kind=kind,
            sitting_date=_SITTING_DATE,
            report_type=report.report_type,
            report_id=report.id,
        )
    )


def _get_stored_rows(
    scratch_session: Session, report: Report
) -> list[tuple[int, Optional[str], Optional[int]]]:
    scratch_session.expire_all()
    return [
        (speech.ordinal, speech.speaker, speech.speaker_id)
        for speech in scratch_session.exec(
            select(Speech).where(Speech.report_id == report.id).order_by(Speech.ordinal)
        ).all()
    ]


def _get_speaker_id(scratch_session: Session, speaker: Speaker) -> int:
    assert speaker.id is not None
    return speaker.id


def _link(scratch_session: Session, report: Report) -> None:
    assert report.id is not None
    link_speakers_by_report_ids_and_sitting_ids(scratch_session, [report.id], [])


def test_a_parsed_chair_resumption_is_credited_and_keeps_no_label(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    chair = _build_speaker(_CHAIR_NAME)
    member = _build_speaker(_CREDITED_NAME)
    report = _build_report(html=_RESUMPTION_HTML)
    scratch_session.add_all([chair, member, report])
    scratch_session.flush()
    speech_range = _build_range(
        report,
        speaker=_CHAIR_LABEL,
        credited_speaker_name=_CREDITED_NAME,
        first_transcript_start=_RESUMPTION_START,
        last_transcript_start=_RESUMPTION_END,
    )
    scratch_session.add_all(
        build_report_speeches(report, {report.id: speech_range}).speeches
    )
    scratch_session.commit()
    _use_ranges(monkeypatch, [speech_range])

    _link(scratch_session, report)

    assert _get_stored_rows(scratch_session, report) == [
        (1, _CHAIR_LABEL, chair.id),
        (2, None, member.id),
        (3, None, member.id),
        (4, _CHAIR_LABEL, chair.id),
    ]


def test_an_unlabelled_opening_speech_before_the_first_speaker_is_credited(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _build_speaker(_CREDITED_NAME)
    report = _build_report()
    scratch_session.add_all([member, report])
    scratch_session.flush()
    _add_speech(scratch_session, report, 1, "When I delivered the Budget Speech")
    _add_speech(scratch_session, report, 2, "Mr Deputy Speaker, Sir, I beg to move.")
    scratch_session.commit()
    _use_ranges(
        monkeypatch,
        [
            _build_range(
                report,
                speaker=None,
                credited_speaker_name=_CREDITED_NAME,
                first_transcript_start="When I delivered",
                last_transcript_start="Mr Deputy Speaker, Sir, I beg",
            )
        ],
    )

    _link(scratch_session, report)

    assert _get_stored_rows(scratch_session, report) == [
        (1, None, member.id),
        (2, None, member.id),
    ]


def test_a_held_row_that_opens_with_a_stray_mark_is_credited(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _build_speaker(_CREDITED_NAME)
    report = _build_report()
    scratch_session.add_all([member, report])
    scratch_session.flush()
    _add_speech(
        scratch_session,
        report,
        1,
        "_[_Please refer to Vernacular Speech_.] Mdm Speaker, I learn",
    )
    _add_speech(scratch_session, report, 2, "I hope that the message")
    scratch_session.commit()
    _use_ranges(
        monkeypatch,
        [
            _build_range(
                report,
                speaker=_CHAIR_LABEL,
                credited_speaker_name=_CREDITED_NAME,
                first_transcript_start="[_Please refer to Vernacular Speech_.] Mdm",
                last_transcript_start="I hope that the message",
            )
        ],
    )

    _link(scratch_session, report)

    assert _get_stored_rows(scratch_session, report) == [
        (1, None, member.id),
        (2, None, member.id),
    ]


def test_a_chamber_event_inside_the_range_stays_uncredited(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _build_speaker(_CREDITED_NAME)
    report = _build_report()
    scratch_session.add_all([member, report])
    scratch_session.flush()
    _add_speech(scratch_session, report, 1, "First, look at the data.")
    _add_speech(
        scratch_session,
        report,
        2,
        "[_Applause._]",
        kind=SpeechKind.CHAMBER_EVENT,
    )
    _add_speech(scratch_session, report, 3, "The Motion acknowledges this.")
    scratch_session.commit()
    _use_ranges(
        monkeypatch,
        [
            _build_range(
                report,
                speaker=_CHAIR_LABEL,
                credited_speaker_name=_CREDITED_NAME,
                first_transcript_start="First, look",
                last_transcript_start="The Motion",
            )
        ],
    )

    _link(scratch_session, report)

    assert _get_stored_rows(scratch_session, report) == [
        (1, None, member.id),
        (2, None, None),
        (3, None, member.id),
    ]


def test_a_credited_name_with_no_speaker_in_the_parliament_raises(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_parliament_member = _build_speaker(_CREDITED_NAME, parliament_number=13)
    report = _build_report()
    scratch_session.add_all([other_parliament_member, report])
    scratch_session.flush()
    _add_speech(scratch_session, report, 1, "First, look at the data.")
    scratch_session.commit()
    _use_ranges(
        monkeypatch,
        [
            _build_range(
                report,
                speaker=None,
                credited_speaker_name=_CREDITED_NAME,
                first_transcript_start="First, look",
                last_transcript_start="First, look",
            )
        ],
    )

    with pytest.raises(HansardUnlabelledSpeechError, match=_CREDITED_NAME):
        _link(scratch_session, report)


def test_a_range_with_a_missing_locator_raises(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _build_speaker(_CREDITED_NAME)
    report = _build_report()
    scratch_session.add_all([member, report])
    scratch_session.flush()
    _add_speech(scratch_session, report, 1, "Another text.")
    scratch_session.commit()
    _use_ranges(
        monkeypatch,
        [
            _build_range(
                report,
                speaker=None,
                credited_speaker_name=_CREDITED_NAME,
                first_transcript_start="First, look",
                last_transcript_start="First, look",
            )
        ],
    )

    with pytest.raises(HansardUnlabelledSpeechError):
        _link(scratch_session, report)


def test_the_opening_speech_of_24248_takes_the_member_of_its_own_parliament(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _build_speaker(
        _OPENING_SPEECH_CREDITED_NAME, _OPENING_SPEECH_PARLIAMENT_NUMBER
    )
    later_parliament_member = _build_speaker(
        _OPENING_SPEECH_CREDITED_NAME, _OPENING_SPEECH_PARLIAMENT_NUMBER + 1
    )
    report = _build_report(_OPENING_SPEECH_PARLIAMENT_NUMBER)
    scratch_session.add_all([member, later_parliament_member, report])
    scratch_session.flush()
    stored_range = next(
        speech_range
        for speech_range in get_unlabelled_speech_ranges()
        if speech_range.report_id == _OPENING_SPEECH_REPORT_ID
    )
    assert report.id is not None
    _add_speech(scratch_session, report, 1, stored_range.first_transcript_start)
    _add_speech(scratch_session, report, 2, stored_range.last_transcript_start)
    scratch_session.commit()
    _use_ranges(monkeypatch, [stored_range.model_copy(update={"report_id": report.id})])

    _link(scratch_session, report)

    assert _get_stored_rows(scratch_session, report) == [
        (1, None, member.id),
        (2, None, member.id),
    ]


def test_the_speaker_link_plan_holds_the_credits(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(apply_speaker_links_script, "engine", scratch_engine)
    member = _build_speaker(_CREDITED_NAME)
    report = _build_report()
    scratch_session.add_all([member, report])
    scratch_session.flush()
    _add_speech(scratch_session, report, 1, "First, look at the data.")
    scratch_session.commit()
    _use_ranges(
        monkeypatch,
        [
            _build_range(
                report,
                speaker=None,
                credited_speaker_name=_CREDITED_NAME,
                first_transcript_start="First, look",
                last_transcript_start="First, look",
            )
        ],
    )
    plan_path = tmp_path / "plan.json"

    apply_speaker_links_script.apply_speaker_links(plan_path, is_commit=False)

    stored_speech_id = scratch_session.exec(
        select(Speech.id).where(Speech.report_id == report.id)
    ).one()
    assert json.loads(plan_path.read_text()) == {
        "speech_id_to_speaker_id": {str(stored_speech_id): member.id},
        "attendance_id_to_speaker_id": {},
    }


def test_a_fresh_parse_keeps_the_credit(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(apply_fresh_parse_script, "engine", scratch_engine)
    chair = _build_speaker(_CHAIR_NAME)
    member = _build_speaker(_CREDITED_NAME)
    report = _build_report(html=_RESUMPTION_HTML)
    scratch_session.add_all([chair, member, report])
    scratch_session.flush()
    _add_speech(scratch_session, report, 1, "Stale text.", speaker=_CHAIR_LABEL)
    scratch_session.commit()
    speech_range = _build_range(
        report,
        speaker=_CHAIR_LABEL,
        credited_speaker_name=_CREDITED_NAME,
        first_transcript_start=_RESUMPTION_START,
        last_transcript_start=_RESUMPTION_END,
    )
    _use_ranges(monkeypatch, [speech_range])
    monkeypatch.setattr(
        apply_fresh_parse_script, "get_unlabelled_speech_ranges", lambda: [speech_range]
    )
    plan_path = tmp_path / "plan.json"
    held_path = tmp_path / "held.json"
    held_path.write_text("[]")
    apply_fresh_parse_script.apply_fresh_parse(plan_path, held_path, is_commit=False)

    apply_fresh_parse_script.apply_fresh_parse(plan_path, held_path, is_commit=True)

    assert _get_stored_rows(scratch_session, report) == [
        (1, _CHAIR_LABEL, chair.id),
        (2, None, member.id),
        (3, None, member.id),
        (4, _CHAIR_LABEL, chair.id),
    ]

import json
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

import scripts.apply_attached_files as apply_attached_files_script
from database.attached_file import AttachedFile
from database.attached_file_pointer import AttachedFilePointer
from database.report import Report
from database.sitting import Sitting
from database.speech import Speech
from enums import AttachedFileKind, ReportType, ReportVersion, SpeechKind
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from scripts.apply_attached_files import apply_attached_files

_SITTING_DATE = datetime(2023, 3, 1)
_ANNEX_VALUE = "20230301/annex-Committee of Supply.pdf"
_VERNACULAR_VALUE = "20160816/vernacular-Thomas Chua(4).pdf"
_OTHER_ANNEX_VALUE = "20230302/annex-Other.pdf"
_DOWNLOAD_PATH = "/search/search/download?value="
_FILE_PATH_PREFIX = "d:/apps/reports/solr_files/"
_HAND_EDITED_TEXT = "Hand edited"
_UNLISTED_SPRS_FILE_ID = 9999
_STORED_FILE_COUNT = 3
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_PLAN_LOG = "Plan: 3 files, 3 pointers for 2 reports"
_TIE_LOG = "Pointers that would take a file: 3"
_TIER_LOG = "Paragraph ties by tier: ONLY_OCCURRENCE 3"


@dataclass(frozen=True)
class _Seeded:
    first_sitting: Sitting
    first_report: Report
    second_report: Report


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _get_entry_text(entry: dict) -> str:
    return json.dumps([entry])


def _get_link(value: str, text: str) -> str:
    return f'<a href="{_DOWNLOAD_PATH}{value}">{text}</a>'


def _build_report(report_id: str, content: str) -> Report:
    return Report(
        volumeNo=14,
        parlNo=14,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title="Sample",
        title="Sample",
        reportId=report_id,
        reportType=ReportType.MOTION,
        content=content,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _build_speech(report: Report, ordinal: int, transcript: str) -> Speech:
    assert report.id is not None
    return Speech(
        ordinal=ordinal,
        speaker=None,
        transcript=transcript,
        kind=SpeechKind.SPEECH,
        speaker_id=None,
        sitting_date=_SITTING_DATE,
        report_type=report.report_type,
        report_id=report.id,
    )


def _seed(session: Session) -> _Seeded:
    first_sitting = Sitting(
        parlement_no=14,
        sitting_date="1-3-2023",
        annexures=_get_entry_text(
            {
                "annexureID": 4101,
                "annexureTitle": "Annex to the debate",
                "filePath": f"{_FILE_PATH_PREFIX}{_ANNEX_VALUE}",
                "fileName": "annex-Committee of Supply.pdf",
                "sectionType": "OS",
            }
        ),
        vernaculars=_get_entry_text(
            {
                "vernacularID": 8201,
                "vernacularTitle": "Vernacular Speech by Mr Thomas Chua",
                "filePath": f"{_FILE_PATH_PREFIX}{_VERNACULAR_VALUE}",
                "fileName": "vernacular-Thomas Chua(4).pdf",
            }
        ),
    )
    second_sitting = Sitting(
        parlement_no=14,
        sitting_date="2-3-2023",
        annexures=_get_entry_text(
            {
                "annexureID": 4102,
                "annexureTitle": "Other annex",
                "filePath": f"{_FILE_PATH_PREFIX}{_OTHER_ANNEX_VALUE}",
                "fileName": "annex-Other.pdf",
                "sectionType": "OS",
            }
        ),
    )
    first_report = _build_report(
        "first#",
        f"<p>Please see {_get_link(_ANNEX_VALUE, 'Annex A')} here.</p>"
        f"<p>{_get_link(_VERNACULAR_VALUE, 'Vernacular Speech')}</p>",
    )
    second_report = _build_report(
        "second#", f"<p>{_get_link(_OTHER_ANNEX_VALUE, 'Other Annex')}</p>"
    )
    session.add_all([first_sitting, second_sitting, first_report, second_report])
    session.flush()
    session.add_all(
        [
            _build_speech(first_report, 1, "Please see Annex A here."),
            _build_speech(first_report, 2, "Vernacular Speech"),
            _build_speech(second_report, 1, "Other Annex"),
        ]
    )
    session.commit()
    return _Seeded(first_sitting, first_report, second_report)


def _get_stored_pointers(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (
            pointer.sprs_report_id,
            pointer.ordinal,
            pointer.speech_ordinal,
            pointer.attached_file_id is not None,
        )
        for pointer in session.exec(
            select(AttachedFilePointer).order_by(
                col(AttachedFilePointer.sprs_report_id),
                col(AttachedFilePointer.ordinal),
            )
        ).all()
    ]


def _get_stored_file_count(session: Session) -> int:
    session.expire_all()
    return len(session.exec(select(AttachedFile)).all())


def _get_row_dumps(session: Session) -> list[dict]:
    session.expire_all()
    return [
        row.model_dump()
        for row in [
            *session.exec(select(Report).order_by(col(Report.id))).all(),
            *session.exec(select(Speech).order_by(col(Speech.id))).all(),
        ]
    ]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_attached_files_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_attached_files_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed(scratch_session)

    apply_attached_files([], is_commit=False)

    assert "Files by kind: ANNEX 2, VERNACULAR 1" in log_recorder.messages
    assert "Pointers by shape: DATED 3" in log_recorder.messages
    assert _TIER_LOG in log_recorder.messages
    assert _TIE_LOG in log_recorder.messages
    assert "Pointers with an address and no file: 0" in log_recorder.messages
    assert "Pointers with no address: 0" in log_recorder.messages
    assert "Links with a bad href in the reports read: 0" in log_recorder.messages
    assert "Stale paragraph ties: 0" in log_recorder.messages
    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_stored_file_count(scratch_session) == 0
    assert _get_stored_pointers(scratch_session) == []


def test_commit_writes_and_a_second_commit_logs_the_same_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed(scratch_session)

    apply_attached_files([], is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    assert _get_stored_file_count(scratch_session) == _STORED_FILE_COUNT
    stored_pointers = _get_stored_pointers(scratch_session)
    assert stored_pointers == [
        ("first#", 1, 1, True),
        ("first#", 2, 2, True),
        ("second#", 1, 1, True),
    ]
    first_run_messages = list(log_recorder.messages)
    log_recorder.messages.clear()

    apply_attached_files([], is_commit=True)

    assert log_recorder.messages == first_run_messages
    assert _get_stored_file_count(scratch_session) == _STORED_FILE_COUNT
    assert _get_stored_pointers(scratch_session) == stored_pointers


def test_report_ids_limit_the_plan_and_leave_other_sittings_files_alone(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded = _seed(scratch_session)
    apply_attached_files([], is_commit=True)
    second_pointer = scratch_session.exec(
        select(AttachedFilePointer).where(
            AttachedFilePointer.sprs_report_id == "second#"
        )
    ).one()
    second_pointer.printed_text = _HAND_EDITED_TEXT
    scratch_session.commit()
    assert seeded.first_report.id is not None

    apply_attached_files([seeded.first_report.id], is_commit=True)

    assert "Plan: 0 files, 2 pointers for 1 reports" in log_recorder.messages
    assert _get_stored_file_count(scratch_session) == _STORED_FILE_COUNT
    scratch_session.expire_all()
    assert (
        scratch_session.exec(
            select(AttachedFilePointer.printed_text).where(
                AttachedFilePointer.sprs_report_id == "second#"
            )
        ).one()
        == _HAND_EDITED_TEXT
    )


def test_commit_repairs_the_speech_ordinal_after_a_report_is_renumbered(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded = _seed(scratch_session)
    apply_attached_files([], is_commit=True)
    assert seeded.first_report.id is not None
    speeches = scratch_session.exec(
        select(Speech)
        .where(Speech.report_id == seeded.first_report.id)
        .order_by(col(Speech.ordinal).desc())
    ).all()
    for speech in speeches:
        speech.ordinal += 1
        scratch_session.flush()
    scratch_session.add(_build_speech(seeded.first_report, 1, "An added opening."))
    scratch_session.commit()

    apply_attached_files([], is_commit=True)

    assert _get_stored_pointers(scratch_session) == [
        ("first#", 1, 2, True),
        ("first#", 2, 3, True),
        ("second#", 1, 1, True),
    ]


def test_commit_leaves_every_speech_and_report_row_equal(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed(scratch_session)
    row_dumps_before = _get_row_dumps(scratch_session)

    apply_attached_files([], is_commit=True)

    assert _get_row_dumps(scratch_session) == row_dumps_before


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(scratch_session)
    monkeypatch.setattr(
        apply_attached_files_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_attached_files([], is_commit=True)

    assert _get_stored_file_count(scratch_session) == 0
    assert _get_stored_pointers(scratch_session) == []


def test_commit_refuses_a_stored_file_outside_the_plan(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded = _seed(scratch_session)
    apply_attached_files([], is_commit=True)
    assert seeded.first_sitting.id is not None
    scratch_session.add(
        AttachedFile(
            kind=AttachedFileKind.ANNEX,
            sprs_file_id=_UNLISTED_SPRS_FILE_ID,
            printed_title="Not listed",
            printed_file_path=f"{_FILE_PATH_PREFIX}20230301/annex-gone.pdf",
            file_name="annex-gone.pdf",
            download_value="20230301/annex-gone.pdf",
            sitting_id=seeded.first_sitting.id,
        )
    )
    scratch_session.commit()

    with pytest.raises(HansardWriteCheckError, match="is not in the plan"):
        apply_attached_files([], is_commit=True)

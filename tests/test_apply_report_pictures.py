import base64
import hashlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

import scripts.apply_report_pictures as apply_report_pictures_script
from database.report import Report
from database.report_picture import ReportPicture
from enums import PictureKind, ReportType, ReportVersion
from exceptions import HansardReportPictureError, HansardWriteTargetError
from schemas.report_picture_plan import (
    PlannedReportPicture,
    ReportPicturePlan,
    TypedCopy,
    TypedTable,
)
from scripts.apply_report_pictures import apply_report_pictures
from services.report_picture import get_inline_pictures

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_SITTING_DATE = datetime(2023, 3, 1)
_TABLE_BYTES = b"a table picture"
_CHART_BYTES = b"a chart picture"
_TABLE_COPY = TypedCopy(
    heading="",
    tables=[
        TypedTable(
            caption="Table 1: Cases",
            header_rows=[["Year", "Cases"]],
            body_rows=[["2022", "23,404"], ["Total", "23,404"]],
            notes=["^1 Provisional"],
        )
    ],
    uncertain=[],
    note="",
)


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_report_pictures_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_report_pictures_script, "logger", recorder)
    return recorder


def _build_image_tag(picture_bytes: bytes, media_type: str) -> str:
    encoded_picture = base64.b64encode(picture_bytes).decode()
    return f'<img alt="" src="data:{media_type};base64,{encoded_picture}" />'


def _build_content() -> str:
    return (
        "<p>The figures are in the table below.</p>"
        + _build_image_tag(_TABLE_BYTES, "image/png")
        + '<p>A logo <img src="https://example.test/logo.png"></p>'
        + _build_image_tag(_CHART_BYTES, "image/jpeg")
    )


def _add_report(session: Session, content: str) -> int:
    report = Report(
        volumeNo=14,
        parlNo=14,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title="Sample",
        title="Sample",
        reportId="written-answer-1#",
        reportType=ReportType.WRITTEN_ANSWER,
        content=content,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )
    session.add(report)
    session.commit()
    assert report.id is not None
    return report.id


def _build_plan(report_id: int, table_copy: TypedCopy) -> ReportPicturePlan:
    content = _build_content()
    return ReportPicturePlan(
        pictures=[
            PlannedReportPicture(
                report_id=report_id,
                picture_index=0,
                content_offset=content.index("<img"),
                follows_ordinal=1,
                media_type="image/png",
                sha256=hashlib.sha256(_TABLE_BYTES).hexdigest(),
                kind=PictureKind.TABLE,
                typed_copy=table_copy,
            ),
            PlannedReportPicture(
                report_id=report_id,
                picture_index=1,
                content_offset=content.rindex("<img"),
                follows_ordinal=2,
                media_type="image/jpeg",
                sha256=hashlib.sha256(_CHART_BYTES).hexdigest(),
                kind=PictureKind.OTHER,
                typed_copy=None,
            ),
        ]
    )


def _write_plan(path: Path, plan: ReportPicturePlan) -> Path:
    path.write_text(plan.model_dump_json(indent=1), encoding="utf8")
    return path


def _get_stored_pictures(session: Session) -> list[ReportPicture]:
    session.expire_all()
    statement = select(ReportPicture).order_by(col(ReportPicture.picture_index))
    return list(session.exec(statement).all())


def test_get_inline_pictures_skips_a_linked_image_and_keeps_offsets() -> None:
    content = _build_content()

    inline_pictures = get_inline_pictures(content)

    assert [inline_picture.picture_bytes for inline_picture in inline_pictures] == [
        _TABLE_BYTES,
        _CHART_BYTES,
    ]
    assert [inline_picture.media_type for inline_picture in inline_pictures] == [
        "image/png",
        "image/jpeg",
    ]
    assert [inline_picture.content_offset for inline_picture in inline_pictures] == [
        content.index("<img"),
        content.rindex("<img"),
    ]


def test_get_inline_pictures_reads_base64_split_across_lines() -> None:
    encoded_picture = base64.b64encode(_TABLE_BYTES).decode()
    content = f"<IMG SRC='data:image/PNG;base64,{encoded_picture[:8]}\n{encoded_picture[8:]}'>"

    inline_pictures = get_inline_pictures(content)

    assert inline_pictures[0].picture_bytes == _TABLE_BYTES
    assert inline_pictures[0].media_type == "image/png"


def test_dry_run_logs_the_counts_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    report_id = _add_report(scratch_session, _build_content())
    plan_path = _write_plan(tmp_path / "plan.json", _build_plan(report_id, _TABLE_COPY))

    apply_report_pictures(plan_path, is_commit=False)

    assert log_recorder.messages == [
        "Pictures by kind: OTHER 1, TABLE 1",
        "Plan: 2 pictures in 1 reports",
        "Rows already stored: 0; to insert: 2; to update: 0; to delete: 0",
        "Dry run: nothing written",
    ]
    assert _get_stored_pictures(scratch_session) == []


def test_commit_stores_the_bytes_and_a_second_commit_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    report_id = _add_report(scratch_session, _build_content())
    plan_path = _write_plan(tmp_path / "plan.json", _build_plan(report_id, _TABLE_COPY))

    apply_report_pictures(plan_path, is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    stored_pictures = _get_stored_pictures(scratch_session)
    assert [stored_picture.picture_bytes for stored_picture in stored_pictures] == [
        _TABLE_BYTES,
        _CHART_BYTES,
    ]
    assert stored_pictures[0].size_bytes == len(_TABLE_BYTES)
    assert stored_pictures[0].typed_copy == _TABLE_COPY.model_dump()
    assert stored_pictures[1].typed_copy is None
    stored_ids = [stored_picture.id for stored_picture in stored_pictures]
    log_recorder.messages.clear()

    apply_report_pictures(plan_path, is_commit=True)

    assert (
        "Rows already stored: 2; to insert: 0; to update: 0; to delete: 0"
        in log_recorder.messages
    )
    assert [
        stored_picture.id for stored_picture in _get_stored_pictures(scratch_session)
    ] == stored_ids


def test_commit_updates_a_changed_copy_and_deletes_a_picture_the_plan_dropped(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    report_id = _add_report(scratch_session, _build_content())
    apply_report_pictures(
        _write_plan(tmp_path / "plan.json", _build_plan(report_id, _TABLE_COPY)),
        is_commit=True,
    )
    table_row_id = _get_stored_pictures(scratch_session)[0].id
    changed_copy = _TABLE_COPY.model_copy(
        update={"note": "The total is printed twice."}
    )
    changed_plan = _build_plan(report_id, changed_copy)
    log_recorder.messages.clear()

    apply_report_pictures(
        _write_plan(
            tmp_path / "changed.json",
            ReportPicturePlan(pictures=changed_plan.pictures[:1]),
        ),
        is_commit=True,
    )

    assert (
        "Rows already stored: 2; to insert: 0; to update: 1; to delete: 1"
        in log_recorder.messages
    )
    stored_pictures = _get_stored_pictures(scratch_session)
    assert [stored_picture.id for stored_picture in stored_pictures] == [table_row_id]
    assert stored_pictures[0].typed_copy == changed_copy.model_dump()


def test_a_picture_whose_sha256_differs_from_the_plan_raises(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    report_id = _add_report(scratch_session, _build_content())
    plan = _build_plan(report_id, _TABLE_COPY)
    changed_picture = plan.pictures[0].model_copy(update={"sha256": "0" * 64})
    plan_path = _write_plan(
        tmp_path / "plan.json",
        ReportPicturePlan(pictures=[changed_picture, plan.pictures[1]]),
    )

    with pytest.raises(HansardReportPictureError, match="has SHA-256"):
        apply_report_pictures(plan_path, is_commit=True)

    assert _get_stored_pictures(scratch_session) == []


def test_a_table_with_no_typed_copy_raises(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    report_id = _add_report(scratch_session, _build_content())
    plan = _build_plan(report_id, _TABLE_COPY)
    changed_picture = plan.pictures[0].model_copy(update={"typed_copy": None})
    plan_path = _write_plan(
        tmp_path / "plan.json",
        ReportPicturePlan(pictures=[changed_picture, plan.pictures[1]]),
    )

    with pytest.raises(HansardReportPictureError, match="has no typed copy"):
        apply_report_pictures(plan_path, is_commit=False)


def test_a_report_the_database_lacks_raises(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    report_id = _add_report(scratch_session, _build_content())
    plan_path = _write_plan(
        tmp_path / "plan.json", _build_plan(report_id + 1, _TABLE_COPY)
    )

    with pytest.raises(HansardReportPictureError, match="are not stored"):
        apply_report_pictures(plan_path, is_commit=False)


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_id = _add_report(scratch_session, _build_content())
    plan_path = _write_plan(tmp_path / "plan.json", _build_plan(report_id, _TABLE_COPY))
    monkeypatch.setattr(
        apply_report_pictures_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_report_pictures(plan_path, is_commit=True)

    assert _get_stored_pictures(scratch_session) == []

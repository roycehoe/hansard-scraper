import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, col, select

from crud.attached_file_pointer import CRUDAttachedFilePointer
from database.attached_file import AttachedFile
from database.attached_file_pointer import AttachedFilePointer
from database.report import Report
from database.sitting import Sitting
from database.speech import Speech
from enums import (
    AttachedFileKind,
    AttachedFilePointerShape,
    ParagraphTieRule,
    ReportType,
    ReportVersion,
    SpeechKind,
)
from exceptions import HansardAttachedFileError, HansardWriteCheckError
from populate.attached_files import (
    get_attached_file_plan,
    get_planned_file_tie_count,
    get_stale_paragraph_tie_count,
    populate_attached_files,
    write_attached_file_plan,
)
from utils.attached_file_tie import AttachedFilePointerTie

_SITTING_DATE = datetime(2023, 3, 1)
_ANNEX_VALUE = "20230301/annex-Committee of Supply.pdf"
_VERNACULAR_VALUE = "20160816/vernacular-Thomas Chua(4).pdf"
_OTHER_ANNEX_VALUE = "20230302/annex-Other.pdf"
_DOWNLOAD_PATH = "/search/search/download?value="
_FILE_PATH_PREFIX = "d:/apps/reports/solr_files/"
_HAND_EDITED_TEXT = "Hand edited"
_ANNEX_LIST_ID = 4101


@dataclass(frozen=True)
class _Seeded:
    first_sitting: Sitting
    second_sitting: Sitting
    first_report: Report
    second_report: Report


def _get_list_text(entries: list[dict]) -> str:
    return json.dumps(entries)


def _get_annex_entry(annexure_id: int, value: str, title: str) -> dict:
    return {
        "annexureID": annexure_id,
        "annexureTitle": title,
        "filePath": f"{_FILE_PATH_PREFIX}{value}",
        "fileName": value.split("/")[-1],
        "sectionType": "OS",
    }


def _get_vernacular_entry(vernacular_id: int, value: str) -> dict:
    return {
        "vernacularID": vernacular_id,
        "vernacularTitle": "Vernacular Speech by Mr Thomas Chua",
        "filePath": f"{_FILE_PATH_PREFIX}{value}",
        "fileName": value.split("/")[-1],
    }


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
        annexures=_get_list_text(
            [_get_annex_entry(_ANNEX_LIST_ID, _ANNEX_VALUE, "Annex to the debate")]
        ),
        vernaculars=_get_list_text([_get_vernacular_entry(8201, _VERNACULAR_VALUE)]),
    )
    second_sitting = Sitting(
        parlement_no=14,
        sitting_date="2-3-2023",
        annexures=_get_list_text(
            [_get_annex_entry(4102, _OTHER_ANNEX_VALUE, "Other annex")]
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
    return _Seeded(first_sitting, second_sitting, first_report, second_report)


def _get_ids(seeded: _Seeded) -> tuple[list[int], list[int]]:
    assert seeded.first_sitting.id is not None
    assert seeded.second_sitting.id is not None
    assert seeded.first_report.id is not None
    assert seeded.second_report.id is not None
    return (
        [seeded.first_report.id, seeded.second_report.id],
        [seeded.first_sitting.id, seeded.second_sitting.id],
    )


def _write_full_plan(session: Session, seeded: _Seeded) -> None:
    report_ids, sitting_ids = _get_ids(seeded)
    plan = get_attached_file_plan(session, report_ids, sitting_ids)
    write_attached_file_plan(session, plan, is_every_sitting=True)
    session.commit()


def _get_stored_pointers(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (
            pointer.sprs_report_id,
            pointer.ordinal,
            pointer.speech_ordinal,
            pointer.paragraph_tie_rule,
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


@contextmanager
def _record_statements(engine: Engine) -> Iterator[list[str]]:
    statements: list[str] = []

    def record_statement(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)


def _get_writing_statements(statements: list[str]) -> list[str]:
    return [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]


def test_plan_builds_the_expected_rows_and_counts(scratch_session: Session) -> None:
    seeded = _seed(scratch_session)
    report_ids, sitting_ids = _get_ids(seeded)

    plan = get_attached_file_plan(scratch_session, report_ids, sitting_ids)

    assert plan.sprs_report_ids == ["first#", "second#"]
    assert len(plan.attached_files) == len(sitting_ids) + 1
    assert len(plan.attached_file_pointers) == len(plan.attached_files)
    assert plan.counts.kind_to_row_count == {
        AttachedFileKind.ANNEX: 2,
        AttachedFileKind.VERNACULAR: 1,
    }
    assert plan.counts.shape_to_row_count == {AttachedFilePointerShape.DATED: 3}
    assert plan.counts.tie_rule_to_row_count == {ParagraphTieRule.ONLY_OCCURRENCE: 3}
    assert plan.counts.pointers_without_address == 0
    assert plan.counts.bad_file_links == 0


def test_write_stores_the_files_and_pointers_and_ties_them(
    scratch_session: Session,
) -> None:
    seeded = _seed(scratch_session)

    _write_full_plan(scratch_session, seeded)

    assert (
        _get_stored_file_count(scratch_session)
        == len(scratch_session.exec(select(Sitting)).all()) + 1
    )
    assert _get_stored_pointers(scratch_session) == [
        ("first#", 1, 1, ParagraphTieRule.ONLY_OCCURRENCE, True),
        ("first#", 2, 2, ParagraphTieRule.ONLY_OCCURRENCE, True),
        ("second#", 1, 1, ParagraphTieRule.ONLY_OCCURRENCE, True),
    ]


def test_a_second_write_issues_no_insert_update_or_delete(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    seeded = _seed(scratch_session)
    _write_full_plan(scratch_session, seeded)
    report_ids, sitting_ids = _get_ids(seeded)

    with _record_statements(scratch_engine) as statements:
        plan = get_attached_file_plan(scratch_session, report_ids, sitting_ids)
        write_attached_file_plan(scratch_session, plan, is_every_sitting=True)
        scratch_session.commit()

    assert _get_writing_statements(statements) == []


def test_a_write_that_ties_nothing_refuses(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed(scratch_session)
    report_ids, sitting_ids = _get_ids(seeded)
    plan = get_attached_file_plan(scratch_session, report_ids, sitting_ids)

    def set_nothing(
        self: CRUDAttachedFilePointer, ties: list[AttachedFilePointerTie]
    ) -> int:
        return 0

    monkeypatch.setattr(
        CRUDAttachedFilePointer, "set_attached_file_ids_bulk", set_nothing
    )

    with pytest.raises(HansardWriteCheckError, match="hold a file"):
        write_attached_file_plan(scratch_session, plan, is_every_sitting=True)


def test_a_list_that_cannot_be_read_names_the_sitting_and_the_list(
    scratch_session: Session,
) -> None:
    seeded = _seed(scratch_session)
    assert seeded.first_sitting.id is not None
    seeded.first_sitting.annexures = _get_list_text(
        [{"annexureID": 1, "annexureTitle": "No path", "fileName": "a.pdf"}]
    )
    scratch_session.commit()

    with pytest.raises(
        HansardAttachedFileError,
        match=f"Sitting id {seeded.first_sitting.id}: annexureList",
    ):
        get_attached_file_plan(scratch_session, [], [seeded.first_sitting.id])


def test_two_files_with_one_address_leave_the_pointer_untied(
    scratch_session: Session,
) -> None:
    seeded = _seed(scratch_session)
    third_sitting = Sitting(
        parlement_no=14,
        sitting_date="3-3-2023",
        annexures=_get_list_text(
            [_get_annex_entry(4103, _ANNEX_VALUE, "The same address again")]
        ),
    )
    scratch_session.add(third_sitting)
    scratch_session.commit()
    assert seeded.first_report.id is not None
    assert seeded.first_sitting.id is not None
    assert third_sitting.id is not None

    plan = get_attached_file_plan(
        scratch_session,
        [seeded.first_report.id],
        [seeded.first_sitting.id, third_sitting.id],
    )
    write_attached_file_plan(scratch_session, plan, is_every_sitting=True)
    scratch_session.commit()

    assert _get_stored_pointers(scratch_session) == [
        ("first#", 1, 1, ParagraphTieRule.ONLY_OCCURRENCE, False),
        ("first#", 2, 2, ParagraphTieRule.ONLY_OCCURRENCE, True),
    ]


def test_a_limited_plan_on_one_report_leaves_other_sittings_alone(
    scratch_session: Session,
) -> None:
    seeded = _seed(scratch_session)
    _write_full_plan(scratch_session, seeded)
    stored_file_count = _get_stored_file_count(scratch_session)
    second_pointer = scratch_session.exec(
        select(AttachedFilePointer).where(
            AttachedFilePointer.sprs_report_id == "second#"
        )
    ).one()
    second_pointer.printed_text = _HAND_EDITED_TEXT
    scratch_session.commit()
    assert seeded.first_report.id is not None

    plan = get_attached_file_plan(scratch_session, [seeded.first_report.id], [])
    write_attached_file_plan(scratch_session, plan, is_every_sitting=False)
    scratch_session.commit()

    assert _get_stored_file_count(scratch_session) == stored_file_count
    scratch_session.expire_all()
    assert (
        scratch_session.exec(
            select(AttachedFilePointer.printed_text).where(
                AttachedFilePointer.sprs_report_id == "second#"
            )
        ).one()
        == _HAND_EDITED_TEXT
    )


def test_a_report_that_loses_its_links_has_its_old_pointers_cleared(
    scratch_session: Session,
) -> None:
    seeded = _seed(scratch_session)
    _write_full_plan(scratch_session, seeded)
    seeded.second_report.content = "<p>No links now.</p>"
    scratch_session.commit()
    report_ids, sitting_ids = _get_ids(seeded)

    plan = get_attached_file_plan(scratch_session, report_ids, sitting_ids)
    write_attached_file_plan(scratch_session, plan, is_every_sitting=True)
    scratch_session.commit()

    assert "second#" in plan.sprs_report_ids
    assert [pointer[0] for pointer in _get_stored_pointers(scratch_session)] == [
        "first#",
        "first#",
    ]


def _validate_write_refuses_a_changed_stored_file(
    session: Session, seeded: _Seeded
) -> None:
    report_ids, sitting_ids = _get_ids(seeded)
    plan = get_attached_file_plan(session, report_ids, sitting_ids)

    with pytest.raises(HansardWriteCheckError, match="differs from the plan"):
        write_attached_file_plan(session, plan, is_every_sitting=True)


def test_a_stored_file_with_another_download_value_refuses(
    scratch_session: Session,
) -> None:
    seeded = _seed(scratch_session)
    _write_full_plan(scratch_session, seeded)
    stored_file = scratch_session.exec(
        select(AttachedFile).where(AttachedFile.sprs_file_id == _ANNEX_LIST_ID)
    ).one()
    stored_file.download_value = "20230301/annex-changed.pdf"
    scratch_session.commit()

    _validate_write_refuses_a_changed_stored_file(scratch_session, seeded)


def test_a_stored_file_with_another_title_refuses(scratch_session: Session) -> None:
    seeded = _seed(scratch_session)
    _write_full_plan(scratch_session, seeded)
    stored_file = scratch_session.exec(
        select(AttachedFile).where(AttachedFile.sprs_file_id == _ANNEX_LIST_ID)
    ).one()
    stored_file.printed_title = "Changed title"
    scratch_session.commit()

    _validate_write_refuses_a_changed_stored_file(scratch_session, seeded)


def test_a_stored_file_outside_the_plan_refuses(scratch_session: Session) -> None:
    seeded = _seed(scratch_session)
    _write_full_plan(scratch_session, seeded)
    assert seeded.first_report.id is not None
    assert seeded.first_sitting.id is not None
    plan = get_attached_file_plan(
        scratch_session, [seeded.first_report.id], [seeded.first_sitting.id]
    )

    with pytest.raises(HansardWriteCheckError, match="is not in the plan"):
        write_attached_file_plan(scratch_session, plan, is_every_sitting=True)


def test_populate_inserts_the_rows_of_new_reports_and_issues_no_delete(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    seeded = _seed(scratch_session)
    report_ids, sitting_ids = _get_ids(seeded)

    with _record_statements(scratch_engine) as statements:
        populate_attached_files(scratch_session, report_ids, sitting_ids)
        scratch_session.commit()

    assert [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("DELETE")
    ] == []
    assert any(
        statement.startswith("INSERT INTO attached_file_pointer")
        for statement in statements
    )
    assert [pointer[4] for pointer in _get_stored_pointers(scratch_session)] == [
        True,
        True,
        True,
    ]


def test_planned_file_tie_count_is_the_same_on_a_full_and_a_limited_plan(
    scratch_session: Session,
) -> None:
    seeded = _seed(scratch_session)
    _write_full_plan(scratch_session, seeded)
    report_ids, sitting_ids = _get_ids(seeded)

    full_plan = get_attached_file_plan(scratch_session, report_ids, sitting_ids)
    limited_plan = get_attached_file_plan(scratch_session, report_ids, [])

    assert get_planned_file_tie_count(
        scratch_session, full_plan, is_every_sitting=True
    ) == get_planned_file_tie_count(
        scratch_session, limited_plan, is_every_sitting=False
    )
    assert get_planned_file_tie_count(
        scratch_session, full_plan, is_every_sitting=True
    ) == len(full_plan.attached_file_pointers)


def test_stale_paragraph_ties_are_counted(scratch_session: Session) -> None:
    seeded = _seed(scratch_session)
    _write_full_plan(scratch_session, seeded)
    report_ids, _ = _get_ids(seeded)
    assert get_stale_paragraph_tie_count(scratch_session, report_ids) == 0

    speech = scratch_session.exec(
        select(Speech).where(
            Speech.report_id == seeded.second_report.id, Speech.ordinal == 1
        )
    ).one()
    speech.transcript = "Different words."
    scratch_session.commit()

    assert get_stale_paragraph_tie_count(scratch_session, report_ids) == 1

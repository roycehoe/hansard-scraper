from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.copy_sitting_lists_to_raw as copy_sitting_lists_to_raw_script
from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.sitting import Sitting

_NEWER_DATE = "10-9-2012"
_OLDER_DATE = "22-10-2007"
_KEPT_DATE = "11-9-2012"
_SECTIONS = '[{"title": "Prayers"}]'
_ANNEXURES = "[]"
_VERNACULARS = '[{"vernacularID": 7}]'
_A2B = '[{"billTitle": "A Bill"}]'
_KEPT_SECTIONS = '[{"title": "Raw copy"}]'


def _use_scratch(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(copy_sitting_lists_to_raw_script, "engine", scratch_engine)


def _add_pair(
    session: Session,
    sitting_date: str,
    sitting_sections: Optional[str],
    raw_sections: Optional[str] = None,
) -> None:
    has_lists = sitting_sections is not None
    session.add(
        Sitting(
            sitting_date=sitting_date,
            sections=sitting_sections,
            annexures=_ANNEXURES if has_lists else None,
            vernaculars=_VERNACULARS if has_lists else None,
            a2b=_A2B if has_lists else None,
        )
    )
    session.add(
        HansardSittingDateResponse(sitting_date=sitting_date, sections=raw_sections)
    )
    session.commit()


def _get_raw_lists(
    session: Session,
) -> dict[str, tuple[Optional[str], ...]]:
    session.expire_all()
    return {
        raw.sitting_date: (raw.sections, raw.annexures, raw.vernaculars, raw.a2b)
        for raw in session.exec(select(HansardSittingDateResponse)).all()
        if raw.sitting_date is not None
    }


def test_fill_counts_name_the_raw_rows_each_list_would_fill(
    scratch_session: Session,
) -> None:
    _add_pair(scratch_session, _NEWER_DATE, _SECTIONS)
    _add_pair(scratch_session, _OLDER_DATE, None)

    counts = CRUDHansardSittingDateResponse(
        scratch_session
    ).get_fill_counts_by_sitting_sitting_date_and_lists_null()

    assert (
        counts.rows,
        counts.sections,
        counts.annexures,
        counts.vernaculars,
        counts.a2b,
    ) == (1, 1, 1, 1, 1)


def test_dry_run_counts_and_writes_nothing(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _add_pair(scratch_session, _NEWER_DATE, _SECTIONS)

    copy_sitting_lists_to_raw_script.copy_sitting_lists_to_raw(False)

    assert _get_raw_lists(scratch_session) == {_NEWER_DATE: (None, None, None, None)}


def test_commit_fills_a_newer_row_leaves_an_older_row_empty_and_keeps_a_filled_column(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _add_pair(scratch_session, _NEWER_DATE, _SECTIONS)
    _add_pair(scratch_session, _OLDER_DATE, None)
    _add_pair(scratch_session, _KEPT_DATE, _SECTIONS, raw_sections=_KEPT_SECTIONS)

    copy_sitting_lists_to_raw_script.copy_sitting_lists_to_raw(True)

    assert _get_raw_lists(scratch_session) == {
        _NEWER_DATE: (_SECTIONS, _ANNEXURES, _VERNACULARS, _A2B),
        _OLDER_DATE: (None, None, None, None),
        _KEPT_DATE: (_KEPT_SECTIONS, _ANNEXURES, _VERNACULARS, _A2B),
    }


def test_second_commit_writes_no_rows(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _add_pair(scratch_session, _NEWER_DATE, _SECTIONS)
    copy_sitting_lists_to_raw_script.copy_sitting_lists_to_raw(True)

    written = CRUDHansardSittingDateResponse(
        scratch_session
    ).set_sections_annexures_vernaculars_and_a2b_from_sitting_by_sitting_date()

    assert written == 0

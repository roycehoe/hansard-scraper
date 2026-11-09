import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.check_office_ranges_against_ministers as check_script
from crud.office_printed_range import OfficePrintedRangeRow
from database.attendance import Attendance
from database.attendance_office import AttendanceOffice
from database.ministry import Ministry
from database.office_printed_range import OfficePrintedRange
from database.office_title_ministry import OfficeTitleMinistry
from database.sitting import Sitting
from database.speaker import Speaker
from enums import (
    AttendanceOfficeSource,
    OfficeCheckFlagKind,
    OfficeClass,
    OfficeTitleMinistrySource,
)
from exceptions import HansardOfficeCheckError
from schemas.office_check_minister import OfficeCheckMinister
from scripts.check_office_ranges_against_ministers import (
    check_office_ranges_against_ministers,
    get_office_check_flags,
)

_MEMBER_NAME = "Test Member"
_SOURCE_URL = "https://example.org/minister"
_HEALTH_MINISTRY = "Health"
_HEALTH_TITLE = "Minister for Health"
_OTHER_TITLE = "Minister for Defence"
_START_DATE = date(2000, 1, 1)
_END_DATE = date(2005, 12, 31)
_SPEAKER_ID = 7
_MINISTER = OfficeCheckMinister(
    member_name=_MEMBER_NAME,
    speaker_ids=[_SPEAKER_ID],
    ministry_name=_HEALTH_MINISTRY,
    start_date=_START_DATE,
    end_date=_END_DATE,
    source_url=_SOURCE_URL,
)
_TITLES_IN_MINISTRY = {_HEALTH_TITLE}
_RANGE_ID = 1
_SITTING_COUNT = 3


def _build_range_row(
    first_sitting_date: date, last_sitting_date: date, office_printed: str = _HEALTH_TITLE
) -> OfficePrintedRangeRow:
    return OfficePrintedRangeRow(
        _RANGE_ID,
        _SPEAKER_ID,
        office_printed,
        _SITTING_COUNT,
        datetime.combine(first_sitting_date, datetime.min.time()),
        datetime.combine(last_sitting_date, datetime.min.time()),
    )


def _get_kinds(range_rows: list[OfficePrintedRangeRow]) -> list[OfficeCheckFlagKind]:
    return [
        flag.kind
        for flag in get_office_check_flags(_MINISTER, range_rows, _TITLES_IN_MINISTRY)
    ]


def test_a_range_inside_the_dates_gives_no_flag() -> None:
    assert _get_kinds([_build_range_row(date(2001, 1, 1), date(2004, 1, 1))]) == []


def test_a_range_straddling_the_start_gives_one_outside_flag() -> None:
    assert _get_kinds([_build_range_row(date(1999, 6, 1), date(2002, 1, 1))]) == [
        OfficeCheckFlagKind.RANGE_OUTSIDE_DATES
    ]


def test_a_range_straddling_the_end_gives_one_outside_flag() -> None:
    assert _get_kinds([_build_range_row(date(2004, 1, 1), date(2007, 1, 1))]) == [
        OfficeCheckFlagKind.RANGE_OUTSIDE_DATES
    ]


def test_a_range_wholly_before_the_start_gives_both_flags() -> None:
    assert _get_kinds([_build_range_row(date(1990, 1, 1), date(1995, 1, 1))]) == [
        OfficeCheckFlagKind.RANGE_OUTSIDE_DATES,
        OfficeCheckFlagKind.NO_PRINT_INSIDE_DATES,
    ]


def test_no_range_gives_one_no_print_flag() -> None:
    flags = get_office_check_flags(_MINISTER, [], _TITLES_IN_MINISTRY)

    assert [flag.kind for flag in flags] == [OfficeCheckFlagKind.NO_PRINT_INSIDE_DATES]
    assert flags[0].member_name == _MEMBER_NAME
    assert flags[0].source_url == _SOURCE_URL
    assert flags[0].office_printed is None


def test_a_range_in_another_ministry_is_ignored() -> None:
    assert _get_kinds(
        [_build_range_row(date(1990, 1, 1), date(1995, 1, 1), _OTHER_TITLE)]
    ) == [OfficeCheckFlagKind.NO_PRINT_INSIDE_DATES]


def _seed_check_database(session: Session) -> int:
    speaker = Speaker(
        name=_MEMBER_NAME,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=9,
    )
    sitting = Sitting(sitting_date="5-3-2003", parlement_no=9)
    health = Ministry(name=_HEALTH_MINISTRY)
    session.add_all([speaker, sitting, health])
    session.flush()
    assert speaker.id is not None
    assert sitting.id is not None
    assert health.id is not None
    attendance = Attendance(
        sitting_id=sitting.id, speaker_name=_MEMBER_NAME, speaker_id=speaker.id
    )
    session.add(attendance)
    session.flush()
    assert attendance.id is not None
    attendance_office = AttendanceOffice(
        office_printed=_HEALTH_TITLE,
        entry_line_printed=_HEALTH_TITLE,
        office_class=OfficeClass.MINISTER,
        source=AttendanceOfficeSource.AFTER_CONSTITUENCY_BRACKET,
        extracted_at=datetime.now(timezone.utc),
        attendance_id=attendance.id,
    )
    session.add(attendance_office)
    session.flush()
    assert attendance_office.id is not None
    session.add_all(
        [
            OfficeTitleMinistry(
                office_printed=_HEALTH_TITLE,
                ordinal=1,
                source=OfficeTitleMinistrySource.CLOSED_LIST_RULE,
                ministry_id=health.id,
            ),
            OfficePrintedRange(
                office_printed=_HEALTH_TITLE,
                office_class=OfficeClass.MINISTER,
                sitting_count=1,
                first_sitting_date=datetime(2003, 3, 5),
                last_sitting_date=datetime(2008, 3, 5),
                built_at=datetime.now(timezone.utc),
                speaker_id=speaker.id,
                first_attendance_office_id=attendance_office.id,
                last_attendance_office_id=attendance_office.id,
            ),
        ]
    )
    session.commit()
    return speaker.id


def _use_scratch_engine(
    monkeypatch: pytest.MonkeyPatch,
    scratch_engine: Engine,
    ministers: list[OfficeCheckMinister],
) -> None:
    monkeypatch.setattr(
        check_script, "build_read_only_engine", lambda database_url: scratch_engine
    )
    monkeypatch.setattr(check_script, "get_office_check_ministers", lambda: ministers)


def test_the_script_writes_one_object_per_flag_and_changes_no_row(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    speaker_id = _seed_check_database(scratch_session)
    minister = _MINISTER.model_copy(update={"speaker_ids": [speaker_id]})
    _use_scratch_engine(monkeypatch, scratch_engine, [minister])
    output_path = tmp_path / "flags.json"

    check_office_ranges_against_ministers(output_path)

    flags = json.loads(output_path.read_text())
    assert [(flag["kind"], flag["office_printed"]) for flag in flags] == [
        ("RANGE_OUTSIDE_DATES", _HEALTH_TITLE)
    ]
    assert flags[0]["first_sitting_date"] == "2003-03-05"
    assert flags[0]["last_sitting_date"] == "2008-03-05"
    scratch_session.expire_all()
    assert scratch_session.get(OfficePrintedRange, 1) is not None


def test_the_script_with_no_ministers_writes_an_empty_list(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_scratch_engine(monkeypatch, scratch_engine, [])
    output_path = tmp_path / "flags.json"

    check_office_ranges_against_ministers(output_path)

    assert json.loads(output_path.read_text()) == []


def test_the_script_refuses_an_existing_output_file(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_scratch_engine(monkeypatch, scratch_engine, [])
    output_path = tmp_path / "flags.json"
    output_path.write_text("kept")

    with pytest.raises(HansardOfficeCheckError, match="exists"):
        check_office_ranges_against_ministers(output_path)

    assert output_path.read_text() == "kept"


def test_the_script_refuses_a_minister_whose_ministry_is_not_stored(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_scratch_engine(monkeypatch, scratch_engine, [_MINISTER])
    output_path = tmp_path / "flags.json"

    with pytest.raises(HansardOfficeCheckError, match="Health"):
        check_office_ranges_against_ministers(output_path)

    assert not output_path.exists()

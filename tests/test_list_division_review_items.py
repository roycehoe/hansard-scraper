from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.list_division_review_items as list_division_review_items_script
from database.attendance import Attendance
from database.division import Division
from database.division_vote import DivisionVote
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from database.report import Report
from database.sitting import Sitting
from database.speaker import Speaker
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionReviewItemKind,
    DivisionVoteChoice,
    DivisionVoteListSource,
    MinutesDivisionPairing,
    MinutesStatus,
    SpeechKind,
)
from schemas.division_review_list import DivisionReviewItem, DivisionReviewList
from scripts.list_division_review_items import (
    get_division_review_list,
    get_summary_lines,
    list_division_review_items,
)
from tests.division_seed import add_division_report, add_division_speech_rows

_SITTING_DATE = date(2021, 10, 4)
_SITTING_DATETIME = datetime(2021, 10, 4)
_SITTING_DATE_TEXT = "04-10-2021"
_PARLIAMENT_NUMBER = 14
_REPORT_ID = "review-report"
_OTHER_REPORT_ID = "review-other-report"
_AYES = 10
_NOES = 3
_PRINTED_COUNTS = "The House divided: Ayes, 10; Noes, 3."
_MINUTES_PRINTED_COUNTS = "On Question put, a division was taken: Ayes 10, Noes 3."
_SPEAKER_NAME = "Lee Hsien Loong"
_REVIEW_NOTE = "the file date disagrees with the sitting"
_EXTRACTED_TEXT_LENGTH = 1_000
_SOURCE_TEXT_LIMIT = 400
_KIND_COUNT = 13
_UNREAD_OPENING = "The House divided."
_PRINTED_LIST = "Ayes: Mr A"


def _get_items(
    review_list: DivisionReviewList, kind: DivisionReviewItemKind
) -> list[DivisionReviewItem]:
    return [item for item in review_list.items if item.kind == kind]


def _add_hansard_division(
    session: Session,
    report: Report,
    number: int,
    abstentions: Optional[int] = None,
    list_status: DivisionListStatus = DivisionListStatus.NOT_PRINTED,
    printed_list: Optional[str] = None,
) -> Division:
    division = Division(
        sitting_date=report.sitting_date.date(),
        parliament_number=report.parliament_number,
        report_division_number=number,
        speech_ordinal=number,
        count_source=DivisionCountSource.PRINTED_LINE,
        printed_counts=_PRINTED_COUNTS,
        ayes=_AYES,
        noes=_NOES,
        abstentions=abstentions,
        list_status=list_status,
        printed_list=printed_list,
        sprs_report_id=report.report_id,
    )
    session.add(division)
    session.flush()
    return division


def _add_minutes_only_division(session: Session) -> Division:
    division = Division(
        sitting_date=_SITTING_DATE,
        parliament_number=_PARLIAMENT_NUMBER,
        count_source=DivisionCountSource.MINUTES,
        printed_counts=_MINUTES_PRINTED_COUNTS,
        ayes=_AYES,
        noes=_NOES,
        list_status=DivisionListStatus.NOT_PRINTED,
    )
    session.add(division)
    session.flush()
    return division


def _add_minutes(
    session: Session,
    status: MinutesStatus = MinutesStatus.TEXT_STORED,
    status_note: Optional[str] = None,
    extracted_text: Optional[str] = None,
) -> Minutes:
    minutes = Minutes(
        sitting_date=_SITTING_DATE,
        status=status,
        status_note=status_note,
        extracted_text=extracted_text,
    )
    session.add(minutes)
    session.flush()
    return minutes


def _add_minutes_division(
    session: Session,
    minutes: Minutes,
    division: Division,
    pairing: MinutesDivisionPairing,
    abstentions: Optional[int] = None,
    list_status: DivisionListStatus = DivisionListStatus.NOT_PRINTED,
    printed_list: Optional[str] = None,
) -> MinutesDivision:
    assert minutes.id is not None
    assert division.id is not None
    minutes_division = MinutesDivision(
        ordinal=1,
        printed_counts=_MINUTES_PRINTED_COUNTS,
        ayes=_AYES,
        noes=_NOES,
        abstentions=abstentions,
        printed_list=printed_list,
        list_status=list_status,
        pairing=pairing,
        minutes_id=minutes.id,
        division_id=division.id,
    )
    session.add(minutes_division)
    session.flush()
    return minutes_division


def _add_speaker(session: Session) -> Speaker:
    speaker = Speaker(
        name=_SPEAKER_NAME,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    session.add(speaker)
    session.flush()
    return speaker


def _add_vote(
    session: Session,
    division: Division,
    list_source: DivisionVoteListSource,
    ordinal: int,
    vote_choice: DivisionVoteChoice,
    speaker: Speaker,
) -> None:
    assert division.id is not None
    session.add(
        DivisionVote(
            ordinal=ordinal,
            printed_name=_SPEAKER_NAME,
            vote_choice=vote_choice,
            list_source=list_source,
            division_id=division.id,
            speaker_id=speaker.id,
        )
    )
    session.flush()


def _add_paired_date(session: Session) -> tuple[Report, Division, MinutesDivision]:
    report = add_division_report(
        session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    division = _add_hansard_division(session, report, 1)
    minutes = _add_minutes(session)
    minutes_division = _add_minutes_division(
        session, minutes, division, MinutesDivisionPairing.PAIRED
    )
    return report, division, minutes_division


def test_an_unread_total_row_is_listed(scratch_session: Session) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    add_division_speech_rows(
        scratch_session, report, [(SpeechKind.PROCEDURAL, None, _UNREAD_OPENING)]
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(review_list, DivisionReviewItemKind.UNREAD_DIVISION_ROW)
    assert item.sprs_report_id == _REPORT_ID
    assert item.sitting_date == _SITTING_DATE
    assert item.source_text == _UNREAD_OPENING
    assert item.data_says == "no division was made from this row"
    assert "OPENING_WITHOUT_COUNTS" in item.rule


def test_a_counts_disagree_list_is_listed(scratch_session: Session) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    division = _add_hansard_division(
        scratch_session,
        report,
        1,
        list_status=DivisionListStatus.COUNTS_DISAGREE,
        printed_list=_PRINTED_LIST,
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(review_list, DivisionReviewItemKind.LIST_COUNTS_DISAGREE)
    assert item.division_id == division.id
    assert item.source_text == _PRINTED_LIST
    assert "Ayes 10, Noes 3" in item.data_says


def test_a_layout_unreadable_list_is_listed(scratch_session: Session) -> None:
    minutes = _add_minutes(scratch_session)
    division = _add_minutes_only_division(scratch_session)
    _add_minutes_division(
        scratch_session,
        minutes,
        division,
        MinutesDivisionPairing.NO_MATCHING_DIVISION,
        list_status=DivisionListStatus.LAYOUT_UNREADABLE,
        printed_list=_PRINTED_LIST,
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(review_list, DivisionReviewItemKind.LIST_LAYOUT_UNREADABLE)
    assert item.minutes_id == minutes.id
    assert item.source_text == _PRINTED_LIST


def test_an_unpaired_minutes_division_is_listed_apart_from_defects(
    scratch_session: Session,
) -> None:
    minutes = _add_minutes(scratch_session)
    division = _add_minutes_only_division(scratch_session)
    _add_minutes_division(
        scratch_session, minutes, division, MinutesDivisionPairing.NO_MATCHING_DIVISION
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(
        review_list, DivisionReviewItemKind.MINUTES_DIVISION_WITHOUT_HANSARD_DIVISION
    )
    assert item.minutes_id == minutes.id
    summary_lines = get_summary_lines(review_list)
    assert "Review items that are defects: 0" in summary_lines
    assert (
        "Expected, not defects, MINUTES_DIVISION_WITHOUT_HANSARD_DIVISION: 1"
        in summary_lines
    )


def test_unequal_number_names_both_sides(scratch_session: Session) -> None:
    first_report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    first_division = _add_hansard_division(scratch_session, first_report, 1)
    second_division = _add_hansard_division(scratch_session, first_report, 2)
    minutes = _add_minutes(scratch_session)
    minutes_only_division = _add_minutes_only_division(scratch_session)
    _add_minutes_division(
        scratch_session,
        minutes,
        minutes_only_division,
        MinutesDivisionPairing.UNEQUAL_NUMBER,
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(
        review_list, DivisionReviewItemKind.MINUTES_DIVISION_UNEQUAL_NUMBER
    )
    assert "minutes division 1: Ayes 10, Noes 3" in item.data_says
    assert f"division {first_division.id} of report {_REPORT_ID}" in item.data_says
    assert f"division {second_division.id} of report {_REPORT_ID}" in item.data_says


def test_a_tied_division_names_both_sides(scratch_session: Session) -> None:
    first_report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    second_report = add_division_report(
        scratch_session, _OTHER_REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    first_division = _add_hansard_division(scratch_session, first_report, 1)
    second_division = _add_hansard_division(scratch_session, second_report, 1)
    minutes = _add_minutes(scratch_session)
    minutes_only_division = _add_minutes_only_division(scratch_session)
    _add_minutes_division(
        scratch_session, minutes, minutes_only_division, MinutesDivisionPairing.TIED
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(review_list, DivisionReviewItemKind.MINUTES_DIVISION_TIED)
    assert f"division {first_division.id} of report {_REPORT_ID}" in item.data_says
    assert (
        f"division {second_division.id} of report {_OTHER_REPORT_ID}" in item.data_says
    )


def test_differing_abstentions_name_both_sides(scratch_session: Session) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    _add_hansard_division(scratch_session, report, 1, abstentions=1)
    minutes = _add_minutes(scratch_session)
    minutes_only_division = _add_minutes_only_division(scratch_session)
    _add_minutes_division(
        scratch_session,
        minutes,
        minutes_only_division,
        MinutesDivisionPairing.ABSTENTIONS_DIFFER,
        abstentions=2,
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(
        review_list, DivisionReviewItemKind.MINUTES_DIVISION_ABSTENTIONS_DIFFER
    )
    assert "Abstentions 2" in item.data_says
    assert "Abstentions 1" in item.data_says


def test_a_hansard_division_with_stored_minutes_and_no_pair_is_listed(
    scratch_session: Session,
) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    division = _add_hansard_division(scratch_session, report, 1)
    _add_minutes(scratch_session)

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(
        review_list, DivisionReviewItemKind.HANSARD_DIVISION_WITHOUT_MINUTES_PAIR
    )
    assert item.division_id == division.id
    assert item.sprs_report_id == _REPORT_ID


def _add_absent_attendance(session: Session, speaker: Speaker) -> Attendance:
    sitting = Sitting(sitting_date=_SITTING_DATE_TEXT)
    session.add(sitting)
    session.flush()
    assert sitting.id is not None
    attendance = Attendance(
        sitting_id=sitting.id,
        speaker_name=_SPEAKER_NAME,
        is_present=False,
        speaker_id=speaker.id,
    )
    session.add(attendance)
    session.flush()
    return attendance


def test_a_vote_for_a_member_absent_that_sitting_is_listed(
    scratch_session: Session,
) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    division = _add_hansard_division(scratch_session, report, 1)
    speaker = _add_speaker(scratch_session)
    attendance = _add_absent_attendance(scratch_session, speaker)
    _add_vote(
        scratch_session,
        division,
        DivisionVoteListSource.HANSARD,
        1,
        DivisionVoteChoice.AYE,
        speaker,
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(
        review_list, DivisionReviewItemKind.VOTE_MEMBER_ABSENT_THAT_SITTING
    )
    assert item.division_id == division.id
    assert f"attendance row {attendance.id}" in item.data_says


def test_an_absent_or_paired_row_of_an_absent_member_is_not_listed(
    scratch_session: Session,
) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    division = _add_hansard_division(scratch_session, report, 1)
    speaker = _add_speaker(scratch_session)
    _add_absent_attendance(scratch_session, speaker)
    _add_vote(
        scratch_session,
        division,
        DivisionVoteListSource.HANSARD,
        1,
        DivisionVoteChoice.ABSENT,
        speaker,
    )
    _add_vote(
        scratch_session,
        division,
        DivisionVoteListSource.HANSARD,
        2,
        DivisionVoteChoice.PAIRED,
        speaker,
    )

    review_list = get_division_review_list(scratch_session)

    assert (
        _get_items(review_list, DivisionReviewItemKind.VOTE_MEMBER_ABSENT_THAT_SITTING)
        == []
    )


def test_a_member_on_two_sides_is_listed(scratch_session: Session) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    division = _add_hansard_division(scratch_session, report, 1)
    speaker = _add_speaker(scratch_session)
    _add_vote(
        scratch_session,
        division,
        DivisionVoteListSource.HANSARD,
        1,
        DivisionVoteChoice.AYE,
        speaker,
    )
    _add_vote(
        scratch_session,
        division,
        DivisionVoteListSource.HANSARD,
        2,
        DivisionVoteChoice.NO,
        speaker,
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(review_list, DivisionReviewItemKind.MEMBER_ON_TWO_SIDES)
    assert item.division_id == division.id
    assert "AYE" in item.data_says
    assert "NO" in item.data_says


def test_a_member_on_different_sides_in_the_two_lists_is_listed(
    scratch_session: Session,
) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    division = _add_hansard_division(scratch_session, report, 1)
    speaker = _add_speaker(scratch_session)
    _add_vote(
        scratch_session,
        division,
        DivisionVoteListSource.MINUTES,
        1,
        DivisionVoteChoice.AYE,
        speaker,
    )
    _add_vote(
        scratch_session,
        division,
        DivisionVoteListSource.HANSARD,
        1,
        DivisionVoteChoice.NO,
        speaker,
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(
        review_list, DivisionReviewItemKind.MEMBER_ON_DIFFERENT_SIDES_IN_TWO_LISTS
    )
    assert item.division_id == division.id
    assert not _get_items(review_list, DivisionReviewItemKind.MEMBER_ON_TWO_SIDES)


def test_a_needs_review_file_is_listed(scratch_session: Session) -> None:
    minutes = _add_minutes(
        scratch_session,
        status=MinutesStatus.NEEDS_REVIEW,
        status_note=_REVIEW_NOTE,
        extracted_text="x" * _EXTRACTED_TEXT_LENGTH,
    )

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(review_list, DivisionReviewItemKind.MINUTES_FILE_NEEDS_REVIEW)
    assert item.minutes_id == minutes.id
    assert item.data_says == _REVIEW_NOTE
    assert len(item.source_text) == _SOURCE_TEXT_LIMIT


def test_a_stale_pairing_is_listed(scratch_session: Session) -> None:
    report, division, minutes_division = _add_paired_date(scratch_session)
    assert get_division_review_list(scratch_session).items == []
    _add_hansard_division(scratch_session, report, 2)

    review_list = get_division_review_list(scratch_session)

    (item,) = _get_items(review_list, DivisionReviewItemKind.MINUTES_PAIRING_STALE)
    assert item.division_id == division.id
    assert item.minutes_id == minutes_division.minutes_id
    assert "stored: pairing PAIRED" in item.data_says
    assert "rerun: pairing UNEQUAL_NUMBER" in item.data_says


def test_the_list_status_share_keeps_hansard_and_minutes_lists_apart(
    scratch_session: Session,
) -> None:
    report = add_division_report(
        scratch_session, _REPORT_ID, _SITTING_DATETIME, _PARLIAMENT_NUMBER
    )
    hansard_division = _add_hansard_division(
        scratch_session,
        report,
        1,
        list_status=DivisionListStatus.STORED,
        printed_list=_PRINTED_LIST,
    )
    _add_minutes_only_division(scratch_session)
    minutes = _add_minutes(scratch_session)
    _add_minutes_division(
        scratch_session,
        minutes,
        hansard_division,
        MinutesDivisionPairing.PAIRED,
        list_status=DivisionListStatus.COUNTS_DISAGREE,
        printed_list=_PRINTED_LIST,
    )

    lines = get_summary_lines(get_division_review_list(scratch_session))

    assert (
        "Hansard divisions of the 2020s by list status: STORED 1 of 1 (100.0%)" in lines
    )
    assert (
        "Minutes lists of the 2020s by list status: COUNTS_DISAGREE 1 of 1 (100.0%)"
        in lines
    )


def test_a_clean_database_gives_an_empty_list(scratch_session: Session) -> None:
    review_list = get_division_review_list(scratch_session)

    assert review_list.items == []
    assert len(review_list.kind_to_count) == _KIND_COUNT
    assert set(review_list.kind_to_count.values()) == {0}


def test_the_script_writes_both_files_through_a_read_only_engine(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _add_minutes(
        scratch_session, status=MinutesStatus.NEEDS_REVIEW, status_note=_REVIEW_NOTE
    )
    scratch_session.commit()
    requested_urls: list[str] = []

    def build_recording_engine(database_url: str) -> Engine:
        requested_urls.append(database_url)
        return scratch_engine

    monkeypatch.setattr(
        list_division_review_items_script,
        "build_read_only_engine",
        build_recording_engine,
    )
    review_path = tmp_path / "review.json"
    summary_path = tmp_path / "summary.txt"

    list_division_review_items(review_path, summary_path)

    assert len(requested_urls) == 1
    review_list = DivisionReviewList.model_validate_json(review_path.read_text())
    assert [item.kind for item in review_list.items] == [
        DivisionReviewItemKind.MINUTES_FILE_NEEDS_REVIEW
    ]
    assert "Review items that are defects: 1" in summary_path.read_text()

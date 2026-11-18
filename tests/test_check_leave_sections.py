from datetime import date

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.check_leave_sections as check_script
from database.leave_period import LeavePeriod, LeavePeriodPrinting
from database.sitting import Sitting
from enums import LeaveEntryFormat, LeaveNameSource, LeaveYearSource
from exceptions import HansardLeaveSectionCheckError
from scripts.check_leave_sections import check_leave_sections

_PARLIAMENT_NUMBER = 3
_GRANTING_SENTENCE = "Under the provisions of clause 2 (d) of Article 30 of the Constitution of Singapore, I have granted permission to Dr Chew Chin Han (Tampines) to be absent from the sitting of Parliament today, the 2nd November, 1967.   "
_READ_MARKDOWN = "\n".join(
    [
        "#### PERMISSION TO MEMBERS TO BE ABSENT",
        "Mr Lee (Tanglin) - from 3rd to 10th June, 1967.",
    ]
)
_SENTENCE_MARKDOWN = "\n".join(
    ["#### PERMISSION TO MEMBER TO BE ABSENT", _GRANTING_SENTENCE]
)
_RENAMED_HEADING_MARKDOWN = "\n".join(
    ["#### LEAVE OF ABSENCE FOR MEMBERS", _GRANTING_SENTENCE]
)
_DEBATE_MARKDOWN = "Mr Lim: Sir, with your permission, I beg leave to withdraw."


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
    monkeypatch.setattr(
        check_script, "build_read_only_engine", lambda database_url: scratch_engine
    )
    monkeypatch.setattr(check_script, "logger", recorder)
    return recorder


def _seed_sitting(
    session: Session, sitting_id: int, sitting_date: str, markdown_content: str
) -> None:
    session.add(
        Sitting(
            id=sitting_id,
            sitting_date=sitting_date,
            parlement_no=_PARLIAMENT_NUMBER,
            markdown_content=markdown_content,
        )
    )
    session.commit()


def _seed_printing(session: Session, sitting_id: int, sitting_date: date) -> None:
    leave_period = LeavePeriod(period_key="mr lee|1967-06-03|1967-06-10")
    session.add(leave_period)
    session.flush()
    assert leave_period.id is not None
    session.add(
        LeavePeriodPrinting(
            ordinal=1,
            sitting_date=sitting_date,
            printed_name="Mr Lee",
            entry_format=LeaveEntryFormat.PROSE_RANGE,
            name_source=LeaveNameSource.PRINTED,
            year_source=LeaveYearSource.PRINTED_IN_ENTRY,
            sitting_id=sitting_id,
            leave_period_id=leave_period.id,
        )
    )
    session.commit()


def test_a_sitting_with_a_stored_printing_or_no_leave_words_is_not_reported(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sitting(scratch_session, 1, "8-6-1967", _READ_MARKDOWN)
    _seed_printing(scratch_session, 1, date(1967, 6, 8))
    _seed_sitting(scratch_session, 2, "9-6-1967", _DEBATE_MARKDOWN)

    check_leave_sections()

    assert log_recorder.messages == [
        "Every sitting that prints a leave section holds a leave period printing"
    ]


def test_a_sitting_that_prints_a_granting_sentence_and_holds_no_printing_is_reported(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sitting(scratch_session, 1, "8-6-1967", _READ_MARKDOWN)
    _seed_printing(scratch_session, 1, date(1967, 6, 8))
    _seed_sitting(scratch_session, 2, "2-11-1967", _SENTENCE_MARKDOWN)

    with pytest.raises(HansardLeaveSectionCheckError, match="1 sittings"):
        check_leave_sections()

    assert log_recorder.messages == [
        "Sitting 2 of 1967-11-02 prints HEADING_WORDS, GRANTING_SENTENCE and holds no leave period printing"
    ]


def test_a_heading_the_reader_does_not_know_is_caught_by_its_granting_sentence(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sitting(scratch_session, 1, "2-11-1967", _RENAMED_HEADING_MARKDOWN)

    with pytest.raises(HansardLeaveSectionCheckError):
        check_leave_sections()

    assert log_recorder.messages == [
        "Sitting 1 of 1967-11-02 prints GRANTING_SENTENCE and holds no leave period printing"
    ]


def test_the_reported_sittings_come_in_date_order(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sitting(scratch_session, 1, "2-11-1967", _SENTENCE_MARKDOWN)
    _seed_sitting(scratch_session, 2, "14-12-1955", _SENTENCE_MARKDOWN)

    with pytest.raises(HansardLeaveSectionCheckError, match="2 sittings"):
        check_leave_sections()

    assert [message.split(" prints ")[0] for message in log_recorder.messages] == [
        "Sitting 2 of 1955-12-14",
        "Sitting 1 of 1967-11-02",
    ]


def test_a_sitting_with_no_markdown_is_not_read(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    scratch_session.add(
        Sitting(id=1, sitting_date="2-11-2020", parlement_no=_PARLIAMENT_NUMBER)
    )
    scratch_session.commit()

    check_leave_sections()

    assert len(log_recorder.messages) == 1


def test_the_check_changes_no_row(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sitting(scratch_session, 1, "2-11-1967", _SENTENCE_MARKDOWN)

    with pytest.raises(HansardLeaveSectionCheckError):
        check_leave_sections()

    scratch_session.expire_all()
    assert len(scratch_session.exec(select(Sitting)).all()) == 1
    assert scratch_session.exec(select(LeavePeriodPrinting)).all() == []
    assert log_recorder.messages

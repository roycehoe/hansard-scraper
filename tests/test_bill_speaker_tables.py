from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from database.bill import Bill
from database.bill_key import BillKey
from database.bill_report_speaker import BillReportSpeaker
from database.bill_stage_line import BillStageLine
from database.speaker import Speaker
from enums import BillStage, ReportType
from tests.bill_seed import seed_bill_report

_SITTING_DATE = datetime(2024, 11, 12)
_FIRST_SPRS_REPORT_ID = "table-first"
_SECOND_SPRS_REPORT_ID = "table-second"


def _seed_bill(session: Session, title_key: str) -> int:
    bill = Bill(
        title="Food Bill",
        title_key=title_key,
        first_sitting_date=_SITTING_DATE,
        last_sitting_date=_SITTING_DATE,
        is_passed=False,
    )
    session.add(bill)
    session.flush()
    assert bill.id is not None
    return bill.id


def _seed_reports(session: Session) -> None:
    for sprs_report_id in (_FIRST_SPRS_REPORT_ID, _SECOND_SPRS_REPORT_ID):
        seed_bill_report(
            session, sprs_report_id, ReportType.BILL, _SITTING_DATE, "Food Bill", []
        )


def _seed_speaker(session: Session) -> int:
    speaker = Speaker(
        name="Ms A", party="PAP", is_legislative_assembly=False, parliament_number=14
    )
    session.add(speaker)
    session.flush()
    assert speaker.id is not None
    return speaker.id


def test_two_bill_keys_cannot_share_a_bill_key(scratch_session: Session) -> None:
    _seed_reports(scratch_session)
    first_bill_id = _seed_bill(scratch_session, "foodbill1")
    second_bill_id = _seed_bill(scratch_session, "foodbill2")
    scratch_session.add(
        BillKey(act_count=0, bill_key=_FIRST_SPRS_REPORT_ID, bill_id=first_bill_id)
    )
    scratch_session.add(
        BillKey(act_count=0, bill_key=_FIRST_SPRS_REPORT_ID, bill_id=second_bill_id)
    )

    with pytest.raises(IntegrityError):
        scratch_session.commit()


def test_two_bill_keys_cannot_share_a_bill(scratch_session: Session) -> None:
    _seed_reports(scratch_session)
    bill_id = _seed_bill(scratch_session, "foodbill1")
    scratch_session.add(
        BillKey(act_count=0, bill_key=_FIRST_SPRS_REPORT_ID, bill_id=bill_id)
    )
    scratch_session.add(
        BillKey(act_count=0, bill_key=_SECOND_SPRS_REPORT_ID, bill_id=bill_id)
    )

    with pytest.raises(IntegrityError):
        scratch_session.commit()


def test_a_member_and_report_pair_is_unique(scratch_session: Session) -> None:
    _seed_reports(scratch_session)
    speaker_id = _seed_speaker(scratch_session)
    for _ in range(2):
        scratch_session.add(
            BillReportSpeaker(
                speech_count=1,
                first_ordinal=1,
                printed_speaker="Ms A",
                sprs_report_id=_FIRST_SPRS_REPORT_ID,
                speaker_id=speaker_id,
            )
        )

    with pytest.raises(IntegrityError):
        scratch_session.commit()


def test_a_stage_line_is_unique_per_report_ordinal_and_stage(
    scratch_session: Session,
) -> None:
    _seed_reports(scratch_session)
    for _ in range(2):
        scratch_session.add(
            BillStageLine(
                stage=BillStage.FIRST_READING,
                printed_text="Bill read a First time.",
                ordinal=1,
                sprs_report_id=_FIRST_SPRS_REPORT_ID,
            )
        )

    with pytest.raises(IntegrityError):
        scratch_session.commit()


def test_the_same_ordinal_can_hold_two_stages(scratch_session: Session) -> None:
    _seed_reports(scratch_session)
    scratch_session.add(
        BillStageLine(
            stage=BillStage.FIRST_READING,
            printed_text="Bill read a First time.",
            ordinal=1,
            sprs_report_id=_FIRST_SPRS_REPORT_ID,
        )
    )
    scratch_session.add(
        BillStageLine(
            stage=BillStage.THIRD_READING,
            printed_text="Bill read a Third time and passed.",
            ordinal=1,
            sprs_report_id=_FIRST_SPRS_REPORT_ID,
        )
    )

    scratch_session.commit()

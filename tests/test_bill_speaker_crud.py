from datetime import datetime

from sqlmodel import Session

from crud.bill_key import BillKeyRow, CRUDBillKey
from crud.bill_report_speaker import CRUDBillReportSpeaker
from crud.bill_stage_line import CRUDBillStageLine
from database.bill_key import BillKey
from database.bill_report_speaker import BillReportSpeaker
from database.bill_stage_line import BillStageLine
from enums import BillReportRole, BillStage, ReportType
from tests.bill_seed import seed_bill, seed_bill_report, seed_speaker

_FIRST_SPRS_REPORT_ID = "crud-first"
_SECOND_SPRS_REPORT_ID = "crud-second"
_SITTING_DATE = datetime(2024, 11, 12)
_TWO_ROWS = 2
_THREE_ROWS = 3


def _seed_two_reports(session: Session) -> list[int]:
    return [
        seed_bill_report(
            session, sprs_report_id, ReportType.BILL, _SITTING_DATE, "Food Bill", []
        )
        for sprs_report_id in (_FIRST_SPRS_REPORT_ID, _SECOND_SPRS_REPORT_ID)
    ]


def _seed_two_bill_keys(session: Session) -> tuple[int, int]:
    first_report_id, second_report_id = _seed_two_reports(session)
    first_bill_id = seed_bill(
        session, "Food Bill", {first_report_id: BillReportRole.READING}
    )
    second_bill_id = seed_bill(
        session, "Water Bill", {second_report_id: BillReportRole.READING}
    )
    CRUDBillKey(session).add_many(
        [
            BillKey(
                act_count=2, bill_key=_SECOND_SPRS_REPORT_ID, bill_id=second_bill_id
            ),
            BillKey(act_count=1, bill_key=_FIRST_SPRS_REPORT_ID, bill_id=first_bill_id),
        ]
    )
    session.commit()
    return first_bill_id, second_bill_id


def test_bill_key_rows_come_back_in_bill_order_and_delete_by_bill_ids_returns_the_count(
    scratch_session: Session,
) -> None:
    first_bill_id, second_bill_id = _seed_two_bill_keys(scratch_session)

    rows = CRUDBillKey(scratch_session).get_rows()

    assert [
        (row.bill_key, row.act_count, row.bill_id) for row in rows
    ] == [
        (_FIRST_SPRS_REPORT_ID, 1, first_bill_id),
        (_SECOND_SPRS_REPORT_ID, 2, second_bill_id),
    ]
    assert all(isinstance(row, BillKeyRow) for row in rows)
    assert CRUDBillKey(scratch_session).delete_by_bill_ids([first_bill_id]) == 1
    scratch_session.commit()
    assert [row.bill_id for row in CRUDBillKey(scratch_session).get_rows()] == [
        second_bill_id
    ]
    assert CRUDBillKey(scratch_session).delete_by_bill_ids([]) == 0


def test_bill_key_delete_all_returns_the_count_and_empties_the_table(
    scratch_session: Session,
) -> None:
    _seed_two_bill_keys(scratch_session)

    assert CRUDBillKey(scratch_session).delete_all() == _TWO_ROWS
    scratch_session.commit()
    assert CRUDBillKey(scratch_session).get_rows() == []


def _seed_three_member_rows(session: Session) -> None:
    _seed_two_reports(session)
    speaker_id = seed_speaker(session, "Ms A")
    other_speaker_id = seed_speaker(session, "Mr B")
    CRUDBillReportSpeaker(session).add_many(
        [
            BillReportSpeaker(
                speech_count=1,
                first_ordinal=5,
                printed_speaker="Mr B",
                sprs_report_id=_FIRST_SPRS_REPORT_ID,
                speaker_id=other_speaker_id,
            ),
            BillReportSpeaker(
                speech_count=2,
                first_ordinal=2,
                printed_speaker="Ms A",
                sprs_report_id=_FIRST_SPRS_REPORT_ID,
                speaker_id=speaker_id,
            ),
            BillReportSpeaker(
                speech_count=1,
                first_ordinal=1,
                printed_speaker="Ms A",
                sprs_report_id=_SECOND_SPRS_REPORT_ID,
                speaker_id=speaker_id,
            ),
        ]
    )
    session.commit()


def test_member_rows_by_sprs_report_ids_return_only_those_reports(
    scratch_session: Session,
) -> None:
    _seed_three_member_rows(scratch_session)

    first_report_rows = CRUDBillReportSpeaker(
        scratch_session
    ).get_rows_by_sprs_report_ids([_FIRST_SPRS_REPORT_ID])

    assert [row.first_ordinal for row in first_report_rows] == [2, 5]
    assert len(CRUDBillReportSpeaker(scratch_session).get_rows()) == _THREE_ROWS


def test_member_rows_delete_by_sprs_report_ids_returns_the_count_and_keeps_other_reports(
    scratch_session: Session,
) -> None:
    _seed_three_member_rows(scratch_session)

    deleted_count = CRUDBillReportSpeaker(scratch_session).delete_by_sprs_report_ids(
        [_FIRST_SPRS_REPORT_ID]
    )
    scratch_session.commit()

    assert deleted_count == _TWO_ROWS
    assert [
        row.sprs_report_id for row in CRUDBillReportSpeaker(scratch_session).get_rows()
    ] == [_SECOND_SPRS_REPORT_ID]
    assert CRUDBillReportSpeaker(scratch_session).delete_all() == 1


def _seed_three_stage_lines(session: Session) -> None:
    _seed_two_reports(session)
    CRUDBillStageLine(session).add_many(
        [
            BillStageLine(
                stage=BillStage.THIRD_READING,
                printed_text="Bill read a Third time and passed.",
                ordinal=1,
                sprs_report_id=_FIRST_SPRS_REPORT_ID,
            ),
            BillStageLine(
                stage=BillStage.FIRST_READING,
                printed_text="Bill read a First time.",
                ordinal=1,
                sprs_report_id=_FIRST_SPRS_REPORT_ID,
            ),
            BillStageLine(
                stage=BillStage.FIRST_READING,
                printed_text="Bill read a First time.",
                ordinal=3,
                sprs_report_id=_SECOND_SPRS_REPORT_ID,
            ),
        ]
    )
    session.commit()


def test_stage_line_rows_by_sprs_report_ids_return_only_those_reports(
    scratch_session: Session,
) -> None:
    _seed_three_stage_lines(scratch_session)

    first_report_rows = CRUDBillStageLine(scratch_session).get_rows_by_sprs_report_ids(
        [_FIRST_SPRS_REPORT_ID]
    )

    assert [(row.ordinal, row.stage) for row in first_report_rows] == [
        (1, BillStage.FIRST_READING),
        (1, BillStage.THIRD_READING),
    ]
    assert [
        (row.sprs_report_id, row.ordinal, row.stage)
        for row in CRUDBillStageLine(scratch_session).get_rows()
    ] == [
        (_FIRST_SPRS_REPORT_ID, 1, BillStage.FIRST_READING),
        (_FIRST_SPRS_REPORT_ID, 1, BillStage.THIRD_READING),
        (_SECOND_SPRS_REPORT_ID, 3, BillStage.FIRST_READING),
    ]


def test_stage_line_rows_delete_by_sprs_report_ids_returns_the_count_and_keeps_other_reports(
    scratch_session: Session,
) -> None:
    _seed_three_stage_lines(scratch_session)

    deleted_count = CRUDBillStageLine(scratch_session).delete_by_sprs_report_ids(
        [_FIRST_SPRS_REPORT_ID]
    )
    scratch_session.commit()

    assert deleted_count == _TWO_ROWS
    assert [
        row.sprs_report_id for row in CRUDBillStageLine(scratch_session).get_rows()
    ] == [_SECOND_SPRS_REPORT_ID]
    assert CRUDBillStageLine(scratch_session).delete_all() == 1

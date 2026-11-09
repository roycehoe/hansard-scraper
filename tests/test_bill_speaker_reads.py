from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session

from crud.bill_report import BillReportSittingDateReportTypeRow, CRUDBillReport
from crud.report import CRUDReport, ReportPlacementRow
from crud.speech import CRUDSpeech, SpeechOrdinalLabelRow, SpeechOrdinalTranscriptRow
from enums import BillReportRole, ReportType, SpeechKind
from tests.bill_seed import seed_bill, seed_bill_report, seed_speaker, seed_speech

_FIRST_DATE = datetime(2024, 11, 12)
_SECOND_DATE = datetime(2025, 1, 8)
_THIRD_READING_PATTERN = (
    r'^\W*[^"]{0,150}\ybill\y[^"]{0,120}\yread (a|the) third time'
)
_THIRD_READING_LINE = "Bill read a Third time and passed."


@dataclass(frozen=True)
class _SeededBill:
    bill_id: int
    first_report_id: int
    second_report_id: int
    budget_report_id: int


def _seed_bill_with_budget_report(session: Session) -> _SeededBill:
    first_report_id = seed_bill_report(
        session, "read-first", ReportType.BILL_INTRODUCTION, _FIRST_DATE, "Food Bill", []
    )
    second_report_id = seed_bill_report(
        session, "read-second", ReportType.BILL, _SECOND_DATE, "Food Bill", []
    )
    budget_report_id = seed_bill_report(
        session, "read-budget", ReportType.BUDGET, _SECOND_DATE, "Supply Bill", []
    )
    bill_id = seed_bill(
        session,
        "Food Bill",
        {
            first_report_id: BillReportRole.READING,
            second_report_id: BillReportRole.READING,
            budget_report_id: BillReportRole.BUDGET_DEBATE,
        },
    )
    return _SeededBill(bill_id, first_report_id, second_report_id, budget_report_id)


def test_bill_report_rows_carry_the_sprs_id_date_type_and_role(
    scratch_session: Session,
) -> None:
    seeded = _seed_bill_with_budget_report(scratch_session)

    rows = CRUDBillReport(scratch_session).get_sitting_date_report_type_rows()

    assert rows == [
        BillReportSittingDateReportTypeRow(
            seeded.bill_id,
            seeded.first_report_id,
            "read-first",
            _FIRST_DATE,
            "bill-intro",
            BillReportRole.READING,
        ),
        BillReportSittingDateReportTypeRow(
            seeded.bill_id,
            seeded.budget_report_id,
            "read-budget",
            _SECOND_DATE,
            "budget",
            BillReportRole.BUDGET_DEBATE,
        ),
        BillReportSittingDateReportTypeRow(
            seeded.bill_id,
            seeded.second_report_id,
            "read-second",
            _SECOND_DATE,
            "bill",
            BillReportRole.READING,
        ),
    ]


def test_bill_report_rows_by_report_ids_return_only_those_reports(
    scratch_session: Session,
) -> None:
    seeded = _seed_bill_with_budget_report(scratch_session)

    rows = CRUDBillReport(
        scratch_session
    ).get_sitting_date_report_type_rows_by_report_ids([seeded.second_report_id])

    assert [row.sprs_report_id for row in rows] == ["read-second"]
    assert (
        CRUDBillReport(scratch_session).get_sitting_date_report_type_rows_by_report_ids(
            []
        )
        == []
    )


def test_placement_rows_include_a_report_that_no_bill_holds(
    scratch_session: Session,
) -> None:
    joined_report_id = seed_bill_report(
        scratch_session, "place-joined", ReportType.BILL, _SECOND_DATE, "Food Bill", []
    )
    loose_report_id = seed_bill_report(
        scratch_session,
        "place-loose",
        ReportType.BILL_INTRODUCTION,
        _FIRST_DATE,
        "Water Bill",
        [],
    )
    seed_bill(scratch_session, "Food Bill", {joined_report_id: BillReportRole.READING})

    rows = CRUDReport(scratch_session).get_placement_rows_by_ids(
        [joined_report_id, loose_report_id]
    )

    assert rows == [
        ReportPlacementRow(
            loose_report_id, "place-loose", _FIRST_DATE, "Water Bill", "bill-intro"
        ),
        ReportPlacementRow(
            joined_report_id, "place-joined", _SECOND_DATE, "Food Bill", "bill"
        ),
    ]


def test_ordinal_label_rows_keep_only_spoken_rows_with_a_speaker_id(
    scratch_session: Session,
) -> None:
    report_id = seed_bill_report(
        scratch_session, "label-report", ReportType.BILL, _FIRST_DATE, "Food Bill", []
    )
    speaker_id = seed_speaker(scratch_session, "Ms A")
    seed_speech(
        scratch_session, report_id, 1, None, None, SpeechKind.PROCEDURAL, "Procedure."
    )
    seed_speech(
        scratch_session, report_id, 2, "Ms A", speaker_id, SpeechKind.SPEECH, "Sir."
    )
    seed_speech(
        scratch_session, report_id, 3, "Hon Member", None, SpeechKind.SPEECH, "Sir."
    )
    seed_speech(
        scratch_session, report_id, 4, "Ms A", speaker_id, SpeechKind.UNCLASSIFIED, "Sir."
    )

    rows = CRUDSpeech(
        scratch_session
    ).get_ordinal_label_rows_by_report_ids_and_kind_and_speaker_id_not_null(
        [report_id], SpeechKind.SPEECH
    )

    assert rows == [SpeechOrdinalLabelRow(report_id, speaker_id, 2, "Ms A")]


def test_ordinal_transcript_rows_apply_the_kinds_the_pattern_and_the_exclusions(
    scratch_session: Session,
) -> None:
    report_id = seed_bill_report(
        scratch_session,
        "transcript-report",
        ReportType.BILL,
        _FIRST_DATE,
        "Food Bill",
        [],
    )
    for ordinal, kind in enumerate(
        (
            SpeechKind.PROCEDURAL,
            SpeechKind.UNCLASSIFIED,
            SpeechKind.SPEECH,
            SpeechKind.DOCUMENT_TEXT,
        ),
        start=1,
    ):
        seed_speech(
            scratch_session, report_id, ordinal, None, None, kind, _THIRD_READING_LINE
        )
    seed_speech(
        scratch_session,
        report_id,
        5,
        None,
        None,
        SpeechKind.PROCEDURAL,
        "That the Bill be now read a Third time.",
    )

    rows = CRUDSpeech(
        scratch_session
    ).get_ordinal_transcript_rows_by_report_ids_and_kinds_and_transcript_regex_and_transcript_not_regexes(
        [report_id],
        (SpeechKind.PROCEDURAL, SpeechKind.UNCLASSIFIED),
        _THIRD_READING_PATTERN,
        ("be now",),
    )

    assert rows == [
        SpeechOrdinalTranscriptRow(report_id, 1, _THIRD_READING_LINE),
        SpeechOrdinalTranscriptRow(report_id, 2, _THIRD_READING_LINE),
    ]

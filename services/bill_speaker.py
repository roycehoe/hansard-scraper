from collections import Counter

from crud.bill_report import BillReportSittingDateReportTypeRow
from crud.speech import SpeechOrdinalLabelRow, SpeechOrdinalTranscriptRow
from database.bill_report_speaker import BillReportSpeaker
from database.bill_stage_line import BillStageLine
from enums import BillReportRole, BillStage
from exceptions import HansardBillKeyError


def get_bill_key(
    bill_id: int, bill_report_rows: list[BillReportSittingDateReportTypeRow]
) -> str:
    try:
        return min(
            (
                bill_report_row
                for bill_report_row in bill_report_rows
                if bill_report_row.role == BillReportRole.READING
            ),
            key=lambda bill_report_row: (
                bill_report_row.sitting_date,
                bill_report_row.sprs_report_id,
            ),
        ).sprs_report_id
    except ValueError as error:
        raise HansardBillKeyError(f"Bill {bill_id} has no READING report") from error


def build_bill_report_speakers(
    ordinal_label_rows: list[SpeechOrdinalLabelRow],
    report_id_to_sprs_report_id: dict[int, str],
) -> list[BillReportSpeaker]:
    report_speaker_key_to_first_row: dict[tuple[int, int], SpeechOrdinalLabelRow] = {}
    report_speaker_key_to_speech_count: Counter[tuple[int, int]] = Counter()
    for ordinal_label_row in ordinal_label_rows:
        report_speaker_key = (ordinal_label_row.report_id, ordinal_label_row.speaker_id)
        report_speaker_key_to_speech_count[report_speaker_key] += 1
        first_row = report_speaker_key_to_first_row.get(report_speaker_key)
        if first_row is None or ordinal_label_row.ordinal < first_row.ordinal:
            report_speaker_key_to_first_row[report_speaker_key] = ordinal_label_row
    return [
        BillReportSpeaker(
            speech_count=report_speaker_key_to_speech_count[report_speaker_key],
            first_ordinal=first_row.ordinal,
            printed_speaker=first_row.speaker,
            sprs_report_id=report_id_to_sprs_report_id[first_row.report_id],
            speaker_id=first_row.speaker_id,
        )
        for report_speaker_key, first_row in sorted(
            report_speaker_key_to_first_row.items()
        )
    ]


def build_bill_stage_lines(
    stage: BillStage,
    ordinal_transcript_rows: list[SpeechOrdinalTranscriptRow],
    report_id_to_sprs_report_id: dict[int, str],
) -> list[BillStageLine]:
    return [
        BillStageLine(
            stage=stage,
            printed_text=ordinal_transcript_row.transcript,
            ordinal=ordinal_transcript_row.ordinal,
            sprs_report_id=report_id_to_sprs_report_id[
                ordinal_transcript_row.report_id
            ],
        )
        for ordinal_transcript_row in ordinal_transcript_rows
    ]

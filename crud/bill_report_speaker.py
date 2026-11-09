from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from database.bill_report_speaker import BillReportSpeaker


@dataclass(frozen=True)
class BillReportSpeakerRow:
    id: int
    speech_count: int
    first_ordinal: int
    printed_speaker: str
    sprs_report_id: str
    speaker_id: int


class CRUDBillReportSpeaker:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, bill_report_speakers: list[BillReportSpeaker]) -> None:
        self.session.add_all(bill_report_speakers)
        self.session.flush()

    def get_rows(self) -> list[BillReportSpeakerRow]:
        statement = select(
            BillReportSpeaker.id,
            BillReportSpeaker.speech_count,
            BillReportSpeaker.first_ordinal,
            BillReportSpeaker.printed_speaker,
            BillReportSpeaker.sprs_report_id,
            BillReportSpeaker.speaker_id,
        ).order_by(
            BillReportSpeaker.sprs_report_id,
            BillReportSpeaker.first_ordinal,
            BillReportSpeaker.speaker_id,
        )
        return [
            BillReportSpeakerRow(*row) for row in self.session.exec(statement).all()
        ]

    def get_rows_by_sprs_report_ids(
        self, sprs_report_ids: list[str]
    ) -> list[BillReportSpeakerRow]:
        statement = (
            select(
                BillReportSpeaker.id,
                BillReportSpeaker.speech_count,
                BillReportSpeaker.first_ordinal,
                BillReportSpeaker.printed_speaker,
                BillReportSpeaker.sprs_report_id,
                BillReportSpeaker.speaker_id,
            )
            .where(col(BillReportSpeaker.sprs_report_id).in_(sprs_report_ids))
            .order_by(
                BillReportSpeaker.sprs_report_id,
                BillReportSpeaker.first_ordinal,
                BillReportSpeaker.speaker_id,
            )
        )
        return [
            BillReportSpeakerRow(*row) for row in self.session.exec(statement).all()
        ]

    def delete_by_sprs_report_ids(self, sprs_report_ids: list[str]) -> int:
        statement = delete(BillReportSpeaker).where(
            col(BillReportSpeaker.sprs_report_id).in_(sprs_report_ids)
        )

        return self.session.exec(statement).rowcount

    def delete_all(self) -> int:
        statement = delete(BillReportSpeaker)

        return self.session.exec(statement).rowcount

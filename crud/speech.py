from sqlmodel import Session, select

from database.report import Report
from database.speech import Speech


class CRUDSpeech:
    def __init__(self, session: Session):
        self.session = session

    def create(self, speech: Speech) -> None:
        self.session.add(speech)
        self.session.commit()

    def create_many(self, speeches: list[Speech]) -> None:
        self.session.add_all(speeches)
        self.session.commit()

    def get_report_ids_with_speeches(self) -> set[int]:
        return set(self.session.exec(select(Speech.report_id).distinct()).all()) - {None}

    def get_speakers_with_report_type(self) -> list[tuple[str, str, int]]:
        rows = self.session.exec(
            select(Speech.speaker, Report.report_type, Report.parliament_number)
            .join(Report, Report.id == Speech.report_id)
            .where(Speech.speaker.is_not(None))
        ).all()
        return list(rows)

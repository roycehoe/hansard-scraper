from sqlmodel import Session, select

from database.speech import Speech


class CRUDSpeech:
    def __init__(self, session: Session):
        self.session = session

    def create(self, speech: Speech) -> None:
        self.session.add(speech)
        self.session.commit()

    def get_report_ids_with_speeches(self) -> set[int]:
        return set(self.session.exec(select(Speech.report_id).distinct()).all()) - {None}

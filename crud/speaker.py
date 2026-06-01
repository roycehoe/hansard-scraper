from sqlmodel import Session, select

from database.speaker import Speaker


class CRUDSpeaker:
    def __init__(self, session: Session):
        self.session = session

    def create(self, speaker: Speaker) -> None:
        self.session.add(speaker)
        self.session.commit()

    def get_all(self) -> list[Speaker]:
        return list(self.session.exec(select(Speaker)).all())

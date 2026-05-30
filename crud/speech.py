from sqlmodel import Session

from database.report import Speech


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


class CRUDSpeech:
    def __init__(self, session: Session):
        self.session = session

    def create_many(self, speeches: list[Speech]) -> None:
        for chunk in _chunks(speeches, 1000):
            self.session.bulk_insert_mappings(Speech, chunk)
        self.session.commit()

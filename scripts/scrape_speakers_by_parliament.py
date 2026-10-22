from sqlmodel import Session

from database.init import engine
from populate.speakers import populate_speakers


def scrape_speakers_by_parliament() -> None:
    with Session(engine) as session:
        populate_speakers(session)


if __name__ == "__main__":
    scrape_speakers_by_parliament()

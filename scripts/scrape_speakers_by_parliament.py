import argparse

from sqlmodel import Session

from database.init import engine
from database.speaker import Speaker
from populate.speakers import populate_speakers
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write


def scrape_speakers_by_parliament(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        populate_speakers(session, is_commit)
        if is_commit:
            vacuum_analyze_written_tables(session, [Speaker.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Store the speakers of every Parliament, from parliament.gov.sg")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    arguments = parser.parse_args()
    scrape_speakers_by_parliament(arguments.commit)

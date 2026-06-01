"""
Scrape all speakers (MPs and Legislative Assembly members) from parliament.gov.sg
and load them into the Speaker table.

Run before populate_speaker_links.
"""
from sqlmodel import Session

from database.init import engine
from populate.speakers import populate_speakers

if __name__ == "__main__":
    with Session(engine) as session:
        populate_speakers(session)

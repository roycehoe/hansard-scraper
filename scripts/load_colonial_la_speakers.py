"""
Load colonial Legislative Assembly members from data/colonial_la_members.json
into the Speaker table.

Idempotent: skips any row where (name, parliament_number) already exists.

Run before populate_speaker_links so these speakers are available for attendance /
speech resolution in colonial-era volumes (1–26, parliament 0 and 1).
"""
import json
from pathlib import Path

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from database.speaker import Speaker

DATA_FILE = Path(__file__).parent.parent / "data" / "colonial_la_members.json"


def load_colonial_la_speakers() -> None:
    records = json.loads(DATA_FILE.read_text())

    with Session(engine) as session:
        crud = CRUDSpeaker(session)
        existing = {(s.name, s.parliament_number) for s in crud.get_all()}

        inserted = 0
        for rec in records:
            key = (rec["name"], rec["parliament_number"])
            if key in existing:
                continue
            crud.create(Speaker(**rec))
            existing.add(key)
            inserted += 1

        print(f"Inserted {inserted} colonial LA speakers ({len(records) - inserted} already existed)")


if __name__ == "__main__":
    load_colonial_la_speakers()

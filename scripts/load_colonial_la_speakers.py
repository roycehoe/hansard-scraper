import json
from pathlib import Path

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from database.speaker import Speaker

_DATA_FILE = Path(__file__).parent.parent / "data" / "colonial_la_members.json"


def load_colonial_la_speakers() -> None:
    records = json.loads(_DATA_FILE.read_text())

    with Session(engine) as session:
        existing = {(speaker.name, speaker.parliament_number) for speaker in CRUDSpeaker(session).get_all()}

        inserted = 0
        for record in records:
            key = (record["name"], record["parliament_number"])
            if key in existing:
                continue
            CRUDSpeaker(session).create(Speaker(**record))
            existing.add(key)
            inserted += 1

        print(f"Inserted {inserted} colonial LA speakers ({len(records) - inserted} already existed)")


if __name__ == "__main__":
    load_colonial_la_speakers()

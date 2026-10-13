"""
Load Governors, the Yang di-Pertuan Negara and Presidents from data/heads_of_state.json into the
Speaker table as non-member rows (is_member false), one row per parliament in which their speeches
appear, so stage 8 can link the Address and the bracketed strings that name them.

Idempotent: a row whose (name, parliament_number) already exists is only marked as a non-member.

Run before populate_speaker_links, after load_colonial_la_speakers.
"""
import json
from pathlib import Path

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from database.speaker import Speaker

DATA_FILE = Path(__file__).parent.parent / "data" / "heads_of_state.json"


def load_heads_of_state() -> None:
    records = json.loads(DATA_FILE.read_text())

    with Session(engine) as session:
        crud = CRUDSpeaker(session)
        existing = {(s.name, s.parliament_number): s for s in crud.get_all()}

        inserted = marked = 0
        for rec in records:
            speaker = existing.get((rec["name"], rec["parliament_number"]))
            if speaker is None:
                crud.create(Speaker(**rec, party="Non-partisan", is_legislative_assembly=False, is_member=False))
                inserted += 1
            elif speaker.is_member:
                speaker.is_member = False
                crud.update(speaker)
                marked += 1

        print(f"Inserted {inserted} head-of-state speakers, marked {marked} existing rows as non-members")


if __name__ == "__main__":
    load_heads_of_state()

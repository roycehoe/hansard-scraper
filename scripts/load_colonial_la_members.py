"""
Load colonial Legislative Assembly members from data/colonial_la_members.json
into the Mp table.

Idempotent: skips any row where (name, parliament_number) already exists.

Run before populate_mp_links so these MPs are available for attendance / speech
resolution in colonial-era volumes (1–26, parliament 0 and 1).
"""
import json
from pathlib import Path

from sqlmodel import Session, select

from database.init import engine
from database.mp import Mp

DATA_FILE = Path(__file__).parent.parent / "data" / "colonial_la_members.json"


def load_colonial_la_members() -> None:
    records = json.loads(DATA_FILE.read_text())

    with Session(engine) as session:
        existing = {
            (mp.name, mp.parliament_number)
            for mp in session.exec(select(Mp)).all()
        }

        inserted = 0
        for rec in records:
            key = (rec["name"], rec["parliament_number"])
            if key in existing:
                continue
            session.add(Mp(**rec))
            existing.add(key)
            inserted += 1

        session.commit()
        print(f"Inserted {inserted} colonial LA members ({len(records) - inserted} already existed)")


if __name__ == "__main__":
    load_colonial_la_members()

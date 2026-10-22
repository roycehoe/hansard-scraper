import json
from pathlib import Path

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from database.speaker import Speaker
from logs import logger

_DATA_DIRECTORY = Path(__file__).parent.parent / "data"
_DATA_FILES = (_DATA_DIRECTORY / "colonial_la_members.json", _DATA_DIRECTORY / "unscraped_members.json")


def load_colonial_la_speakers() -> None:
    records = [record for data_file in _DATA_FILES for record in json.loads(data_file.read_text())]

    with Session(engine) as session:
        stored_keys = {(speaker.name, speaker.parliament_number) for speaker in CRUDSpeaker(session).get_all()}

        inserted = 0
        for record in records:
            speaker_key = (record["name"], record["parliament_number"])
            if speaker_key in stored_keys:
                continue
            CRUDSpeaker(session).create(Speaker(**record))
            stored_keys.add(speaker_key)
            inserted += 1

        logger.info(f"Inserted {inserted} hand-typed speakers ({len(records) - inserted} already existed)")


if __name__ == "__main__":
    load_colonial_la_speakers()

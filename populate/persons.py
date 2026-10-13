import json
from pathlib import Path

from sqlmodel import Session

from crud.person import CRUDPerson
from crud.speaker import CRUDSpeaker
from database.person import Person
from logs import logger
from services.person import Decision, cluster_speakers

DECISIONS_FILE = Path(__file__).parent.parent / "data" / "person_decisions.json"


def _load_decisions() -> list[Decision]:
    return [
        Decision(
            members=[(member["name"], member["parliament_number"]) for member in entry["members"]],
            decision=entry["decision"],
            person_name=entry.get("person_name"),
        )
        for entry in json.loads(DECISIONS_FILE.read_text())
    ]


def populate_persons(session: Session) -> None:
    """Give every speaker row a person. A cluster that already holds a person keeps it (the lowest id
    when it holds several); a cluster with none gets a new one. Rerunning with unchanged input writes nothing."""
    crud_speaker, crud_person = CRUDSpeaker(session), CRUDPerson(session)
    speakers = crud_speaker.get_all()
    result = cluster_speakers(speakers, _load_decisions())
    for conflict in result.conflicts:
        logger.warning(f"Person: refused union, {conflict}")

    created = 0
    updates: dict[int, int] = {}
    for cluster, name, basis in zip(result.clusters, result.names, result.bases):
        existing_person_ids = sorted({speaker.person_id for speaker in cluster if speaker.person_id is not None})
        if len(existing_person_ids) > 1:
            logger.warning(f"Person: cluster {name!r} spans persons {existing_person_ids}; keeping {existing_person_ids[0]}")
        person_id = existing_person_ids[0] if existing_person_ids else crud_person.create(Person(canonical_name=name, basis=basis))
        created += not existing_person_ids
        updates.update({speaker.id: person_id for speaker in cluster if speaker.person_id != person_id})
    crud_speaker.set_person_ids_bulk(updates)
    session.commit()
    logger.info(
        f"Person: {len(result.clusters)} persons for {len(speakers)} speaker rows; "
        f"{created} created, {len(updates)} speaker rows updated, {len(result.conflicts)} refused unions"
    )

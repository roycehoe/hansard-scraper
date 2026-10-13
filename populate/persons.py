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
            members=[(m["name"], m["parliament_number"]) for m in entry["members"]],
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
        existing = sorted({s.person_id for s in cluster if s.person_id is not None})
        if len(existing) > 1:
            logger.warning(f"Person: cluster {name!r} spans persons {existing}; keeping {existing[0]}")
        person_id = existing[0] if existing else crud_person.create(Person(canonical_name=name, basis=basis))
        created += not existing
        updates.update({s.id: person_id for s in cluster if s.person_id != person_id})
    crud_speaker.set_person_ids_bulk(updates)
    session.commit()
    logger.info(
        f"Person: {len(result.clusters)} persons for {len(speakers)} speaker rows; "
        f"{created} created, {len(updates)} speaker rows updated, {len(result.conflicts)} refused unions"
    )

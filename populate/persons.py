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
    # NOTE: a cluster that already holds a person keeps it, the lowest id when it holds several.
    # A cluster with none gets a new person, so rerunning with unchanged input writes nothing.
    speakers = CRUDSpeaker(session).get_all()
    cluster_result = cluster_speakers(speakers, _load_decisions())
    for conflict in cluster_result.conflicts:
        logger.warning(f"Person: refused union, {conflict}")

    created = 0
    speaker_id_to_person_id: dict[int, int] = {}
    for cluster, name, basis in zip(cluster_result.clusters, cluster_result.names, cluster_result.bases):
        existing_person_ids = sorted({speaker.person_id for speaker in cluster if speaker.person_id is not None})
        if len(existing_person_ids) > 1:
            logger.warning(f"Person: cluster {name!r} spans persons {existing_person_ids}; keeping {existing_person_ids[0]}")
        person_id = existing_person_ids[0] if existing_person_ids else CRUDPerson(session).create(Person(canonical_name=name, basis=basis))
        created += not existing_person_ids
        speaker_id_to_person_id.update({speaker.id: person_id for speaker in cluster if speaker.person_id != person_id})
    CRUDSpeaker(session).set_person_ids_bulk(speaker_id_to_person_id)
    session.commit()
    logger.info(
        f"Person: {len(cluster_result.clusters)} persons for {len(speakers)} speaker rows; "
        f"{created} created, {len(speaker_id_to_person_id)} speaker rows updated, {len(cluster_result.conflicts)} refused unions"
    )

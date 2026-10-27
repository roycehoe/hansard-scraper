from sqlmodel import Session

from crud.person import CRUDPerson
from crud.speaker import CRUDSpeaker
from database.person import Person
from logs import logger
from services.person import cluster_speakers
from utils.data_files import get_person_decisions


def populate_persons(session: Session) -> None:
    speakers = CRUDSpeaker(session).get_all()
    person_id_to_person = {person.id: person for person in CRUDPerson(session).get_all()}
    cluster_result = cluster_speakers(speakers, get_person_decisions())
    for conflict in cluster_result.conflicts:
        logger.warning(f"Person: refused union, {conflict}")

    created = 0
    renamed = 0
    basis_changed = 0
    speaker_id_to_person_id: dict[int, int] = {}
    for person_cluster in cluster_result.clusters:
        existing_person_ids = sorted({speaker.person_id for speaker in person_cluster.memberships if speaker.person_id is not None})
        if len(existing_person_ids) > 1:
            logger.warning(f"Person: cluster {person_cluster.canonical_name!r} spans persons {existing_person_ids}; keeping {existing_person_ids[0]}")
        if existing_person_ids:
            person_id = existing_person_ids[0]
        else:
            person_id = CRUDPerson(session).create(Person(canonical_name=person_cluster.canonical_name, basis=person_cluster.basis))
            created += 1
        person = person_id_to_person.get(person_id)
        if person is not None and person.canonical_name != person_cluster.canonical_name:
            logger.info(f"Person {person_id}: {person.canonical_name!r} -> {person_cluster.canonical_name!r}")
            CRUDPerson(session).set_canonical_name(person, person_cluster.canonical_name)
            renamed += 1
        if person is not None and person.basis != person_cluster.basis:
            logger.info(f"Person {person_id}: basis {person.basis!r} -> {person_cluster.basis!r}")
            CRUDPerson(session).set_basis(person, person_cluster.basis)
            basis_changed += 1
        speaker_id_to_person_id.update({speaker.id: person_id for speaker in person_cluster.memberships if speaker.person_id != person_id})
    CRUDSpeaker(session).set_person_ids_bulk(speaker_id_to_person_id)
    session.commit()
    logger.info(
        f"Person: {len(cluster_result.clusters)} persons for {len(speakers)} speaker rows; "
        f"{created} created, {renamed} renamed, {basis_changed} with a new basis, {len(speaker_id_to_person_id)} speaker rows updated, {len(cluster_result.conflicts)} refused unions"
    )

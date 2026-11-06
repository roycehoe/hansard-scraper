from sqlmodel import Session

from crud.person import CRUDPerson
from crud.person_name_spelling import CRUDPersonNameSpelling
from crud.speaker import CRUDSpeaker
from database.person import Person
from database.person_name_spelling import PersonNameSpelling
from logs import logger
from services.person import Key, build_person_name_spellings, cluster_speakers
from utils.data_files import get_person_decisions, get_person_name_spellings


def _replace_person_name_spellings(
    session: Session, person_name_spellings: list[PersonNameSpelling]
) -> int:
    stored_rows = [
        stored.model_dump(exclude={"id"})
        for stored in CRUDPersonNameSpelling(session).get_all()
    ]
    planned_rows = [
        planned.model_dump(exclude={"id"})
        for planned in sorted(
            person_name_spellings,
            key=lambda spelling: (spelling.person_id, spelling.ordinal),
        )
    ]
    if planned_rows == stored_rows:
        return 0
    CRUDPersonNameSpelling(session).delete_all()
    CRUDPersonNameSpelling(session).create_many(person_name_spellings)
    return len(person_name_spellings)


def populate_persons(session: Session) -> None:
    speakers = CRUDSpeaker(session).get_all()
    person_id_to_person = {
        person.id: person for person in CRUDPerson(session).get_all()
    }
    cluster_result = cluster_speakers(speakers, get_person_decisions())
    for conflict in cluster_result.conflicts:
        logger.warning(f"Person: refused union, {conflict}")

    created = 0
    renamed = 0
    basis_changed = 0
    speaker_id_to_person_id: dict[int, int] = {}
    key_to_person_id: dict[Key, int] = {}
    person_id_to_canonical_name: dict[int, str] = {}
    for person_cluster in cluster_result.clusters:
        existing_person_ids = sorted(
            {
                speaker.person_id
                for speaker in person_cluster.memberships
                if speaker.person_id is not None
            }
        )
        if len(existing_person_ids) > 1:
            logger.warning(
                f"Person: cluster {person_cluster.canonical_name!r} spans persons {existing_person_ids}; keeping {existing_person_ids[0]}"
            )
        if existing_person_ids:
            person_id = existing_person_ids[0]
        else:
            person_id = CRUDPerson(session).create(
                Person(
                    canonical_name=person_cluster.canonical_name,
                    basis=person_cluster.basis,
                )
            )
            created += 1
        person = person_id_to_person.get(person_id)
        if (
            person is not None
            and person.canonical_name != person_cluster.canonical_name
        ):
            logger.info(
                f"Person {person_id}: {person.canonical_name!r} -> {person_cluster.canonical_name!r}"
            )
            CRUDPerson(session).set_canonical_name(
                person, person_cluster.canonical_name
            )
            renamed += 1
        if person is not None and person.basis != person_cluster.basis:
            logger.info(
                f"Person {person_id}: basis {person.basis!r} -> {person_cluster.basis!r}"
            )
            CRUDPerson(session).set_basis(person, person_cluster.basis)
            basis_changed += 1
        speaker_id_to_person_id.update(
            {
                speaker.id: person_id
                for speaker in person_cluster.memberships
                if speaker.person_id != person_id
            }
        )
        key_to_person_id.update(
            {
                (speaker.name, speaker.parliament_number): person_id
                for speaker in person_cluster.memberships
            }
        )
        person_id_to_canonical_name[person_id] = person_cluster.canonical_name
    CRUDSpeaker(session).set_person_ids_bulk(speaker_id_to_person_id)
    name_spellings_written = _replace_person_name_spellings(
        session,
        build_person_name_spellings(
            get_person_name_spellings(), key_to_person_id, person_id_to_canonical_name
        ),
    )
    session.commit()
    logger.info(
        f"Person: {len(cluster_result.clusters)} persons for {len(speakers)} speaker rows; "
        f"{created} created, {renamed} renamed, {basis_changed} with a new basis, {len(speaker_id_to_person_id)} speaker rows updated, {name_spellings_written} name spellings written, {len(cluster_result.conflicts)} refused unions"
    )

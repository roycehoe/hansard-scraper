import argparse
import json
from pathlib import Path

from sqlmodel import Session

from crud.party_affiliation import CRUDPartyAffiliation
from crud.speaker import CRUDSpeaker
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.party_affiliation import MembershipPartyAffiliations
from services.party_affiliation import (
    build_party_affiliations,
    get_unstored_party_affiliations,
)
from settings import settings
from utils.write_target import validate_can_write

_PARTY_AFFILIATIONS_FILE = Path(__file__).parent.parent / "data" / "party_affiliations.json"


def load_party_affiliations(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    memberships = [MembershipPartyAffiliations.model_validate(record) for record in json.loads(_PARTY_AFFILIATIONS_FILE.read_text())]
    with Session(engine) as session:
        party_affiliations = build_party_affiliations(memberships, CRUDSpeaker(session).get_all())
        speaker_ids = [party_affiliation.speaker_id for party_affiliation in party_affiliations]
        unstored_party_affiliations = get_unstored_party_affiliations(party_affiliations, CRUDPartyAffiliation(session).get_by_speaker_ids(speaker_ids))
        for party_affiliation in unstored_party_affiliations:
            logger.info(
                f"Insert speaker {party_affiliation.speaker_id}: {party_affiliation.party!r} "
                f"from {party_affiliation.started_on} ({party_affiliation.started_on_precision}), "
                f"upper bound {party_affiliation.is_started_on_upper_bound}"
            )
        logger.info(
            f"Plan: {len(unstored_party_affiliations)} rows to insert, "
            f"{len(party_affiliations) - len(unstored_party_affiliations)} already stored"
        )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        CRUDPartyAffiliation(session).add_many(unstored_party_affiliations)
        session.expire_all()
        if get_unstored_party_affiliations(party_affiliations, CRUDPartyAffiliation(session).get_by_speaker_ids(speaker_ids)):
            raise HansardWriteCheckError("Party affiliations are not stored after the insert")
        session.commit()
        logger.info(f"Committed: {len(unstored_party_affiliations)} rows inserted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Store the dated party history of data/party_affiliations.json, skipping the rows already stored")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    arguments = parser.parse_args()
    load_party_affiliations(arguments.commit)

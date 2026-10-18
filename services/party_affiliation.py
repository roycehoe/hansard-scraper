from itertools import pairwise

from database.party_affiliation import PartyAffiliation
from database.speaker import Speaker
from exceptions import HansardPartyAffiliationError, HansardWriteCheckError
from schemas.party_affiliation import MembershipPartyAffiliations


def _get_content(party_affiliation: PartyAffiliation) -> dict[str, object]:
    return party_affiliation.model_dump(exclude={"id"})


def _get_validated_speaker(membership: MembershipPartyAffiliations, speakers: list[Speaker]) -> Speaker:
    membership_label = f"{membership.name!r}, Parliament {membership.parliament_number}"
    matching_speakers = [
        speaker for speaker in speakers if speaker.name == membership.name and speaker.parliament_number == membership.parliament_number
    ]
    if len(matching_speakers) == 0:
        raise HansardPartyAffiliationError(f"No speaker row for {membership_label}")
    if len(matching_speakers) > 1:
        raise HansardPartyAffiliationError(f"{len(matching_speakers)} speaker rows for {membership_label}")
    speaker = matching_speakers[0]
    if membership.affiliations[0].party != speaker.party:
        raise HansardPartyAffiliationError(
            f"{membership_label}: first span holds {membership.affiliations[0].party!r}, the stored party is {speaker.party!r}"
        )
    return speaker


def _validate_can_chain_spans(membership: MembershipPartyAffiliations) -> None:
    membership_label = f"{membership.name!r}, Parliament {membership.parliament_number}"
    for previous_span, span in pairwise(membership.affiliations):
        if span.started_on <= previous_span.started_on:
            raise HansardPartyAffiliationError(
                f"{membership_label}: span of {span.party!r} starts on {span.started_on}, not after the span before it on {previous_span.started_on}"
            )
        if span.party == previous_span.party:
            raise HansardPartyAffiliationError(f"{membership_label}: two consecutive spans hold {span.party!r}")


def build_party_affiliations(memberships: list[MembershipPartyAffiliations], speakers: list[Speaker]) -> list[PartyAffiliation]:
    party_affiliations = []
    for membership in memberships:
        speaker = _get_validated_speaker(membership, speakers)
        _validate_can_chain_spans(membership)
        party_affiliations.extend(
            PartyAffiliation(
                party=span.party,
                started_on=span.started_on,
                started_on_precision=span.started_on_precision,
                event=span.event,
                source_url=span.source_url,
                speaker_id=speaker.id,
            )
            for span in membership.affiliations
        )
    return party_affiliations


def get_unstored_party_affiliations(
    party_affiliations: list[PartyAffiliation], stored_party_affiliations: list[PartyAffiliation]
) -> list[PartyAffiliation]:
    planned_contents = [_get_content(party_affiliation) for party_affiliation in party_affiliations]
    stored_contents = [_get_content(stored_party_affiliation) for stored_party_affiliation in stored_party_affiliations]
    for stored_party_affiliation, stored_content in zip(stored_party_affiliations, stored_contents, strict=True):
        if stored_content not in planned_contents:
            raise HansardWriteCheckError(
                f"Speaker {stored_party_affiliation.speaker_id} holds a stored span of {stored_party_affiliation.party!r} "
                f"from {stored_party_affiliation.started_on} that the file does not"
            )
    return [party_affiliation for party_affiliation, content in zip(party_affiliations, planned_contents, strict=True) if content not in stored_contents]

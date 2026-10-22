import re
from dataclasses import dataclass
from operator import attrgetter

from database.speaker import Speaker
from enums import LegislativeAssemblyFlag
from exceptions import HansardGatewayError, HansardWriteCheckError
from schemas.head_of_state import HeadOfStateResult
from schemas.parliament_member_list_response import ParliamentMemberListResponse
from schemas.speaker import SpeakerResult
from schemas.speaker_override import PartyOverride, SpeakerOverrides
from utils.speaker_resolution_constants import COLONIAL_PARLIAMENT_NUMBER

_CURLY_APOSTROPHE = "\u2019"
_STRAIGHT_APOSTROPHE = "'"
_LOADED_PARLIAMENT_NUMBER = 1
_PARLIAMENT_TITLE_RE = re.compile(r"(\d+)(?:st|nd|rd|th) Parliament")
_NAME_WITH_COMMENT_RE = re.compile(r"^(.*?)\s*\((.+)\)\s*$")


@dataclass(frozen=True)
class PartyChange:
    id: int
    name: str
    parliament_number: int
    party_before: str
    party_after: str


@dataclass(frozen=True)
class ParliamentChange:
    id: int
    name: str
    parliament_number_before: int
    parliament_number_after: int


def normalise_party(party: str) -> str:
    return party.replace(_CURLY_APOSTROPHE, _STRAIGHT_APOSTROPHE)


def _get_parliament_number(parliament_title: str) -> int:
    match = _PARLIAMENT_TITLE_RE.fullmatch(parliament_title)
    if match is None:
        raise HansardGatewayError(f"Member list names an unreadable Parliament {parliament_title!r}")
    return int(match.group(1))


def build_speaker_results(parliament_member_list_response: ParliamentMemberListResponse) -> list[SpeakerResult]:
    session_id_to_parliament_number = {
        session_id: _get_parliament_number(parliament.title)
        for parliament in parliament_member_list_response.options
        for session_id in parliament.parliament_sessions
    }
    speaker_results = []
    for member in parliament_member_list_response.mps.data:
        full_name = member.full_name.strip()
        match = _NAME_WITH_COMMENT_RE.match(full_name)
        name = full_name if match is None else match.group(1).strip()
        comments = None if match is None else match.group(2).strip()
        try:
            parliament_numbers = {
                session_id_to_parliament_number[session.parliament_sessions_id] for session in member.parliament_session
            }
        except KeyError as error:
            raise HansardGatewayError(f"Member list gives {full_name!r} a session of no listed Parliament") from error
        speaker_results.extend(
            SpeakerResult(
                name=name,
                party=member.party_affliation.strip(),
                is_legislative_assembly=member.legislative_assembly == LegislativeAssemblyFlag.YES,
                parliament_number=parliament_number,
                comments=comments,
            )
            for parliament_number in parliament_numbers
        )
    return sorted(speaker_results, key=attrgetter("parliament_number"))


def get_name_parliament_to_is_legislative_assembly(speaker_overrides: SpeakerOverrides) -> dict[tuple[str, int], bool]:
    return {
        (override.name, override.parliament_number): override.is_legislative_assembly
        for override in speaker_overrides.legislative_assembly_overrides
    }


def get_name_parliament_to_party(speaker_overrides: SpeakerOverrides) -> dict[tuple[str, int], str]:
    return {(override.name, override.parliament_number): override.party for override in speaker_overrides.party_overrides}


def build_speaker(
    speaker_result: SpeakerResult,
    name_parliament_to_is_legislative_assembly: dict[tuple[str, int], bool],
    name_parliament_to_party: dict[tuple[str, int], str],
) -> Speaker:
    key = (speaker_result.name, speaker_result.parliament_number)
    is_legislative_assembly = name_parliament_to_is_legislative_assembly.get(key, speaker_result.is_legislative_assembly)
    party = normalise_party(name_parliament_to_party.get(key, speaker_result.party))
    return Speaker(
        **speaker_result.model_dump(exclude={"is_legislative_assembly", "party"}),
        party=party,
        is_legislative_assembly=is_legislative_assembly,
    )


def get_party_changes(
    speakers: list[Speaker], overrides: list[PartyOverride], colonial_members: list[SpeakerResult]
) -> list[PartyChange]:
    key_to_speaker = {(speaker.name, speaker.parliament_number): speaker for speaker in speakers}
    name_parliament_to_party = {(member.name, member.parliament_number): member.party for member in colonial_members}
    for override in overrides:
        speaker = key_to_speaker.get((override.name, override.parliament_number))
        if speaker is None:
            raise HansardWriteCheckError(f"No speaker row for override {override.name!r}, Parliament {override.parliament_number}")
        if speaker.party != override.source_party and speaker.party != override.party:
            raise HansardWriteCheckError(f"Speaker {speaker.id}: stored party is neither the source value nor the override")
        name_parliament_to_party[(override.name, override.parliament_number)] = override.party
    for member in colonial_members:
        if (member.name, member.parliament_number) not in key_to_speaker:
            raise HansardWriteCheckError(f"No speaker row for colonial member {member.name!r}, Parliament {member.parliament_number}")
    party_changes = []
    for speaker in speakers:
        party_after = normalise_party(name_parliament_to_party.get((speaker.name, speaker.parliament_number), speaker.party))
        if party_after == speaker.party:
            continue
        party_changes.append(PartyChange(speaker.id, speaker.name, speaker.parliament_number, speaker.party, party_after))
    return party_changes


def get_parliament_changes(
    speakers: list[Speaker], colonial_members: list[SpeakerResult], heads_of_state: list[HeadOfStateResult]
) -> list[ParliamentChange]:
    key_to_speaker = {(speaker.name, speaker.parliament_number): speaker for speaker in speakers}
    assembly_names = [member.name for member in colonial_members if member.parliament_number == COLONIAL_PARLIAMENT_NUMBER]
    assembly_names += [head.name for head in heads_of_state if head.parliament_number == COLONIAL_PARLIAMENT_NUMBER]
    parliament_changes = []
    for name in assembly_names:
        assembly_speaker = key_to_speaker.get((name, COLONIAL_PARLIAMENT_NUMBER))
        loaded_speaker = key_to_speaker.get((name, _LOADED_PARLIAMENT_NUMBER))
        if assembly_speaker is not None and loaded_speaker is not None:
            raise HansardWriteCheckError(f"Speaker rows for {name!r} exist in Parliament {COLONIAL_PARLIAMENT_NUMBER} and {_LOADED_PARLIAMENT_NUMBER}")
        if assembly_speaker is not None:
            continue
        if loaded_speaker is None:
            raise HansardWriteCheckError(f"No speaker row for {name!r} in Parliament {COLONIAL_PARLIAMENT_NUMBER} or {_LOADED_PARLIAMENT_NUMBER}")
        parliament_changes.append(
            ParliamentChange(loaded_speaker.id, name, _LOADED_PARLIAMENT_NUMBER, COLONIAL_PARLIAMENT_NUMBER)
        )
    return parliament_changes

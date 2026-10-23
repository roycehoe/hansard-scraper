import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from database.speaker import Speaker
from enums import PersonDecisionKind
from exceptions import HansardDataFileError
from schemas.person_decision import PersonDecision, PersonDecisionMember
from utils.names import (
    invert_to_natural,
    period_normalize,
    strip_bin,
    strip_title,
)

Key = tuple[str, int]

_TRAILING_DECORATION_RE = re.compile(r"\s+(?:BPM|BBM)$")


@dataclass(frozen=True)
class PersonCluster:
    memberships: list[Speaker]
    canonical_name: str
    basis: str


@dataclass(frozen=True)
class ClusterResult:
    clusters: list[PersonCluster] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def normalize_person_name(name: str) -> str:
    natural = invert_to_natural(name) or name
    return period_normalize(strip_bin(strip_title(natural)))


class _SpeakerClusters:
    def __init__(self, speakers: list[Speaker], distinct: set[frozenset[int]]):
        self.parent: dict[int, int] = {speaker.id: speaker.id for speaker in speakers}
        self.members: dict[int, list[Speaker]] = {speaker.id: [speaker] for speaker in speakers}
        self.distinct: set[frozenset[int]] = distinct
        self.basis: dict[int, str] = {}

    def find(self, speaker_id: int) -> int:
        while self.parent[speaker_id] != speaker_id:
            speaker_id = self.parent[speaker_id]
        return speaker_id

    def get_refusal_reason(self, left_id: int, right_id: int) -> Optional[str]:
        left, right = self.members[left_id], self.members[right_id]
        left_slots = {(speaker.parliament_number, speaker.is_legislative_assembly, speaker.is_member) for speaker in left}
        right_slots = {(speaker.parliament_number, speaker.is_legislative_assembly, speaker.is_member) for speaker in right}
        if left_slots & right_slots:
            return "same parliament"
        if any(
            frozenset((left_speaker.id, right_speaker.id)) in self.distinct
            for left_speaker in left
            for right_speaker in right
        ):
            return "distinct decision"
        return None

    def union(self, left_id: int, right_id: int, basis: str) -> Optional[str]:
        left_id, right_id = self.find(left_id), self.find(right_id)
        if left_id == right_id:
            return None
        if (refusal_reason := self.get_refusal_reason(left_id, right_id)) is not None:
            return refusal_reason
        self.parent[right_id] = left_id
        self.members[left_id] += self.members.pop(right_id)
        self.basis[left_id] = basis
        return None


def _get_canonical_name(cluster: list[Speaker]) -> str:
    name_to_count = Counter(speaker.name for speaker in cluster)
    most_common_name = max(
        cluster, key=lambda speaker: (name_to_count[speaker.name], speaker.parliament_number, len(speaker.name))
    ).name
    return _TRAILING_DECORATION_RE.sub("", invert_to_natural(most_common_name) or most_common_name)


def _get_member_keys(members: list[PersonDecisionMember]) -> list[Key]:
    return [(member.name, member.parliament_number) for member in members]


def cluster_speakers(speakers: list[Speaker], decisions: list[PersonDecision]) -> ClusterResult:
    key_to_speaker = {(speaker.name, speaker.parliament_number): speaker for speaker in speakers}
    for decision in decisions:
        for key in _get_member_keys(decision.members):
            try:
                key_to_speaker[key]
            except KeyError as error:
                raise HansardDataFileError(f"data/person_decisions.json names no speaker row: {key}") from error
    distinct = {
        frozenset((key_to_speaker[left_key].id, key_to_speaker[right_key].id))
        for decision in decisions if decision.decision == PersonDecisionKind.DISTINCT
        for left_key in _get_member_keys(decision.members) for right_key in _get_member_keys(decision.members) if left_key != right_key
    }
    clusters = _SpeakerClusters(speakers, distinct)
    cluster_result = ClusterResult()
    speaker_id_to_person_name: dict[int, str] = {}

    for decision in decisions:
        if decision.decision != PersonDecisionKind.MERGE:
            continue
        member_keys = _get_member_keys(decision.members)
        first, *rest = (key_to_speaker[key].id for key in member_keys)
        for other in rest:
            if (refusal_reason := clusters.union(first, other, "review:merge")) is not None:
                raise HansardDataFileError(f"data/person_decisions.json merge decision refused ({refusal_reason}): {member_keys}")
        if decision.person_name:
            speaker_id_to_person_name[first] = decision.person_name

    for decision in decisions:
        if decision.decision != PersonDecisionKind.NAME:
            continue
        speaker_id_to_person_name[key_to_speaker[_get_member_keys(decision.members)[0]].id] = decision.person_name

    for basis, key_function in (
        ("auto:exact", lambda speaker: speaker.name),
        ("auto:normalised", lambda speaker: normalize_person_name(speaker.name)),
    ):
        key_to_speaker_ids: dict[str, list[int]] = {}
        for speaker in speakers:
            key_to_speaker_ids.setdefault(key_function(speaker), []).append(speaker.id)
        for key, speaker_ids in key_to_speaker_ids.items():
            for other in speaker_ids[1:]:
                if (refusal_reason := clusters.union(speaker_ids[0], other, basis)) is not None:
                    cluster_result.conflicts.append(f"{basis} {key!r}: {refusal_reason}")

    for root, members in clusters.members.items():
        members = sorted(members, key=lambda speaker: speaker.parliament_number)
        decided = [speaker_id_to_person_name[speaker.id] for speaker in members if speaker.id in speaker_id_to_person_name]
        cluster_result.clusters.append(
            PersonCluster(
                memberships=members,
                canonical_name=decided[0] if decided else _get_canonical_name(members),
                basis=clusters.basis.get(root, "single"),
            )
        )
    return cluster_result

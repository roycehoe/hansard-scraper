import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from database.speaker import Speaker
from utils.names import (
    invert_to_natural,
    period_normalize,
    strip_bin,
    strip_title,
)

Key = tuple[str, int]

_TRAILING_DECORATION_RE = re.compile(r"\s+(?:BPM|BBM)$")


@dataclass(frozen=True)
class Decision:
    members: list[Key]
    decision: str
    person_name: Optional[str] = None


@dataclass
class ClusterResult:
    clusters: list[list[Speaker]] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def normalize_person_name(name: str) -> str:
    natural = invert_to_natural(name) or name
    return period_normalize(strip_bin(strip_title(natural)))


def _get_slot(speaker: Speaker) -> tuple[int, bool, bool]:
    return speaker.parliament_number, speaker.is_legislative_assembly, speaker.is_member


class _SpeakerClusters:
    def __init__(self, speakers: list[Speaker], distinct: set[frozenset[int]]):
        self.parent = {speaker.id: speaker.id for speaker in speakers}
        self.members = {speaker.id: [speaker] for speaker in speakers}
        self.distinct = distinct
        self.basis: dict[int, str] = {}

    def find(self, speaker_id: int) -> int:
        while self.parent[speaker_id] != speaker_id:
            speaker_id = self.parent[speaker_id]
        return speaker_id

    def get_refusal_reason(self, left_id: int, right_id: int) -> Optional[str]:
        left, right = self.members[left_id], self.members[right_id]
        if {_get_slot(speaker) for speaker in left} & {_get_slot(speaker) for speaker in right}:
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
        if refusal_reason := self.get_refusal_reason(left_id, right_id):
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


def cluster_speakers(speakers: list[Speaker], decisions: list[Decision]) -> ClusterResult:
    key_to_speaker = {(speaker.name, speaker.parliament_number): speaker for speaker in speakers}
    for decision in decisions:
        for key in decision.members:
            if key not in key_to_speaker:
                raise ValueError(f"person decision names no speaker row: {key}")
    distinct = {
        frozenset((key_to_speaker[left_key].id, key_to_speaker[right_key].id))
        for decision in decisions if decision.decision == "distinct"
        for left_key in decision.members for right_key in decision.members if left_key != right_key
    }
    clusters = _SpeakerClusters(speakers, distinct)
    cluster_result = ClusterResult()
    speaker_id_to_person_name: dict[int, str] = {}

    for decision in decisions:
        if decision.decision != "merge":
            continue
        first, *rest = (key_to_speaker[key].id for key in decision.members)
        for other in rest:
            if refusal_reason := clusters.union(first, other, "review:merge"):
                raise ValueError(f"merge decision refused ({refusal_reason}): {decision.members}")
        if decision.person_name:
            speaker_id_to_person_name[first] = decision.person_name

    for decision in decisions:
        if decision.decision != "name":
            continue
        speaker_id_to_person_name[key_to_speaker[decision.members[0]].id] = decision.person_name

    for basis, key_function in (
        ("auto:exact", lambda speaker: speaker.name),
        ("auto:normalised", lambda speaker: normalize_person_name(speaker.name)),
    ):
        key_to_speaker_ids: dict[str, list[int]] = {}
        for speaker in speakers:
            key_to_speaker_ids.setdefault(key_function(speaker), []).append(speaker.id)
        for key, speaker_ids in key_to_speaker_ids.items():
            for other in speaker_ids[1:]:
                if refusal_reason := clusters.union(speaker_ids[0], other, basis):
                    cluster_result.conflicts.append(f"{basis} {key!r}: {refusal_reason}")

    for root, members in clusters.members.items():
        members = sorted(members, key=lambda speaker: speaker.parliament_number)
        cluster_result.clusters.append(members)
        decided = [speaker_id_to_person_name[speaker.id] for speaker in members if speaker.id in speaker_id_to_person_name]
        cluster_result.names.append(decided[0] if decided else _get_canonical_name(members))
        cluster_result.bases.append(clusters.basis.get(root, "single"))
    return cluster_result

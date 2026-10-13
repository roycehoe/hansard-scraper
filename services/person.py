"""Group per-parliament Speaker rows into persons (plans/person-identity.md).

Rules, in order: a hand decision from data/person_decisions.json ("merge" joins the listed rows,
"distinct" forbids any join between them), then identical names, then names equal after title,
period, "bin" and inversion normalisation. A person holds at most one row per
(parliament_number, is_legislative_assembly, is_member); a rule that would break that is refused and
reported, and a merge decision that would break it stops the run.
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from database.speaker import Speaker
from services.attendance import (
    _invert_to_natural,
    _period_normalize,
    _strip_bin,
    strip_title,
)

Key = tuple[str, int]  # (name, parliament_number), the natural key of a speaker row


@dataclass
class Decision:
    members: list[Key]
    decision: str  # "merge" or "distinct"
    person_name: Optional[str] = None


@dataclass
class ClusterResult:
    clusters: list[list[Speaker]] = field(default_factory=list)
    names: list[str] = field(default_factory=list)  # canonical name per cluster
    bases: list[str] = field(default_factory=list)  # rule that formed each cluster
    conflicts: list[str] = field(default_factory=list)  # refused unions, for the log


def normalised_name(name: str) -> str:
    natural = _invert_to_natural(name) or name
    return _period_normalize(_strip_bin(strip_title(natural)))


def _get_slot(speaker: Speaker) -> tuple[int, bool, bool]:
    return speaker.parliament_number, speaker.is_legislative_assembly, speaker.is_member


class _SpeakerClusters:
    def __init__(self, speakers: list[Speaker], distinct: set[frozenset[int]]):
        self.parent = {speaker.id: speaker.id for speaker in speakers}
        self.members = {speaker.id: [speaker] for speaker in speakers}
        self.distinct = distinct  # pairs of speaker ids that may never share a person
        self.basis: dict[int, str] = {}

    def find(self, speaker_id: int) -> int:
        while self.parent[speaker_id] != speaker_id:
            speaker_id = self.parent[speaker_id]
        return speaker_id

    def refusal(self, left_id: int, right_id: int) -> Optional[str]:
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
        if refusal_reason := self.refusal(left_id, right_id):
            return refusal_reason
        self.parent[right_id] = left_id
        self.members[left_id] += self.members.pop(right_id)
        self.basis[left_id] = basis
        return None


def _get_canonical_name(cluster: list[Speaker]) -> str:
    counts = Counter(speaker.name for speaker in cluster)
    return max(
        cluster, key=lambda speaker: (counts[speaker.name], speaker.parliament_number, len(speaker.name))
    ).name


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
    speaker_id_to_person_name: dict[int, str] = {}  # a merged row's id -> the decision's person name

    for decision in decisions:
        if decision.decision != "merge":
            continue
        first, *rest = (key_to_speaker[key].id for key in decision.members)
        for other in rest:
            if refusal_reason := clusters.union(first, other, "review:merge"):
                raise ValueError(f"merge decision refused ({refusal_reason}): {decision.members}")
        if decision.person_name:
            speaker_id_to_person_name[first] = decision.person_name

    for basis, key_function in (
        ("auto:exact", lambda speaker: speaker.name),
        ("auto:normalised", lambda speaker: normalised_name(speaker.name)),
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

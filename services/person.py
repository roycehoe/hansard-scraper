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


def _slot(speaker: Speaker) -> tuple[int, bool, bool]:
    return speaker.parliament_number, speaker.is_legislative_assembly, speaker.is_member


class _Union:
    def __init__(self, speakers: list[Speaker], distinct: set[frozenset[int]]):
        self.parent = {s.id: s.id for s in speakers}
        self.members = {s.id: [s] for s in speakers}
        self.distinct = distinct  # pairs of speaker ids that may never share a person
        self.basis: dict[int, str] = {}

    def find(self, speaker_id: int) -> int:
        while self.parent[speaker_id] != speaker_id:
            speaker_id = self.parent[speaker_id]
        return speaker_id

    def refusal(self, a: int, b: int) -> Optional[str]:
        left, right = self.members[a], self.members[b]
        if {_slot(s) for s in left} & {_slot(s) for s in right}:
            return "same parliament"
        if any(frozenset((x.id, y.id)) in self.distinct for x in left for y in right):
            return "distinct decision"
        return None

    def union(self, a: int, b: int, basis: str) -> Optional[str]:
        a, b = self.find(a), self.find(b)
        if a == b:
            return None
        if why := self.refusal(a, b):
            return why
        self.parent[b] = a
        self.members[a] += self.members.pop(b)
        self.basis[a] = basis
        return None


def _canonical_name(cluster: list[Speaker]) -> str:
    counts = Counter(s.name for s in cluster)
    return max(cluster, key=lambda s: (counts[s.name], s.parliament_number, len(s.name))).name


def cluster_speakers(speakers: list[Speaker], decisions: list[Decision]) -> ClusterResult:
    by_key = {(s.name, s.parliament_number): s for s in speakers}
    for decision in decisions:
        for key in decision.members:
            if key not in by_key:
                raise ValueError(f"person decision names no speaker row: {key}")
    distinct = {
        frozenset((by_key[a].id, by_key[b].id))
        for d in decisions if d.decision == "distinct"
        for a in d.members for b in d.members if a != b
    }
    union = _Union(speakers, distinct)
    result = ClusterResult()
    merged_names: dict[int, str] = {}  # a merged row's id -> the decision's person name

    for decision in decisions:
        if decision.decision != "merge":
            continue
        first, *rest = (by_key[k].id for k in decision.members)
        for other in rest:
            if why := union.union(first, other, "review:merge"):
                raise ValueError(f"merge decision refused ({why}): {decision.members}")
        if decision.person_name:
            merged_names[first] = decision.person_name

    for basis, key_of in (("auto:exact", lambda s: s.name), ("auto:normalised", lambda s: normalised_name(s.name))):
        groups: dict[str, list[int]] = {}
        for s in speakers:
            groups.setdefault(key_of(s), []).append(s.id)
        for key, ids in groups.items():
            for other in ids[1:]:
                if why := union.union(ids[0], other, basis):
                    result.conflicts.append(f"{basis} {key!r}: {why}")

    for root, members in union.members.items():
        members = sorted(members, key=lambda s: s.parliament_number)
        result.clusters.append(members)
        decided = [merged_names[s.id] for s in members if s.id in merged_names]
        result.names.append(decided[0] if decided else _canonical_name(members))
        result.bases.append(union.basis.get(root, "single"))
    return result

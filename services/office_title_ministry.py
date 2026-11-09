import re
from dataclasses import dataclass
from typing import Optional

from enums import OfficeTitleMinistrySource

_SPACE_RUN_RE = re.compile(r"\s+")
_LEADING_THE = "The "
_THE_WORD = "the "
_BRACKET_RE = re.compile(r"\s*\([^)]*\)")
_TITLE_EDGE_CHARACTERS = " ,.;"
_RANK_WORDS_RE = re.compile(r"^(?:(?:Acting|First|Second|Senior)\s+)+")
_LEADING_THE_IN_CLAUSE_RE = re.compile(r"^the\s+")
_CLAUSE_HEAD = (
    r"(?:Deputy Prime Minister|Prime Minister|Coordinating Minister|Co-ordinating Minister"
    r"|Senior Minister of State|Minister of State|Senior Minister|Second Minister|Acting Minister"
    r"|Minister-in-charge|Minister-in-Charge|Minister in charge|Minister"
    r"|Senior Parliamentary Secretary|Parliamentary Secretary|Assistant Minister"
    r"|Leader of the House|Deputy Leader|Government Whip|Deputy Government Whip|Acting Government Whip"
    r"|Ministry of|Attorney|Chief Secretary|Financial Secretary)"
)
_CLAUSE_BOUNDARY_RE = re.compile(
    r"(?:,\s*and\s+|\s+and\s+|,\s+|;\s+(?:and\s+)?)(?=(?:the\s+)?"
    + _CLAUSE_HEAD
    + r"\b)"
)
_ROLE_ONLY_CLAUSES = frozenset(
    {
        "Deputy Prime Minister",
        "Senior Minister",
        "Minister Mentor",
        "Minister",
        "Minister of State",
        "Senior Minister of State",
        "Minister without Portfolio",
        "Leader of the House",
        "Leader of the Opposition",
        "Deputy Leader of the House",
        "Government Whip",
        "Deputy Government Whip",
        "Attorney-General",
        "Chief Minister",
        "Chief Secretary",
        "Financial Secretary",
        "Chairman",
        "Assistant Minister",
        "Parliamentary Secretary",
        "Parliamentary Secretary to the Prime Minister",
        "Parliamentary Secretary to the Deputy Prime Minister",
        "Assistant Minister to the Chief Secretary",
    }
)
_CHAIR_CLAUSE_RE = re.compile(
    r"^(?:Honourable\s+)?(?:Mr\.?\s+|Mdm\s+)?(?:(?:First|Second)\s+)?(?:Deputy\s+)?Speaker$",
    re.IGNORECASE,
)
_PORTFOLIO_PREFIX_RE = re.compile(
    r"^(?:Coordinating Minister|Co-ordinating Minister|Minister of State|Minister-in-charge"
    r"|Minister-in-Charge|Minister in charge|Parliamentary Secretary|Assistant Minister|Minister|Ministry)"
    r"\s*,?\s*(?:to the (?:Acting )?Ministers? (?:for|of)|to the (?:Acting )?Ministers?|for|of|in)?\s+(?:the\s+)?(.+)$"
)
_NAME_SEPARATOR_RE = re.compile(r"\s*(?:,\s*and\s+|\s+and\s+|,\s*|;\s*)")


@dataclass(frozen=True)
class OfficeTitlePlacement:
    ministry_name: str
    source: OfficeTitleMinistrySource


def _get_match_title(office_printed: str) -> str:
    return (
        _SPACE_RUN_RE.sub(" ", office_printed)
        .replace("’", "'")
        .strip(_TITLE_EDGE_CHARACTERS)
        .removeprefix(_LEADING_THE)
    )


def _get_clauses(match_title: str) -> list[str]:
    return [
        _LEADING_THE_IN_CLAUSE_RE.sub("", clause.strip(_TITLE_EDGE_CHARACTERS))
        for clause in _CLAUSE_BOUNDARY_RE.split(_BRACKET_RE.sub("", match_title))
    ]


def _get_segmented_names(
    text: str, ministry_names_longest_first: list[str]
) -> Optional[list[str]]:
    if not text:
        return None
    segmented_names: list[str] = []
    position = 0
    while position < len(text):
        if text.startswith(_THE_WORD, position):
            position += len(_THE_WORD)
            continue
        ministry_name = next(
            (
                ministry_name
                for ministry_name in ministry_names_longest_first
                if text.startswith(ministry_name, position)
            ),
            None,
        )
        if ministry_name is None:
            return None
        segmented_names.append(ministry_name)
        position += len(ministry_name)
        if position == len(text):
            break
        separator_match = _NAME_SEPARATOR_RE.match(text, position)
        if separator_match is None:
            return None
        position = separator_match.end()
    return segmented_names


def _get_hand_kept_placements(
    ministry_names: list[str],
) -> list[OfficeTitlePlacement]:
    return [
        OfficeTitlePlacement(ministry_name, OfficeTitleMinistrySource.HAND_KEPT_TITLE)
        for ministry_name in ministry_names
    ]


def _get_clause_placements(
    clause: str,
    ministry_names_longest_first: list[str],
    title_to_ministry_names: dict[str, list[str]],
) -> Optional[list[OfficeTitlePlacement]]:
    clause_without_rank = _RANK_WORDS_RE.sub("", clause)
    hand_kept_ministry_names = title_to_ministry_names.get(clause_without_rank)
    if hand_kept_ministry_names is None:
        hand_kept_ministry_names = title_to_ministry_names.get(clause)
    if hand_kept_ministry_names is not None:
        return _get_hand_kept_placements(hand_kept_ministry_names)
    if clause_without_rank in _ROLE_ONLY_CLAUSES:
        return []
    if _CHAIR_CLAUSE_RE.match(clause_without_rank):
        return []
    segmented_names = _get_segmented_names(
        clause_without_rank, ministry_names_longest_first
    )
    if segmented_names is None:
        portfolio_match = _PORTFOLIO_PREFIX_RE.match(clause_without_rank)
        if portfolio_match is None:
            return None
        segmented_names = _get_segmented_names(
            portfolio_match.group(1), ministry_names_longest_first
        )
    if segmented_names is None:
        return None
    return [
        OfficeTitlePlacement(ministry_name, OfficeTitleMinistrySource.CLOSED_LIST_RULE)
        for ministry_name in segmented_names
    ]


def get_office_title_placement(
    office_printed: str,
    ministry_names_longest_first: list[str],
    title_to_ministry_names: dict[str, list[str]],
) -> Optional[list[OfficeTitlePlacement]]:
    match_title = _get_match_title(office_printed)
    hand_kept_ministry_names = title_to_ministry_names.get(match_title)
    if hand_kept_ministry_names is not None:
        return _get_hand_kept_placements(hand_kept_ministry_names)
    ministry_name_to_placement: dict[str, OfficeTitlePlacement] = {}
    for clause in _get_clauses(match_title):
        clause_placements = _get_clause_placements(
            clause, ministry_names_longest_first, title_to_ministry_names
        )
        if clause_placements is None:
            return None
        for clause_placement in clause_placements:
            ministry_name_to_placement.setdefault(
                clause_placement.ministry_name, clause_placement
            )
    return list(ministry_name_to_placement.values())

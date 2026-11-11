from dataclasses import dataclass
from datetime import date
from typing import Optional

from enums import MinutesDivisionPairing


@dataclass(frozen=True)
class PairableHansardDivision:
    division_id: int
    sitting_date: date
    sprs_report_id: str
    speech_number: int
    speech_ordinal: int
    ayes: Optional[int]
    noes: Optional[int]
    abstentions: Optional[int]


@dataclass(frozen=True)
class PairableMinutesDivision:
    sitting_date: date
    ordinal: int
    ayes: int
    noes: int
    abstentions: Optional[int]


@dataclass(frozen=True)
class DivisionPairing:
    sitting_date: date
    minutes_ordinal: int
    pairing: MinutesDivisionPairing
    division_id: Optional[int]
    hansard_division_ids: tuple[int, ...]


def _is_speech_number_tied(hansard_group: list[PairableHansardDivision]) -> bool:
    speech_number_to_sprs_report_ids: dict[int, set[str]] = {}
    for hansard_division in hansard_group:
        speech_number_to_sprs_report_ids.setdefault(
            hansard_division.speech_number, set()
        ).add(hansard_division.sprs_report_id)
    for sprs_report_ids in speech_number_to_sprs_report_ids.values():
        if len(sprs_report_ids) > 1:
            return True
    return False


def _has_differing_abstentions(
    hansard_group: list[PairableHansardDivision],
    minutes_group: list[PairableMinutesDivision],
) -> bool:
    for hansard_division, minutes_division in zip(hansard_group, minutes_group):
        if hansard_division.abstentions is None:
            continue
        if minutes_division.abstentions is None:
            continue
        if hansard_division.abstentions != minutes_division.abstentions:
            return True
    return False


def _pair_group(
    hansard_group: list[PairableHansardDivision],
    minutes_group: list[PairableMinutesDivision],
) -> list[DivisionPairing]:
    hansard_division_ids = tuple(
        hansard_division.division_id for hansard_division in hansard_group
    )
    if len(hansard_group) == 0:
        return [
            DivisionPairing(
                minutes_division.sitting_date,
                minutes_division.ordinal,
                MinutesDivisionPairing.NO_MATCHING_DIVISION,
                None,
                (),
            )
            for minutes_division in minutes_group
        ]
    if _is_speech_number_tied(hansard_group):
        return [
            DivisionPairing(
                minutes_division.sitting_date,
                minutes_division.ordinal,
                MinutesDivisionPairing.TIED,
                None,
                hansard_division_ids,
            )
            for minutes_division in minutes_group
        ]
    if len(hansard_group) != len(minutes_group):
        return [
            DivisionPairing(
                minutes_division.sitting_date,
                minutes_division.ordinal,
                MinutesDivisionPairing.UNEQUAL_NUMBER,
                None,
                hansard_division_ids,
            )
            for minutes_division in minutes_group
        ]
    if _has_differing_abstentions(hansard_group, minutes_group):
        return [
            DivisionPairing(
                minutes_division.sitting_date,
                minutes_division.ordinal,
                MinutesDivisionPairing.ABSTENTIONS_DIFFER,
                None,
                hansard_division_ids,
            )
            for minutes_division in minutes_group
        ]
    return [
        DivisionPairing(
            minutes_division.sitting_date,
            minutes_division.ordinal,
            MinutesDivisionPairing.PAIRED,
            hansard_division.division_id,
            (hansard_division.division_id,),
        )
        for hansard_division, minutes_division in zip(hansard_group, minutes_group)
    ]


def get_division_pairings(
    hansard_divisions: list[PairableHansardDivision],
    minutes_divisions: list[PairableMinutesDivision],
) -> list[DivisionPairing]:
    group_to_hansard_divisions: dict[
        tuple[date, int, int], list[PairableHansardDivision]
    ] = {}
    for hansard_division in hansard_divisions:
        if hansard_division.ayes is None:
            continue
        if hansard_division.noes is None:
            continue
        group_to_hansard_divisions.setdefault(
            (hansard_division.sitting_date, hansard_division.ayes, hansard_division.noes),
            [],
        ).append(hansard_division)
    group_to_minutes_divisions: dict[
        tuple[date, int, int], list[PairableMinutesDivision]
    ] = {}
    for minutes_division in minutes_divisions:
        group_to_minutes_divisions.setdefault(
            (minutes_division.sitting_date, minutes_division.ayes, minutes_division.noes),
            [],
        ).append(minutes_division)
    pairings: list[DivisionPairing] = []
    for group, minutes_group in group_to_minutes_divisions.items():
        hansard_group = sorted(
            group_to_hansard_divisions.get(group, []),
            key=lambda hansard_division: (
                hansard_division.speech_number,
                hansard_division.speech_ordinal,
            ),
        )
        pairings.extend(
            _pair_group(
                hansard_group,
                sorted(minutes_group, key=lambda minutes_division: minutes_division.ordinal),
            )
        )
    return sorted(
        pairings,
        key=lambda pairing: (pairing.sitting_date, pairing.minutes_ordinal),
    )

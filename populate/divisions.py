from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence, Union

from sqlmodel import Session

from crud.division import CRUDDivision
from crud.division_vote import CRUDDivisionVote
from crud.minutes_division import CRUDMinutesDivision
from crud.party_affiliation import CRUDPartyAffiliation
from crud.report import CRUDReport, ReportDivisionRow
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechParseRow
from database.division import Division
from database.division_vote import DivisionVote
from database.party_affiliation import PartyAffiliation
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteListSource,
    MinutesDivisionPairing,
)
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.division_plan import DivisionPlan, PlannedDivision, PlannedUnreadRow
from schemas.minutes_division_plan import PlannedDivisionVote
from services.attendance import build_inverted_name_to_canonical, build_speaker_lookups
from services.division import ParsedDivision, ReportDivisions, get_report_divisions
from services.division_list import ParsedDivisionList, get_division_list
from services.party_affiliation import get_party_on_date
from services.speaker_link import VoteSpeakerMatch, resolve_vote_speaker
from utils.division_detachment import DivisionDetachment
from utils.division_update import DivisionUpdate
from utils.division_vote_name import ParsedVoteName, get_name_to_resolve
from utils.speaker_resolution import SpeakerLookups

_REPORT_BATCH = 200
_YEARS_PER_DECADE = 10


@dataclass(frozen=True)
class DivisionMatch:
    division_updates: list[DivisionUpdate]
    divisions_to_add: list[Division]
    division_ids_to_delete: list[int]
    division_id_to_votes: dict[int, list[PlannedDivisionVote]]


@dataclass(frozen=True)
class PairedDivisionAtRisk:
    division_id: int
    sprs_report_id: str
    printed_counts: str
    is_line_gone: bool


@dataclass(frozen=True)
class _NameLookups:
    speaker_lookups: SpeakerLookups
    inverted_name_to_canonical: dict[tuple[str, int], str]
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int]
    speaker_id_to_party: dict[int, str]


@dataclass(frozen=True)
class _ResolvedName:
    name: ParsedVoteName
    vote_speaker_match: Optional[VoteSpeakerMatch]


@dataclass(frozen=True)
class _ReadDivision:
    report_row: ReportDivisionRow
    parsed_division: ParsedDivision
    division_list: ParsedDivisionList
    resolved_names: list[_ResolvedName]


@dataclass(frozen=True)
class _DivisionShape:
    report_division_number: Optional[int]
    speech_ordinal: Optional[int]
    printed_counts: str
    ayes: Optional[int]
    noes: Optional[int]
    abstentions: Optional[int]
    absent: Optional[int]
    paired: Optional[int]


def get_decade_label(sitting_date: date) -> str:
    return f"{sitting_date.year // _YEARS_PER_DECADE * _YEARS_PER_DECADE}s"


def get_decade_and_source_counts(
    divisions: Sequence[Union[Division, PlannedDivision]],
) -> Counter[tuple[str, DivisionCountSource]]:
    return Counter(
        (get_decade_label(division.sitting_date), division.count_source)
        for division in divisions
    )


def _build_name_lookups(session: Session) -> _NameLookups:
    speakers = CRUDSpeaker(session).get_all()
    name_parliament_number_to_speaker_count = Counter(
        (speaker.name, speaker.parliament_number) for speaker in speakers
    )
    return _NameLookups(
        speaker_lookups=build_speaker_lookups(speakers),
        inverted_name_to_canonical=build_inverted_name_to_canonical(speakers),
        name_parliament_number_to_speaker_id={
            (speaker.name, speaker.parliament_number): speaker.id
            for speaker in speakers
            if speaker.id is not None
            and name_parliament_number_to_speaker_count[
                (speaker.name, speaker.parliament_number)
            ]
            == 1
        },
        speaker_id_to_party={
            speaker.id: speaker.party for speaker in speakers if speaker.id is not None
        },
    )


def _resolve_names(
    names: list[ParsedVoteName], parliament_number: int, name_lookups: _NameLookups
) -> list[_ResolvedName]:
    return [
        _ResolvedName(
            name,
            resolve_vote_speaker(
                get_name_to_resolve(name.printed_name),
                parliament_number,
                name_lookups.speaker_lookups,
                name_lookups.inverted_name_to_canonical,
                name_lookups.name_parliament_number_to_speaker_id,
            ),
        )
        for name in names
    ]


def _read_report_divisions(
    report_row: ReportDivisionRow,
    report_divisions: ReportDivisions,
    content: Optional[str],
    name_lookups: _NameLookups,
) -> list[_ReadDivision]:
    printed_line_numbers = [
        parsed_division.report_division_number
        for parsed_division in sorted(
            report_divisions.divisions,
            key=lambda parsed_division: parsed_division.speech_ordinal,
        )
        if parsed_division.count_source == DivisionCountSource.PRINTED_LINE
    ]
    read_divisions: list[_ReadDivision] = []
    for parsed_division in report_divisions.divisions:
        if parsed_division.count_source != DivisionCountSource.PRINTED_LINE:
            read_divisions.append(
                _ReadDivision(
                    report_row,
                    parsed_division,
                    ParsedDivisionList(DivisionListStatus.NOT_PRINTED, None, []),
                    [],
                )
            )
            continue
        division_list = get_division_list(
            content,
            printed_line_numbers.index(parsed_division.report_division_number),
            len(printed_line_numbers),
            parsed_division.ayes,
            parsed_division.noes,
            parsed_division.abstentions,
            parsed_division.absent,
            parsed_division.paired,
        )
        read_divisions.append(
            _ReadDivision(
                report_row,
                parsed_division,
                division_list,
                _resolve_names(
                    division_list.names, report_row.parliament_number, name_lookups
                ),
            )
        )
    return read_divisions


def _get_planned_votes(
    resolved_names: list[_ResolvedName],
    sitting_date: date,
    name_lookups: _NameLookups,
    speaker_id_to_party_affiliations: dict[int, list[PartyAffiliation]],
) -> list[PlannedDivisionVote]:
    planned_votes: list[PlannedDivisionVote] = []
    for resolved_name in resolved_names:
        name = resolved_name.name
        vote_speaker_match = resolved_name.vote_speaker_match
        if vote_speaker_match is None:
            planned_votes.append(
                PlannedDivisionVote(
                    ordinal=name.ordinal,
                    printed_name=name.printed_name,
                    vote_choice=name.vote_choice,
                    speaker_id=None,
                    name_rule=None,
                    party=None,
                    is_party_uncertain=False,
                )
            )
            continue
        party_on_date = get_party_on_date(
            name_lookups.speaker_id_to_party[vote_speaker_match.speaker_id],
            speaker_id_to_party_affiliations.get(vote_speaker_match.speaker_id, []),
            sitting_date,
        )
        planned_votes.append(
            PlannedDivisionVote(
                ordinal=name.ordinal,
                printed_name=name.printed_name,
                vote_choice=name.vote_choice,
                speaker_id=vote_speaker_match.speaker_id,
                name_rule=vote_speaker_match.name_rule,
                party=party_on_date.party,
                is_party_uncertain=party_on_date.is_party_uncertain,
            )
        )
    return planned_votes


def _plan_report_batch(
    session: Session, report_rows: list[ReportDivisionRow], name_lookups: _NameLookups
) -> tuple[list[PlannedDivision], list[PlannedUnreadRow]]:
    report_id_to_speech_parse_rows: defaultdict[int, list[SpeechParseRow]] = (
        defaultdict(list)
    )
    for speech_parse_row in CRUDSpeech(session).get_parse_rows_by_report_ids(
        [report_row.id for report_row in report_rows]
    ):
        report_id_to_speech_parse_rows[speech_parse_row.report_id].append(
            speech_parse_row
        )
    report_id_to_report_divisions = {
        report_row.id: get_report_divisions(report_id_to_speech_parse_rows[report_row.id])
        for report_row in report_rows
    }
    report_id_to_content = {
        content_row.id: content_row.content
        for content_row in CRUDReport(session).get_content_rows_by_ids(
            [
                report_row.id
                for report_row in report_rows
                if any(
                    parsed_division.count_source == DivisionCountSource.PRINTED_LINE
                    for parsed_division in report_id_to_report_divisions[
                        report_row.id
                    ].divisions
                )
            ]
        )
    }
    read_divisions = [
        read_division
        for report_row in report_rows
        for read_division in _read_report_divisions(
            report_row,
            report_id_to_report_divisions[report_row.id],
            report_id_to_content.get(report_row.id),
            name_lookups,
        )
    ]
    speaker_id_to_party_affiliations: defaultdict[int, list[PartyAffiliation]] = (
        defaultdict(list)
    )
    for party_affiliation in CRUDPartyAffiliation(session).get_by_speaker_ids(
        sorted(
            {
                resolved_name.vote_speaker_match.speaker_id
                for read_division in read_divisions
                for resolved_name in read_division.resolved_names
                if resolved_name.vote_speaker_match is not None
            }
        )
    ):
        speaker_id_to_party_affiliations[party_affiliation.speaker_id].append(
            party_affiliation
        )
    planned_divisions = [
        PlannedDivision(
            sprs_report_id=read_division.report_row.report_id,
            sitting_date=read_division.report_row.sitting_date.date(),
            parliament_number=read_division.report_row.parliament_number,
            report_division_number=read_division.parsed_division.report_division_number,
            speech_ordinal=read_division.parsed_division.speech_ordinal,
            count_source=read_division.parsed_division.count_source,
            printed_counts=read_division.parsed_division.printed_counts,
            ayes=read_division.parsed_division.ayes,
            noes=read_division.parsed_division.noes,
            abstentions=read_division.parsed_division.abstentions,
            absent=read_division.parsed_division.absent,
            paired=read_division.parsed_division.paired,
            list_status=read_division.division_list.list_status,
            printed_list=read_division.division_list.printed_list,
            votes=_get_planned_votes(
                read_division.resolved_names,
                read_division.report_row.sitting_date.date(),
                name_lookups,
                speaker_id_to_party_affiliations,
            ),
        )
        for read_division in read_divisions
    ]
    planned_unread_rows = [
        PlannedUnreadRow(
            report_id=report_row.id,
            sprs_report_id=report_row.report_id,
            speech_ordinal=unread_row.speech_ordinal,
            reason=unread_row.reason,
            printed_text=unread_row.printed_text,
        )
        for report_row in report_rows
        for unread_row in report_id_to_report_divisions[report_row.id].unread_rows
    ]
    return planned_divisions, planned_unread_rows


def get_division_plan(session: Session, report_ids: list[int]) -> DivisionPlan:
    planned_report_ids: list[int] = []
    sprs_report_ids: list[str] = []
    planned_divisions: list[PlannedDivision] = []
    planned_unread_rows: list[PlannedUnreadRow] = []
    name_lookups = _build_name_lookups(session)
    sorted_report_ids = sorted(report_ids)
    for start in range(0, len(sorted_report_ids), _REPORT_BATCH):
        report_rows = CRUDReport(session).get_division_report_rows_by_ids(
            sorted_report_ids[start : start + _REPORT_BATCH]
        )
        batch_divisions, batch_unread_rows = _plan_report_batch(
            session, report_rows, name_lookups
        )
        planned_report_ids.extend(report_row.id for report_row in report_rows)
        sprs_report_ids.extend(report_row.report_id for report_row in report_rows)
        planned_divisions.extend(batch_divisions)
        planned_unread_rows.extend(batch_unread_rows)
    return DivisionPlan(
        report_ids=planned_report_ids,
        sprs_report_ids=sprs_report_ids,
        divisions=planned_divisions,
        unread_rows=planned_unread_rows,
    )


def _build_division(planned_division: PlannedDivision) -> Division:
    return Division(
        sitting_date=planned_division.sitting_date,
        parliament_number=planned_division.parliament_number,
        report_division_number=planned_division.report_division_number,
        speech_ordinal=planned_division.speech_ordinal,
        count_source=planned_division.count_source,
        printed_counts=planned_division.printed_counts,
        ayes=planned_division.ayes,
        noes=planned_division.noes,
        abstentions=planned_division.abstentions,
        absent=planned_division.absent,
        paired=planned_division.paired,
        list_status=planned_division.list_status,
        printed_list=planned_division.printed_list,
        sprs_report_id=planned_division.sprs_report_id,
    )


def _get_division_update(division_id: int, division: Division) -> DivisionUpdate:
    return DivisionUpdate(
        id=division_id,
        sitting_date=division.sitting_date,
        parliament_number=division.parliament_number,
        report_division_number=division.report_division_number,
        speech_ordinal=division.speech_ordinal,
        count_source=division.count_source,
        printed_counts=division.printed_counts,
        ayes=division.ayes,
        noes=division.noes,
        abstentions=division.abstentions,
        absent=division.absent,
        paired=division.paired,
        list_status=division.list_status,
        printed_list=division.printed_list,
    )


def get_division_match(session: Session, plan: DivisionPlan) -> DivisionMatch:
    division_id_to_stored_division: dict[int, Division] = {}
    sprs_report_id_and_printed_counts_to_stored_ids: defaultdict[
        tuple[str, str], deque[int]
    ] = defaultdict(deque)
    for stored_division in CRUDDivision(session).get_by_sprs_report_ids(
        plan.sprs_report_ids
    ):
        if stored_division.id is None or stored_division.sprs_report_id is None:
            continue
        division_id_to_stored_division[stored_division.id] = stored_division
        sprs_report_id_and_printed_counts_to_stored_ids[
            (stored_division.sprs_report_id, stored_division.printed_counts)
        ].append(stored_division.id)

    division_updates: list[DivisionUpdate] = []
    divisions_to_add: list[Division] = []
    division_id_to_votes: dict[int, list[PlannedDivisionVote]] = {}
    for planned_division in plan.divisions:
        stored_ids = sprs_report_id_and_printed_counts_to_stored_ids[
            (planned_division.sprs_report_id, planned_division.printed_counts)
        ]
        division = _build_division(planned_division)
        if not stored_ids:
            divisions_to_add.append(division)
            continue
        division_id = stored_ids.popleft()
        division_id_to_votes[division_id] = planned_division.votes
        division_update = _get_division_update(division_id, division)
        if division_update != _get_division_update(
            division_id, division_id_to_stored_division[division_id]
        ):
            division_updates.append(division_update)
    return DivisionMatch(
        division_updates,
        divisions_to_add,
        sorted(
            division_id
            for stored_ids in sprs_report_id_and_printed_counts_to_stored_ids.values()
            for division_id in stored_ids
        ),
        division_id_to_votes,
    )


def _build_division_votes(
    division_id: int, planned_votes: list[PlannedDivisionVote]
) -> list[DivisionVote]:
    return [
        DivisionVote(
            ordinal=planned_vote.ordinal,
            printed_name=planned_vote.printed_name,
            vote_choice=planned_vote.vote_choice,
            list_source=DivisionVoteListSource.HANSARD,
            name_rule=planned_vote.name_rule,
            party=planned_vote.party,
            is_party_uncertain=planned_vote.is_party_uncertain,
            division_id=division_id,
            speaker_id=planned_vote.speaker_id,
        )
        for planned_vote in planned_votes
    ]


def _get_division_id(division: Division) -> int:
    if division.id is None:
        raise HansardWriteCheckError("A division was added and holds no id")
    return division.id


def _get_added_division_votes(
    plan: DivisionPlan, added_divisions: list[Division]
) -> list[DivisionVote]:
    sprs_report_id_and_number_to_votes = {
        (planned_division.sprs_report_id, planned_division.report_division_number): (
            planned_division.votes
        )
        for planned_division in plan.divisions
    }
    return [
        division_vote
        for added_division in added_divisions
        for division_vote in _build_division_votes(
            _get_division_id(added_division),
            sprs_report_id_and_number_to_votes[
                (added_division.sprs_report_id, added_division.report_division_number)
            ],
        )
    ]


def _get_division_shape(division: Union[Division, PlannedDivision]) -> _DivisionShape:
    return _DivisionShape(
        report_division_number=division.report_division_number,
        speech_ordinal=division.speech_ordinal,
        printed_counts=division.printed_counts,
        ayes=division.ayes,
        noes=division.noes,
        abstentions=division.abstentions,
        absent=division.absent,
        paired=division.paired,
    )


def _validate_can_commit_divisions(session: Session, plan: DivisionPlan) -> None:
    stored_divisions = CRUDDivision(session).get_by_sprs_report_ids(
        plan.sprs_report_ids
    )
    stored_counts = get_decade_and_source_counts(stored_divisions)
    planned_counts = get_decade_and_source_counts(plan.divisions)
    for key in stored_counts.keys() | planned_counts.keys():
        if stored_counts[key] != planned_counts[key]:
            raise HansardWriteCheckError(
                f"{key}: {stored_counts[key]} stored divisions, the plan has {planned_counts[key]}"
            )
    stored_list_status_counts = Counter(
        stored_division.list_status for stored_division in stored_divisions
    )
    planned_list_status_counts = Counter(
        planned_division.list_status for planned_division in plan.divisions
    )
    if stored_list_status_counts != planned_list_status_counts:
        raise HansardWriteCheckError(
            f"The stored divisions by list status {dict(stored_list_status_counts)} differ from the plan {dict(planned_list_status_counts)}"
        )
    stored_vote_counts = Counter(
        (vote_row.vote_choice, vote_row.speaker_id is not None)
        for vote_row in CRUDDivisionVote(
            session
        ).get_rows_by_division_ids_and_list_source(
            [
                stored_division.id
                for stored_division in stored_divisions
                if stored_division.id is not None
            ],
            DivisionVoteListSource.HANSARD,
        )
    )
    planned_vote_counts = Counter(
        (planned_vote.vote_choice, planned_vote.speaker_id is not None)
        for planned_division in plan.divisions
        for planned_vote in planned_division.votes
    )
    if stored_vote_counts != planned_vote_counts:
        raise HansardWriteCheckError(
            f"The stored Hansard vote rows by choice and link {dict(stored_vote_counts)} differ from the plan {dict(planned_vote_counts)}"
        )
    sprs_report_id_to_stored_shapes: defaultdict[str, list[_DivisionShape]] = (
        defaultdict(list)
    )
    for stored_division in stored_divisions:
        if stored_division.sprs_report_id is None:
            continue
        sprs_report_id_to_stored_shapes[stored_division.sprs_report_id].append(
            _get_division_shape(stored_division)
        )
    sprs_report_id_to_planned_shapes: defaultdict[str, list[_DivisionShape]] = (
        defaultdict(list)
    )
    for planned_division in plan.divisions:
        sprs_report_id_to_planned_shapes[planned_division.sprs_report_id].append(
            _get_division_shape(planned_division)
        )
    for sprs_report_id in plan.sprs_report_ids:
        if (
            sprs_report_id_to_stored_shapes[sprs_report_id]
            != sprs_report_id_to_planned_shapes[sprs_report_id]
        ):
            raise HansardWriteCheckError(
                f"Report {sprs_report_id}: the stored divisions differ from the plan"
            )


def _build_paired_division_at_risk(
    stored_division: Division, is_line_gone: bool
) -> PairedDivisionAtRisk:
    if stored_division.id is None or stored_division.sprs_report_id is None:
        raise HansardWriteCheckError("A stored division holds no id or no report")
    return PairedDivisionAtRisk(
        division_id=stored_division.id,
        sprs_report_id=stored_division.sprs_report_id,
        printed_counts=stored_division.printed_counts,
        is_line_gone=is_line_gone,
    )


def get_paired_divisions_at_risk(
    session: Session, plan: DivisionPlan
) -> list[PairedDivisionAtRisk]:
    division_id_to_stored_division = {
        stored_division.id: stored_division
        for stored_division in CRUDDivision(session).get_by_sprs_report_ids(
            plan.sprs_report_ids
        )
        if stored_division.id is not None and stored_division.sprs_report_id is not None
    }
    paired_division_ids = {
        minutes_division_row.division_id
        for minutes_division_row in CRUDMinutesDivision(
            session
        ).get_rows_by_division_ids(list(division_id_to_stored_division))
        if minutes_division_row.pairing == MinutesDivisionPairing.PAIRED
    }
    if not paired_division_ids:
        return []
    match = get_division_match(session, plan)
    at_risk_divisions: list[PairedDivisionAtRisk] = []
    sprs_report_id_and_number_of_added_divisions = {
        (added_division.sprs_report_id, added_division.report_division_number)
        for added_division in match.divisions_to_add
    }
    for division_id in match.division_ids_to_delete:
        if division_id in paired_division_ids:
            stored_division = division_id_to_stored_division[division_id]
            at_risk_divisions.append(
                _build_paired_division_at_risk(
                    stored_division,
                    is_line_gone=(
                        stored_division.sprs_report_id,
                        stored_division.report_division_number,
                    )
                    not in sprs_report_id_and_number_of_added_divisions,
                )
            )
    for division_update in match.division_updates:
        if division_update.id not in paired_division_ids:
            continue
        stored_division = division_id_to_stored_division[division_update.id]
        if (division_update.ayes, division_update.noes) != (
            stored_division.ayes,
            stored_division.noes,
        ):
            at_risk_divisions.append(
                _build_paired_division_at_risk(stored_division, is_line_gone=False)
            )
    return sorted(at_risk_divisions, key=lambda at_risk: at_risk.division_id)


def _detach_paired_divisions(
    session: Session, at_risk_divisions: list[PairedDivisionAtRisk]
) -> None:
    division_ids = [at_risk.division_id for at_risk in at_risk_divisions]
    division_detachments = [
        DivisionDetachment(
            division_id=minutes_division_row.division_id,
            printed_counts=minutes_division_row.printed_counts,
            ayes=minutes_division_row.ayes,
            noes=minutes_division_row.noes,
            abstentions=minutes_division_row.abstentions,
        )
        for minutes_division_row in CRUDMinutesDivision(
            session
        ).get_rows_by_division_ids(division_ids)
        if minutes_division_row.pairing == MinutesDivisionPairing.PAIRED
    ]
    if len(division_detachments) != len(division_ids):
        raise HansardWriteCheckError(
            f"{len(division_ids)} paired divisions to detach, {len(division_detachments)} paired minutes rows read"
        )
    detached_count = CRUDDivision(session).detach_report_many(division_detachments)
    if detached_count != len(division_ids):
        raise HansardWriteCheckError(
            f"Detached {detached_count} divisions, planned {len(division_ids)}"
        )
    CRUDDivisionVote(session).delete_by_division_ids_and_list_source(
        division_ids, DivisionVoteListSource.HANSARD
    )
    repaired_count = CRUDMinutesDivision(session).set_pairing_by_division_ids(
        division_ids, MinutesDivisionPairing.NO_MATCHING_DIVISION
    )
    if repaired_count != len(division_ids):
        raise HansardWriteCheckError(
            f"Set the pairing of {repaired_count} minutes divisions, planned {len(division_ids)}"
        )


def write_division_plan(
    session: Session, plan: DivisionPlan, *, is_detaching_paired: bool = False
) -> None:
    at_risk_divisions = get_paired_divisions_at_risk(session, plan)
    for at_risk in at_risk_divisions:
        if not at_risk.is_line_gone:
            raise HansardWriteCheckError(
                f"Division {at_risk.division_id} of report {at_risk.sprs_report_id} ({at_risk.printed_counts}) is paired with a minutes division and the plan would change its Ayes or Noes"
            )
        if not is_detaching_paired:
            raise HansardWriteCheckError(
                f"Division {at_risk.division_id} of report {at_risk.sprs_report_id} ({at_risk.printed_counts}) is paired with a minutes division and its line has gone; rerun with --detach-paired to rewrite it to a minutes-only division"
            )
    if at_risk_divisions:
        _detach_paired_divisions(session, at_risk_divisions)
    match = get_division_match(session, plan)
    CRUDDivisionVote(session).delete_by_division_ids_and_list_source(
        sorted(match.division_id_to_votes) + match.division_ids_to_delete,
        DivisionVoteListSource.HANSARD,
    )
    if match.division_ids_to_delete:
        deleted_count = CRUDDivision(session).delete_by_ids(
            match.division_ids_to_delete
        )
        if deleted_count != len(match.division_ids_to_delete):
            raise HansardWriteCheckError(
                f"Deleted {deleted_count} divisions, planned {len(match.division_ids_to_delete)}"
            )
    CRUDDivision(session).update_many(match.division_updates)
    CRUDDivision(session).add_many(match.divisions_to_add)
    CRUDDivisionVote(session).add_many(
        [
            division_vote
            for division_id, planned_votes in match.division_id_to_votes.items()
            for division_vote in _build_division_votes(division_id, planned_votes)
        ]
        + _get_added_division_votes(plan, match.divisions_to_add)
    )
    _validate_can_commit_divisions(session, plan)


# NOTE: inserts only, because the refresh role has no UPDATE or DELETE grant on division or division_vote
def populate_divisions(session: Session, report_ids: list[int]) -> list[int]:
    plan = get_division_plan(session, report_ids)
    added_divisions = [
        _build_division(planned_division) for planned_division in plan.divisions
    ]
    CRUDDivision(session).add_many(added_divisions)
    CRUDDivisionVote(session).add_many(_get_added_division_votes(plan, added_divisions))
    _validate_can_commit_divisions(session, plan)
    logger.info(
        f"Divisions: added {len(plan.divisions)} rows for {len(plan.report_ids)} reports"
    )
    return sorted({unread_row.report_id for unread_row in plan.unread_rows})

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional

from sqlmodel import Session

from crud.division import CRUDDivision
from crud.division_vote import CRUDDivisionVote
from crud.minutes import CRUDMinutes
from crud.minutes_division import CRUDMinutesDivision
from crud.party_affiliation import CRUDPartyAffiliation
from crud.report import CRUDReport
from crud.speaker import CRUDSpeaker
from database.division import Division
from database.division_vote import DivisionVote
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from database.party_affiliation import PartyAffiliation
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteListSource,
    MinutesDivisionPairing,
    MinutesStatus,
)
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.minutes_division_plan import (
    MinutesDivisionPlan,
    PlannedDivisionVote,
    PlannedMinutesDivision,
    PlannedMinutesOnlyDivision,
    PlannedMinutesReview,
)
from services.attendance import build_inverted_name_to_canonical, build_speaker_lookups
from services.division_pairing import (
    DivisionPairing,
    PairableHansardDivision,
    PairableMinutesDivision,
    get_division_pairs,
)
from services.minutes_division import ParsedMinutesDivision, get_minutes_divisions
from services.party_affiliation import get_party_on_date
from services.speaker_link import VoteSpeakerMatch, resolve_vote_speaker
from utils.division_vote_name import ParsedVoteName
from utils.speaker_resolution import SpeakerLookups

MINUTES_DIVISION_FIRST_DATE = date(2008, 10, 1)
UNREAD_DIVISION_STATUS_NOTE = "A division is mentioned and none could be read"
TWO_PARLIAMENTS_STATUS_NOTE = "The reports of this date hold two Parliament numbers"
_OWN_REVIEW_STATUS_NOTES = frozenset(
    {UNREAD_DIVISION_STATUS_NOTE, TWO_PARLIAMENTS_STATUS_NOTE}
)
_MINUTES_BATCH = 50


@dataclass(frozen=True)
class _NameLookups:
    speaker_lookups: SpeakerLookups
    inverted_name_to_canonical: dict[tuple[str, int], str]
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int]
    speaker_id_to_party: dict[int, str]


@dataclass(frozen=True)
class _MinutesBatchPlan:
    minutes_ids: list[int]
    minutes_to_review: list[PlannedMinutesReview]
    minutes_divisions: list[PlannedMinutesDivision]


@dataclass(frozen=True)
class _ResolvedName:
    name: ParsedVoteName
    vote_speaker_match: Optional[VoteSpeakerMatch]


@dataclass(frozen=True)
class _ParsedMinutes:
    minutes_id: int
    sitting_date: date
    parliament_number: int
    divisions: list[ParsedMinutesDivision]
    ordinal_to_resolved_names: dict[int, list[_ResolvedName]]


def _get_skip_reason(minutes: Minutes) -> Optional[str]:
    if minutes.sitting_date < MINUTES_DIVISION_FIRST_DATE:
        return f"its sitting is before {MINUTES_DIVISION_FIRST_DATE}"
    if minutes.extracted_text is None:
        return "it holds no text"
    if minutes.status == MinutesStatus.TEXT_STORED:
        return None
    if (
        minutes.status == MinutesStatus.NEEDS_REVIEW
        and minutes.status_note in _OWN_REVIEW_STATUS_NOTES
    ):
        return None
    return f"its status is {minutes.status} with the note {minutes.status_note!r}"


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
                name.printed_name,
                parliament_number,
                name_lookups.speaker_lookups,
                name_lookups.inverted_name_to_canonical,
                name_lookups.name_parliament_number_to_speaker_id,
            ),
        )
        for name in names
    ]


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


def _get_pairable_hansard_divisions(
    session: Session, sitting_dates: list[date]
) -> list[PairableHansardDivision]:
    divisions = CRUDDivision(session).get_by_sitting_dates_and_sprs_report_id_not_null(
        sitting_dates
    )
    sprs_report_id_to_speech_number = {
        report.report_id: report.speech_number
        for report in CRUDReport(session).get_by_report_ids(
            sorted(
                {
                    division.sprs_report_id
                    for division in divisions
                    if division.sprs_report_id is not None
                }
            )
        )
    }
    return [
        PairableHansardDivision(
            division_id=division.id,
            sitting_date=division.sitting_date,
            sprs_report_id=division.sprs_report_id,
            speech_number=sprs_report_id_to_speech_number[division.sprs_report_id],
            speech_ordinal=division.speech_ordinal,
            ayes=division.ayes,
            noes=division.noes,
            abstentions=division.abstentions,
        )
        for division in divisions
        if division.id is not None
        and division.sprs_report_id is not None
        and division.speech_ordinal is not None
    ]


def _get_planned_division(
    parsed_minutes: _ParsedMinutes,
    parsed_division: ParsedMinutesDivision,
    division_pairing: DivisionPairing,
    name_lookups: _NameLookups,
    speaker_id_to_party_affiliations: dict[int, list[PartyAffiliation]],
) -> PlannedMinutesDivision:
    new_division = (
        None
        if division_pairing.pairing == MinutesDivisionPairing.PAIRED
        else PlannedMinutesOnlyDivision(
            sitting_date=parsed_minutes.sitting_date,
            parliament_number=parsed_minutes.parliament_number,
            printed_counts=parsed_division.printed_counts,
            ayes=parsed_division.ayes,
            noes=parsed_division.noes,
            abstentions=parsed_division.abstentions,
        )
    )
    return PlannedMinutesDivision(
        minutes_id=parsed_minutes.minutes_id,
        sitting_date=parsed_minutes.sitting_date,
        ordinal=parsed_division.ordinal,
        printed_counts=parsed_division.printed_counts,
        ayes=parsed_division.ayes,
        noes=parsed_division.noes,
        abstentions=parsed_division.abstentions,
        list_status=parsed_division.list_status,
        printed_list=parsed_division.printed_list,
        pairing=division_pairing.pairing,
        division_id=division_pairing.division_id,
        new_division=new_division,
        votes=_get_planned_votes(
            parsed_minutes.ordinal_to_resolved_names[parsed_division.ordinal],
            parsed_minutes.sitting_date,
            name_lookups,
            speaker_id_to_party_affiliations,
        ),
    )


def _plan_minutes_batch(
    session: Session, batch_minutes: list[Minutes], name_lookups: _NameLookups
) -> _MinutesBatchPlan:
    sitting_date_to_parliament_numbers: defaultdict[date, set[int]] = defaultdict(set)
    for report in CRUDReport(session).get_by_sitting_dates(
        [
            datetime.combine(sitting_date, time.min)
            for sitting_date in sorted({minutes.sitting_date for minutes in batch_minutes})
        ]
    ):
        sitting_date_to_parliament_numbers[report.sitting_date.date()].add(
            report.parliament_number
        )
    minutes_ids: list[int] = []
    minutes_to_review: list[PlannedMinutesReview] = []
    parsed_minutes_list: list[_ParsedMinutes] = []
    for minutes in batch_minutes:
        minutes_id = minutes.id
        extracted_text = minutes.extracted_text
        if minutes_id is None or extracted_text is None:
            raise HansardWriteCheckError(
                f"The minutes of {minutes.sitting_date} have no id or no text"
            )
        parliament_numbers = sitting_date_to_parliament_numbers[minutes.sitting_date]
        if not parliament_numbers:
            logger.info(
                f"Minutes divisions: skipped minutes {minutes_id}, no report on {minutes.sitting_date}"
            )
            continue
        minutes_ids.append(minutes_id)
        if len(parliament_numbers) > 1:
            minutes_to_review.append(
                PlannedMinutesReview(
                    minutes_id=minutes_id, status_note=TWO_PARLIAMENTS_STATUS_NOTE
                )
            )
            continue
        minutes_text_divisions = get_minutes_divisions(extracted_text)
        if minutes_text_divisions.is_division_mentioned_without_division:
            minutes_to_review.append(
                PlannedMinutesReview(
                    minutes_id=minutes_id, status_note=UNREAD_DIVISION_STATUS_NOTE
                )
            )
            continue
        parliament_number = next(iter(parliament_numbers))
        parsed_minutes_list.append(
            _ParsedMinutes(
                minutes_id,
                minutes.sitting_date,
                parliament_number,
                minutes_text_divisions.divisions,
                {
                    parsed_division.ordinal: _resolve_names(
                        parsed_division.names, parliament_number, name_lookups
                    )
                    for parsed_division in minutes_text_divisions.divisions
                },
            )
        )
    division_pairings = get_division_pairs(
        _get_pairable_hansard_divisions(
            session,
            sorted(
                {parsed_minutes.sitting_date for parsed_minutes in parsed_minutes_list}
            ),
        ),
        [
            PairableMinutesDivision(
                parsed_minutes.sitting_date,
                parsed_division.ordinal,
                parsed_division.ayes,
                parsed_division.noes,
                parsed_division.abstentions,
            )
            for parsed_minutes in parsed_minutes_list
            for parsed_division in parsed_minutes.divisions
        ],
    )
    sitting_date_and_ordinal_to_pairing = {
        (division_pairing.sitting_date, division_pairing.minutes_ordinal): division_pairing
        for division_pairing in division_pairings
    }
    linked_speaker_ids = sorted(
        {
            resolved_name.vote_speaker_match.speaker_id
            for parsed_minutes in parsed_minutes_list
            for resolved_names in parsed_minutes.ordinal_to_resolved_names.values()
            for resolved_name in resolved_names
            if resolved_name.vote_speaker_match is not None
        }
    )
    speaker_id_to_party_affiliations: defaultdict[int, list[PartyAffiliation]] = (
        defaultdict(list)
    )
    for party_affiliation in CRUDPartyAffiliation(session).get_by_speaker_ids(
        linked_speaker_ids
    ):
        speaker_id_to_party_affiliations[party_affiliation.speaker_id].append(
            party_affiliation
        )
    return _MinutesBatchPlan(
        minutes_ids,
        minutes_to_review,
        [
            _get_planned_division(
                parsed_minutes,
                parsed_division,
                sitting_date_and_ordinal_to_pairing[
                    (parsed_minutes.sitting_date, parsed_division.ordinal)
                ],
                name_lookups,
                speaker_id_to_party_affiliations,
            )
            for parsed_minutes in parsed_minutes_list
            for parsed_division in parsed_minutes.divisions
        ],
    )


def get_minutes_division_plan(
    session: Session, minutes_ids: list[int]
) -> MinutesDivisionPlan:
    name_lookups = _build_name_lookups(session)
    planned_minutes_ids: list[int] = []
    minutes_to_review: list[PlannedMinutesReview] = []
    minutes_divisions: list[PlannedMinutesDivision] = []
    sorted_minutes_ids = sorted(minutes_ids)
    for start in range(0, len(sorted_minutes_ids), _MINUTES_BATCH):
        batch_minutes: list[Minutes] = []
        for minutes in CRUDMinutes(session).get_by_ids(
            sorted_minutes_ids[start : start + _MINUTES_BATCH]
        ):
            skip_reason = _get_skip_reason(minutes)
            if skip_reason is not None:
                logger.info(
                    f"Minutes divisions: skipped minutes {minutes.id}, {skip_reason}"
                )
                continue
            batch_minutes.append(minutes)
        batch_plan = _plan_minutes_batch(session, batch_minutes, name_lookups)
        planned_minutes_ids.extend(batch_plan.minutes_ids)
        minutes_to_review.extend(batch_plan.minutes_to_review)
        minutes_divisions.extend(batch_plan.minutes_divisions)
    return MinutesDivisionPlan(
        minutes_ids=planned_minutes_ids,
        minutes_to_review=minutes_to_review,
        minutes_divisions=minutes_divisions,
    )


def _get_division_id(division: Division) -> int:
    if division.id is None:
        raise HansardWriteCheckError("A division was added and holds no id")
    return division.id


def _build_minutes_only_division(
    new_division: PlannedMinutesOnlyDivision,
) -> Division:
    return Division(
        sitting_date=new_division.sitting_date,
        parliament_number=new_division.parliament_number,
        report_division_number=None,
        speech_ordinal=None,
        count_source=DivisionCountSource.MINUTES,
        printed_counts=new_division.printed_counts,
        ayes=new_division.ayes,
        noes=new_division.noes,
        abstentions=new_division.abstentions,
        absent=None,
        paired=None,
        list_status=DivisionListStatus.NOT_PRINTED,
        printed_list=None,
        sprs_report_id=None,
    )


def _validate_can_commit_minutes_divisions(
    session: Session, plan: MinutesDivisionPlan
) -> None:
    stored_rows = CRUDMinutesDivision(session).get_rows_by_minutes_ids(plan.minutes_ids)
    if Counter(row.list_status for row in stored_rows) != Counter(
        planned.list_status for planned in plan.minutes_divisions
    ):
        raise HansardWriteCheckError(
            "The stored minutes divisions by list status differ from the plan"
        )
    if Counter(row.pairing for row in stored_rows) != Counter(
        planned.pairing for planned in plan.minutes_divisions
    ):
        raise HansardWriteCheckError(
            "The stored minutes divisions by pairing differ from the plan"
        )
    stored_vote_rows = CRUDDivisionVote(session).get_rows_by_division_ids_and_list_source(
        [row.division_id for row in stored_rows], DivisionVoteListSource.MINUTES
    )
    stored_vote_counts = Counter(
        (vote_row.vote_choice, vote_row.speaker_id is not None)
        for vote_row in stored_vote_rows
    )
    planned_vote_counts = Counter(
        (vote.vote_choice, vote.speaker_id is not None)
        for planned in plan.minutes_divisions
        for vote in planned.votes
    )
    if stored_vote_counts != planned_vote_counts:
        raise HansardWriteCheckError(
            f"The stored minutes vote rows by choice and link {dict(stored_vote_counts)} differ from the plan {dict(planned_vote_counts)}"
        )


def _insert_minutes_divisions(session: Session, plan: MinutesDivisionPlan) -> int:
    planned_with_new_division = [
        planned
        for planned in plan.minutes_divisions
        if planned.new_division is not None
    ]
    new_divisions = [
        _build_minutes_only_division(planned.new_division)
        for planned in planned_with_new_division
        if planned.new_division is not None
    ]
    CRUDDivision(session).add_many(new_divisions)
    minutes_id_and_ordinal_to_new_division_id = {
        (planned.minutes_id, planned.ordinal): _get_division_id(new_division)
        for planned, new_division in zip(
            planned_with_new_division, new_divisions, strict=True
        )
    }
    minutes_divisions: list[MinutesDivision] = []
    division_votes: list[DivisionVote] = []
    for planned in plan.minutes_divisions:
        division_id = (
            planned.division_id
            if planned.division_id is not None
            else minutes_id_and_ordinal_to_new_division_id[
                (planned.minutes_id, planned.ordinal)
            ]
        )
        minutes_divisions.append(
            MinutesDivision(
                ordinal=planned.ordinal,
                printed_counts=planned.printed_counts,
                ayes=planned.ayes,
                noes=planned.noes,
                abstentions=planned.abstentions,
                printed_list=planned.printed_list,
                list_status=planned.list_status,
                pairing=planned.pairing,
                minutes_id=planned.minutes_id,
                division_id=division_id,
            )
        )
        division_votes.extend(
            DivisionVote(
                ordinal=vote.ordinal,
                printed_name=vote.printed_name,
                vote_choice=vote.vote_choice,
                list_source=DivisionVoteListSource.MINUTES,
                name_rule=vote.name_rule,
                party=vote.party,
                is_party_uncertain=vote.is_party_uncertain,
                division_id=division_id,
                speaker_id=vote.speaker_id,
            )
            for vote in planned.votes
        )
    CRUDMinutesDivision(session).add_many(minutes_divisions)
    CRUDDivisionVote(session).add_many(division_votes)
    _validate_can_commit_minutes_divisions(session, plan)
    return len(new_divisions) + len(minutes_divisions) + len(division_votes)


def _delete_stored_minutes_divisions(session: Session, minutes_ids: list[int]) -> None:
    stored_rows = CRUDMinutesDivision(session).get_rows_by_minutes_ids(minutes_ids)
    division_ids = [row.division_id for row in stored_rows]
    stored_vote_count = len(
        CRUDDivisionVote(session).get_rows_by_division_ids_and_list_source(
            division_ids, DivisionVoteListSource.MINUTES
        )
    )
    deleted_vote_count = CRUDDivisionVote(
        session
    ).delete_by_division_ids_and_list_source(division_ids, DivisionVoteListSource.MINUTES)
    if deleted_vote_count != stored_vote_count:
        raise HansardWriteCheckError(
            f"Deleted {deleted_vote_count} minutes vote rows, read {stored_vote_count}"
        )
    deleted_row_count = CRUDMinutesDivision(session).delete_by_minutes_ids(minutes_ids)
    if deleted_row_count != len(stored_rows):
        raise HansardWriteCheckError(
            f"Deleted {deleted_row_count} minutes divisions, read {len(stored_rows)}"
        )
    division_ids_to_delete = [
        division.id
        for division in CRUDDivision(session).get_by_ids(division_ids)
        if division.id is not None
        and division.count_source == DivisionCountSource.MINUTES
        and division.sprs_report_id is None
    ]
    deleted_division_count = CRUDDivision(session).delete_by_ids(division_ids_to_delete)
    if deleted_division_count != len(division_ids_to_delete):
        raise HansardWriteCheckError(
            f"Deleted {deleted_division_count} divisions, planned {len(division_ids_to_delete)}"
        )


def _move_minutes_statuses(session: Session, plan: MinutesDivisionPlan) -> None:
    minutes_id_to_stored_minutes = {
        minutes.id: minutes
        for minutes in CRUDMinutes(session).get_by_ids(plan.minutes_ids)
    }
    for minutes_review in plan.minutes_to_review:
        if (
            minutes_id_to_stored_minutes[minutes_review.minutes_id].status
            == MinutesStatus.TEXT_STORED
        ):
            CRUDMinutes(session).set_status_by_id_and_status(
                minutes_review.minutes_id,
                MinutesStatus.TEXT_STORED,
                MinutesStatus.NEEDS_REVIEW,
                minutes_review.status_note,
            )
    for minutes_id in sorted({planned.minutes_id for planned in plan.minutes_divisions}):
        stored_minutes = minutes_id_to_stored_minutes[minutes_id]
        if (
            stored_minutes.status == MinutesStatus.NEEDS_REVIEW
            and stored_minutes.status_note in _OWN_REVIEW_STATUS_NOTES
        ):
            CRUDMinutes(session).set_status_by_id_and_status(
                minutes_id, MinutesStatus.NEEDS_REVIEW, MinutesStatus.TEXT_STORED, None
            )


def write_minutes_division_plan(session: Session, plan: MinutesDivisionPlan) -> None:
    for start in range(0, len(plan.minutes_ids), _MINUTES_BATCH):
        _delete_stored_minutes_divisions(
            session, plan.minutes_ids[start : start + _MINUTES_BATCH]
        )
    _insert_minutes_divisions(session, plan)
    _move_minutes_statuses(session, plan)


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_minutes_divisions(session: Session, minutes_id: int) -> Optional[str]:
    plan = get_minutes_division_plan(session, [minutes_id])
    if not plan.minutes_ids:
        return None
    if plan.minutes_to_review:
        status_note = plan.minutes_to_review[0].status_note
        CRUDMinutes(session).set_status_by_id_and_status(
            minutes_id, MinutesStatus.TEXT_STORED, MinutesStatus.NEEDS_REVIEW, status_note
        )
        logger.info(f"Minutes divisions: minutes {minutes_id} to review, {status_note}")
        return status_note
    added_count = _insert_minutes_divisions(session, plan)
    logger.info(
        f"Minutes divisions: added {added_count} rows for minutes {minutes_id}"
    )
    return None

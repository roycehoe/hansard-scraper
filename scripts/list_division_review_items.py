import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.division import CRUDDivision
from crud.division_vote import CRUDDivisionVote, DivisionVoteSittingRow
from crud.minutes import CRUDMinutes
from crud.minutes_division import CRUDMinutesDivision
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from crud.speech import CRUDSpeech, SpeechParseRow
from database.init import build_read_only_engine
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from enums import (
    DivisionListStatus,
    DivisionReviewItemKind,
    DivisionVoteChoice,
    DivisionVoteListSource,
    MinutesDivisionPairing,
    MinutesStatus,
)
from logs import logger
from populate.minutes_divisions import (
    MINUTES_DIVISION_FIRST_DATE,
    get_pairable_hansard_divisions,
)
from schemas.division_review_list import (
    DivisionListStatusCount,
    DivisionReviewItem,
    DivisionReviewList,
    MinutesDivisionPairingCount,
    MinutesListStatusCount,
)
from services.division import get_report_divisions
from services.division_pairing import (
    DivisionPairing,
    PairableHansardDivision,
    PairableMinutesDivision,
    get_division_pairs,
)
from settings import settings
from utils.sitting_dates import get_decade_label, parse_sitting_date

_REPORT_BATCH = 200
_SOURCE_TEXT_LIMIT = 400
_READ_ISOLATION_LEVEL = "REPEATABLE READ"
_UNREAD_ROW_DATA_SAYS = "no division was made from this row"
_UNREAD_ROW_RULE = "The division opening or spoken total test matched this row, and the row was left unread because of"
_LIST_COUNTS_DISAGREE_RULE = "The names found do not add up to the printed counts, so the list stores no vote rows"
_LIST_LAYOUT_UNREADABLE_RULE = "The layout of the printed list matches no reading rule, so the list stores no vote rows"
_MINUTES_WITHOUT_HANSARD_RULE = "No Hansard division of the date has these Ayes and Noes; expected since 2013, when Hansard prints divisions mostly as spoken totals"
_UNEQUAL_NUMBER_RULE = "The date holds a different number of minutes and Hansard divisions with these Ayes and Noes, so none is paired"
_TIED_RULE = "Two reports hold the same speech number among the Hansard divisions with these Ayes and Noes, so none is paired"
_ABSTENTIONS_DIFFER_RULE = "The printed Abstentions of the minutes and a Hansard division with these Ayes and Noes differ, so none is paired"
_HANSARD_WITHOUT_PAIR_RULE = "The minutes of the date are stored and no minutes division names this Hansard division"
_VOTE_ABSENT_RULE = "The linked Member's attendance row for the sitting says absent"
_TWO_SIDES_RULE = "One Member holds two different Aye, No or Abstain rows in one list of one division"
_DIFFERENT_SIDES_RULE = "One Member holds different choices in the minutes list and the Hansard list of one division"
_NEEDS_REVIEW_RULE = "The minutes file is NEEDS_REVIEW"
_PAIRING_STALE_RULE = "The pairing rule, run now on the stored divisions of the date, gives another pairing than the stored one"
_COUNTED_VOTE_CHOICES = frozenset(
    {DivisionVoteChoice.AYE, DivisionVoteChoice.NO, DivisionVoteChoice.ABSTAIN}
)


@dataclass(frozen=True)
class _ReviewInputs:
    minutes_divisions: list[MinutesDivision]
    minutes_id_to_sitting_date: dict[int, date]
    pairable_hansard_divisions: list[PairableHansardDivision]


def _build_unread_division_row_items(session: Session) -> list[DivisionReviewItem]:
    report_ids = CRUDReport(session).get_ids()
    items: list[DivisionReviewItem] = []
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch_report_ids = report_ids[start : start + _REPORT_BATCH]
        report_id_to_speech_parse_rows: defaultdict[int, list[SpeechParseRow]] = (
            defaultdict(list)
        )
        for speech_parse_row in CRUDSpeech(session).get_parse_rows_by_report_ids(
            batch_report_ids
        ):
            report_id_to_speech_parse_rows[speech_parse_row.report_id].append(
                speech_parse_row
            )
        for report_row in CRUDReport(session).get_division_report_rows_by_ids(
            batch_report_ids
        ):
            report_divisions = get_report_divisions(
                report_id_to_speech_parse_rows[report_row.id]
            )
            items.extend(
                DivisionReviewItem(
                    kind=DivisionReviewItemKind.UNREAD_DIVISION_ROW,
                    sitting_date=report_row.sitting_date.date(),
                    division_id=None,
                    minutes_id=None,
                    sprs_report_id=report_row.report_id,
                    source_text=unread_row.printed_text,
                    data_says=_UNREAD_ROW_DATA_SAYS,
                    rule=f"{_UNREAD_ROW_RULE} {unread_row.reason}",
                )
                for unread_row in report_divisions.unread_rows
            )
    return items


def _build_list_status_items(
    session: Session, inputs: _ReviewInputs
) -> list[DivisionReviewItem]:
    list_status_to_kind = {
        DivisionListStatus.COUNTS_DISAGREE: (
            DivisionReviewItemKind.LIST_COUNTS_DISAGREE,
            _LIST_COUNTS_DISAGREE_RULE,
        ),
        DivisionListStatus.LAYOUT_UNREADABLE: (
            DivisionReviewItemKind.LIST_LAYOUT_UNREADABLE,
            _LIST_LAYOUT_UNREADABLE_RULE,
        ),
    }
    items: list[DivisionReviewItem] = []
    for division in CRUDDivision(session).get_by_list_statuses(
        list(list_status_to_kind)
    ):
        kind, rule = list_status_to_kind[division.list_status]
        items.append(
            DivisionReviewItem(
                kind=kind,
                sitting_date=division.sitting_date,
                division_id=division.id,
                minutes_id=None,
                sprs_report_id=division.sprs_report_id,
                source_text=division.printed_list or "",
                data_says=f"printed counts {division.printed_counts}; Ayes {division.ayes}, Noes {division.noes}, Abstentions {division.abstentions}; list status {division.list_status}",
                rule=rule,
            )
        )
    for minutes_division in inputs.minutes_divisions:
        if minutes_division.list_status not in list_status_to_kind:
            continue
        kind, rule = list_status_to_kind[minutes_division.list_status]
        items.append(
            DivisionReviewItem(
                kind=kind,
                sitting_date=inputs.minutes_id_to_sitting_date[
                    minutes_division.minutes_id
                ],
                division_id=None,
                minutes_id=minutes_division.minutes_id,
                sprs_report_id=None,
                source_text=minutes_division.printed_list or "",
                data_says=f"printed counts {minutes_division.printed_counts}; Ayes {minutes_division.ayes}, Noes {minutes_division.noes}, Abstentions {minutes_division.abstentions}; list status {minutes_division.list_status}",
                rule=rule,
            )
        )
    return items


def _format_hansard_divisions(hansard_divisions: list[PairableHansardDivision]) -> str:
    if not hansard_divisions:
        return "none"
    return "; ".join(
        f"division {hansard_division.division_id} of report {hansard_division.sprs_report_id}, speech {hansard_division.speech_number}, row {hansard_division.speech_ordinal}, Abstentions {hansard_division.abstentions}"
        for hansard_division in hansard_divisions
    )


def _build_pairing_items(inputs: _ReviewInputs) -> list[DivisionReviewItem]:
    pairing_to_kind_and_rule = {
        MinutesDivisionPairing.NO_MATCHING_DIVISION: (
            DivisionReviewItemKind.MINUTES_DIVISION_WITHOUT_HANSARD_DIVISION,
            _MINUTES_WITHOUT_HANSARD_RULE,
        ),
        MinutesDivisionPairing.UNEQUAL_NUMBER: (
            DivisionReviewItemKind.MINUTES_DIVISION_UNEQUAL_NUMBER,
            _UNEQUAL_NUMBER_RULE,
        ),
        MinutesDivisionPairing.TIED: (
            DivisionReviewItemKind.MINUTES_DIVISION_TIED,
            _TIED_RULE,
        ),
        MinutesDivisionPairing.ABSTENTIONS_DIFFER: (
            DivisionReviewItemKind.MINUTES_DIVISION_ABSTENTIONS_DIFFER,
            _ABSTENTIONS_DIFFER_RULE,
        ),
    }
    items: list[DivisionReviewItem] = []
    for minutes_division in inputs.minutes_divisions:
        if minutes_division.pairing not in pairing_to_kind_and_rule:
            continue
        kind, rule = pairing_to_kind_and_rule[minutes_division.pairing]
        sitting_date = inputs.minutes_id_to_sitting_date[minutes_division.minutes_id]
        data_says = f"minutes division {minutes_division.ordinal}: Ayes {minutes_division.ayes}, Noes {minutes_division.noes}, Abstentions {minutes_division.abstentions}; pairing {minutes_division.pairing}"
        if kind != DivisionReviewItemKind.MINUTES_DIVISION_WITHOUT_HANSARD_DIVISION:
            matching_hansard_divisions = [
                hansard_division
                for hansard_division in inputs.pairable_hansard_divisions
                if hansard_division.sitting_date == sitting_date
                and hansard_division.ayes == minutes_division.ayes
                and hansard_division.noes == minutes_division.noes
            ]
            data_says += f"; Hansard divisions of the date with the same Ayes and Noes: {_format_hansard_divisions(matching_hansard_divisions)}"
        items.append(
            DivisionReviewItem(
                kind=kind,
                sitting_date=sitting_date,
                division_id=minutes_division.division_id,
                minutes_id=minutes_division.minutes_id,
                sprs_report_id=None,
                source_text=minutes_division.printed_counts,
                data_says=data_says,
                rule=rule,
            )
        )
    return items


def _build_stale_pairing_items(inputs: _ReviewInputs) -> list[DivisionReviewItem]:
    sitting_date_and_ordinal_to_pairing: dict[tuple[date, int], DivisionPairing] = {
        (division_pairing.sitting_date, division_pairing.minutes_ordinal): division_pairing
        for division_pairing in get_division_pairs(
            inputs.pairable_hansard_divisions,
            [
                PairableMinutesDivision(
                    inputs.minutes_id_to_sitting_date[minutes_division.minutes_id],
                    minutes_division.ordinal,
                    minutes_division.ayes,
                    minutes_division.noes,
                    minutes_division.abstentions,
                )
                for minutes_division in inputs.minutes_divisions
            ],
        )
    }
    items: list[DivisionReviewItem] = []
    for minutes_division in inputs.minutes_divisions:
        sitting_date = inputs.minutes_id_to_sitting_date[minutes_division.minutes_id]
        rerun_pairing = sitting_date_and_ordinal_to_pairing[
            (sitting_date, minutes_division.ordinal)
        ]
        is_pairing_stale = rerun_pairing.pairing != minutes_division.pairing or (
            rerun_pairing.pairing == MinutesDivisionPairing.PAIRED
            and rerun_pairing.division_id != minutes_division.division_id
        )
        if not is_pairing_stale:
            continue
        items.append(
            DivisionReviewItem(
                kind=DivisionReviewItemKind.MINUTES_PAIRING_STALE,
                sitting_date=sitting_date,
                division_id=minutes_division.division_id,
                minutes_id=minutes_division.minutes_id,
                sprs_report_id=None,
                source_text=minutes_division.printed_counts,
                data_says=f"stored: pairing {minutes_division.pairing} with division {minutes_division.division_id}; rerun: pairing {rerun_pairing.pairing} with division {rerun_pairing.division_id}, Hansard divisions {list(rerun_pairing.hansard_division_ids)}",
                rule=_PAIRING_STALE_RULE,
            )
        )
    return items


def _build_unpaired_hansard_division_items(
    session: Session, inputs: _ReviewInputs, stored_minutes: list[Minutes]
) -> list[DivisionReviewItem]:
    stored_sitting_dates = sorted(
        minutes.sitting_date
        for minutes in stored_minutes
        if minutes.status == MinutesStatus.TEXT_STORED
        and minutes.sitting_date >= MINUTES_DIVISION_FIRST_DATE
    )
    paired_division_ids = {
        minutes_division.division_id for minutes_division in inputs.minutes_divisions
    }
    return [
        DivisionReviewItem(
            kind=DivisionReviewItemKind.HANSARD_DIVISION_WITHOUT_MINUTES_PAIR,
            sitting_date=division.sitting_date,
            division_id=division.id,
            minutes_id=None,
            sprs_report_id=division.sprs_report_id,
            source_text=division.printed_counts,
            data_says=f"division {division.id}: Ayes {division.ayes}, Noes {division.noes}; the minutes of {division.sitting_date} are stored and no minutes division names it",
            rule=_HANSARD_WITHOUT_PAIR_RULE,
        )
        for division in CRUDDivision(
            session
        ).get_by_sitting_dates_and_sprs_report_id_not_null(stored_sitting_dates)
        if division.id not in paired_division_ids
    ]


def _get_minutes_id(
    vote_row: DivisionVoteSittingRow, division_id_to_minutes_id: dict[int, int]
) -> Optional[int]:
    if vote_row.list_source != DivisionVoteListSource.MINUTES:
        return None
    return division_id_to_minutes_id.get(vote_row.division_id)


def _build_absent_vote_items(
    session: Session,
    vote_rows: list[DivisionVoteSittingRow],
    division_id_to_minutes_id: dict[int, int],
) -> list[DivisionReviewItem]:
    sitting_id_to_sitting_date = {
        sitting_date_row.id: parse_sitting_date(sitting_date_row.sitting_date).date()
        for sitting_date_row in CRUDSitting(session).get_date_rows()
    }
    speaker_id_and_sitting_date_to_attendance = {
        (attendance.speaker_id, sitting_id_to_sitting_date[attendance.sitting_id]): attendance
        for attendance in CRUDAttendance(session).get_by_is_present_and_speaker_id_not_null(
            False
        )
    }
    items: list[DivisionReviewItem] = []
    for vote_row in vote_rows:
        if vote_row.vote_choice not in _COUNTED_VOTE_CHOICES:
            continue
        attendance = speaker_id_and_sitting_date_to_attendance.get(
            (vote_row.speaker_id, vote_row.sitting_date)
        )
        if attendance is None:
            continue
        items.append(
            DivisionReviewItem(
                kind=DivisionReviewItemKind.VOTE_MEMBER_ABSENT_THAT_SITTING,
                sitting_date=vote_row.sitting_date,
                division_id=vote_row.division_id,
                minutes_id=_get_minutes_id(vote_row, division_id_to_minutes_id),
                sprs_report_id=vote_row.sprs_report_id,
                source_text=vote_row.printed_name,
                data_says=f"{vote_row.list_source} vote row {vote_row.ordinal} ({vote_row.vote_choice}) is linked to speaker {vote_row.speaker_id}; attendance row {attendance.id} lists {attendance.speaker_name} as absent",
                rule=_VOTE_ABSENT_RULE,
            )
        )
    return items


def _build_two_sides_items(
    vote_rows: list[DivisionVoteSittingRow], division_id_to_minutes_id: dict[int, int]
) -> list[DivisionReviewItem]:
    key_to_vote_rows: defaultdict[
        tuple[int, DivisionVoteListSource, int], list[DivisionVoteSittingRow]
    ] = defaultdict(list)
    for vote_row in vote_rows:
        if vote_row.vote_choice not in _COUNTED_VOTE_CHOICES:
            continue
        key_to_vote_rows[
            (vote_row.division_id, vote_row.list_source, vote_row.speaker_id)
        ].append(vote_row)
    items: list[DivisionReviewItem] = []
    for group_vote_rows in key_to_vote_rows.values():
        if len({vote_row.vote_choice for vote_row in group_vote_rows}) <= 1:
            continue
        first_vote_row = group_vote_rows[0]
        items.append(
            DivisionReviewItem(
                kind=DivisionReviewItemKind.MEMBER_ON_TWO_SIDES,
                sitting_date=first_vote_row.sitting_date,
                division_id=first_vote_row.division_id,
                minutes_id=_get_minutes_id(first_vote_row, division_id_to_minutes_id),
                sprs_report_id=first_vote_row.sprs_report_id,
                source_text="; ".join(
                    f"{vote_row.printed_name} ({vote_row.vote_choice})"
                    for vote_row in group_vote_rows
                ),
                data_says=f"speaker {first_vote_row.speaker_id} holds rows {[vote_row.ordinal for vote_row in group_vote_rows]} of the {first_vote_row.list_source} list with choices {[str(vote_row.vote_choice) for vote_row in group_vote_rows]}",
                rule=_TWO_SIDES_RULE,
            )
        )
    return items


def _build_different_sides_items(
    vote_rows: list[DivisionVoteSittingRow], division_id_to_minutes_id: dict[int, int]
) -> list[DivisionReviewItem]:
    key_to_list_source_to_vote_rows: defaultdict[
        tuple[int, int],
        defaultdict[DivisionVoteListSource, list[DivisionVoteSittingRow]],
    ] = defaultdict(lambda: defaultdict(list))
    for vote_row in vote_rows:
        if vote_row.vote_choice not in _COUNTED_VOTE_CHOICES:
            continue
        key_to_list_source_to_vote_rows[(vote_row.division_id, vote_row.speaker_id)][
            vote_row.list_source
        ].append(vote_row)
    items: list[DivisionReviewItem] = []
    for list_source_to_vote_rows in key_to_list_source_to_vote_rows.values():
        minutes_vote_rows = list_source_to_vote_rows[DivisionVoteListSource.MINUTES]
        hansard_vote_rows = list_source_to_vote_rows[DivisionVoteListSource.HANSARD]
        if len(minutes_vote_rows) != 1 or len(hansard_vote_rows) != 1:
            continue
        minutes_vote_row = minutes_vote_rows[0]
        hansard_vote_row = hansard_vote_rows[0]
        if minutes_vote_row.vote_choice == hansard_vote_row.vote_choice:
            continue
        items.append(
            DivisionReviewItem(
                kind=DivisionReviewItemKind.MEMBER_ON_DIFFERENT_SIDES_IN_TWO_LISTS,
                sitting_date=minutes_vote_row.sitting_date,
                division_id=minutes_vote_row.division_id,
                minutes_id=_get_minutes_id(minutes_vote_row, division_id_to_minutes_id),
                sprs_report_id=hansard_vote_row.sprs_report_id,
                source_text=f"minutes: {minutes_vote_row.printed_name}; Hansard: {hansard_vote_row.printed_name}",
                data_says=f"speaker {minutes_vote_row.speaker_id} is {minutes_vote_row.vote_choice} in the minutes list and {hansard_vote_row.vote_choice} in the Hansard list",
                rule=_DIFFERENT_SIDES_RULE,
            )
        )
    return items


def _build_vote_items(
    session: Session, inputs: _ReviewInputs
) -> list[DivisionReviewItem]:
    vote_rows = CRUDDivisionVote(session).get_sitting_date_rows_by_speaker_id_not_null()
    division_id_to_minutes_id = {
        minutes_division.division_id: minutes_division.minutes_id
        for minutes_division in inputs.minutes_divisions
    }
    return (
        _build_absent_vote_items(session, vote_rows, division_id_to_minutes_id)
        + _build_two_sides_items(vote_rows, division_id_to_minutes_id)
        + _build_different_sides_items(vote_rows, division_id_to_minutes_id)
    )


def _build_needs_review_items(stored_minutes: list[Minutes]) -> list[DivisionReviewItem]:
    return [
        DivisionReviewItem(
            kind=DivisionReviewItemKind.MINUTES_FILE_NEEDS_REVIEW,
            sitting_date=minutes.sitting_date,
            division_id=None,
            minutes_id=minutes.id,
            sprs_report_id=None,
            source_text=(minutes.extracted_text or "")[:_SOURCE_TEXT_LIMIT],
            data_says=minutes.status_note or "",
            rule=_NEEDS_REVIEW_RULE,
        )
        for minutes in stored_minutes
        if minutes.status == MinutesStatus.NEEDS_REVIEW
    ]


def get_division_review_list(session: Session) -> DivisionReviewList:
    stored_minutes = CRUDMinutes(session).get_by_statuses(list(MinutesStatus))
    minutes_id_to_sitting_date = {
        minutes.id: minutes.sitting_date
        for minutes in stored_minutes
        if minutes.id is not None
    }
    minutes_divisions = CRUDMinutesDivision(session).get_all()
    inputs = _ReviewInputs(
        minutes_divisions,
        minutes_id_to_sitting_date,
        get_pairable_hansard_divisions(
            session,
            sorted(
                {
                    minutes_id_to_sitting_date[minutes_division.minutes_id]
                    for minutes_division in minutes_divisions
                }
            ),
        ),
    )
    items = (
        _build_unread_division_row_items(session)
        + _build_list_status_items(session, inputs)
        + _build_pairing_items(inputs)
        + _build_stale_pairing_items(inputs)
        + _build_unpaired_hansard_division_items(session, inputs, stored_minutes)
        + _build_vote_items(session, inputs)
        + _build_needs_review_items(stored_minutes)
    )
    kind_counts = Counter(item.kind for item in items)
    decade_and_list_status_counts = Counter(
        (get_decade_label(division_row.sitting_date), division_row.list_status)
        for division_row in CRUDDivision(
            session
        ).get_list_status_rows_by_sprs_report_id_not_null()
    )
    minutes_decade_and_list_status_counts = Counter(
        (
            get_decade_label(minutes_id_to_sitting_date[minutes_division.minutes_id]),
            minutes_division.list_status,
        )
        for minutes_division in minutes_divisions
    )
    pairing_counts = Counter(
        minutes_division.pairing for minutes_division in minutes_divisions
    )
    return DivisionReviewList(
        items=items,
        kind_to_count={kind: kind_counts[kind] for kind in DivisionReviewItemKind},
        list_status_counts=[
            DivisionListStatusCount(
                decade=decade, list_status=list_status, division_count=division_count
            )
            for (decade, list_status), division_count in sorted(
                decade_and_list_status_counts.items()
            )
        ],
        minutes_list_status_counts=[
            MinutesListStatusCount(
                decade=decade,
                list_status=list_status,
                minutes_division_count=minutes_division_count,
            )
            for (decade, list_status), minutes_division_count in sorted(
                minutes_decade_and_list_status_counts.items()
            )
        ],
        pairing_counts=[
            MinutesDivisionPairingCount(
                pairing=pairing, minutes_division_count=minutes_division_count
            )
            for pairing, minutes_division_count in sorted(pairing_counts.items())
        ],
    )


def _format_share(count: int, total: int) -> str:
    if total == 0:
        return f"{count:,} of 0"
    return f"{count:,} of {total:,} ({count / total:.1%})"


def _get_list_status_lines(
    label: str,
    decade_and_list_status_to_count: dict[tuple[str, DivisionListStatus], int],
) -> list[str]:
    decade_to_total: Counter[str] = Counter()
    for (decade, _), count in decade_and_list_status_to_count.items():
        decade_to_total[decade] += count
    return [
        f"{label} of the {decade} by list status: "
        + ", ".join(
            f"{list_status} {_format_share(count, decade_to_total[decade])}"
            for (count_decade, list_status), count in sorted(
                decade_and_list_status_to_count.items()
            )
            if count_decade == decade
        )
        for decade in sorted(decade_to_total)
    ]


def get_summary_lines(review_list: DivisionReviewList) -> list[str]:
    expected_kind = DivisionReviewItemKind.MINUTES_DIVISION_WITHOUT_HANSARD_DIVISION
    defect_kind_to_count = {
        kind: count
        for kind, count in review_list.kind_to_count.items()
        if kind != expected_kind
    }
    lines = [
        f"Review items that are defects: {sum(defect_kind_to_count.values()):,}",
        "Defects by kind: "
        + (
            ", ".join(
                f"{kind} {count:,}"
                for kind, count in sorted(defect_kind_to_count.items())
                if count > 0
            )
            or "none"
        ),
        f"Expected, not defects, {expected_kind}: {review_list.kind_to_count[expected_kind]:,}",
    ]
    lines.extend(
        _get_list_status_lines(
            "Hansard divisions",
            {
                (list_status_count.decade, list_status_count.list_status): list_status_count.division_count
                for list_status_count in review_list.list_status_counts
            },
        )
    )
    lines.extend(
        _get_list_status_lines(
            "Minutes lists",
            {
                (list_status_count.decade, list_status_count.list_status): list_status_count.minutes_division_count
                for list_status_count in review_list.minutes_list_status_counts
            },
        )
    )
    pairing_total = sum(
        pairing_count.minutes_division_count
        for pairing_count in review_list.pairing_counts
    )
    lines.append(
        "Minutes divisions by pairing: "
        + (
            ", ".join(
                f"{pairing_count.pairing} {_format_share(pairing_count.minutes_division_count, pairing_total)}"
                for pairing_count in review_list.pairing_counts
            )
            or "none"
        )
    )
    return lines


def list_division_review_items(review_path: Path, summary_path: Path) -> None:
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_READ_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        review_list = get_division_review_list(session)
    lines = get_summary_lines(review_list)
    for line in lines:
        logger.info(line)
    review_path.write_text(review_list.model_dump_json(indent=1))
    summary_path.write_text("\n".join(lines) + "\n")
    logger.info(f"Wrote {review_path} and {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List the divisions, vote rows and minutes files that need a person's look, and the counts by kind, read only"
    )
    parser.add_argument(
        "--review-file",
        type=Path,
        required=True,
        help="where to write the review items as JSON, such as RUN/flags/votes.json",
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        required=True,
        help="where to write the summary lines",
    )
    arguments = parser.parse_args()
    list_division_review_items(arguments.review_file, arguments.summary_file)

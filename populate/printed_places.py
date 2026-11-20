from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session

from crud.report import CRUDReport, ReportPrintedPlaceTextRow
from crud.sitting import CRUDSitting
from enums import PrintedPlaceRule
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.printed_place_plan import (
    PlannedPrintedPlace,
    PrintedPlacePlan,
    PrintedPlaceRuleCount,
    SpeechNumberAgreement,
)
from services.printed_place import PlaceableReport, PrintedPlace, get_printed_places
from utils.printed_place_update import PrintedPlaceUpdate
from utils.sitting_dates import get_sitting_date_key

_SITTING_BATCH = 50


@dataclass(frozen=True)
class PairCount:
    pair_count: int
    agreeing_pair_count: int


def _get_pair_count(
    text_rows: list[ReportPrintedPlaceTextRow],
    report_id_to_printed_place: dict[str, PrintedPlace],
) -> PairCount:
    numbered_places = []
    for text_row in text_rows:
        printed_place = report_id_to_printed_place[text_row.report_id].printed_place
        if printed_place is None:
            continue
        numbered_places.append((text_row.speech_number, printed_place))
    pair_count = 0
    agreeing_pair_count = 0
    for i, (speech_number, printed_place) in enumerate(numbered_places):
        for other_speech_number, other_printed_place in numbered_places[i + 1 :]:
            if speech_number == other_speech_number:
                continue
            if printed_place == other_printed_place:
                continue
            pair_count += 1
            if (speech_number < other_speech_number) == (
                printed_place < other_printed_place
            ):
                agreeing_pair_count += 1
    return PairCount(pair_count, agreeing_pair_count)


def get_printed_place_plan(
    session: Session, sitting_dates: list[datetime]
) -> PrintedPlacePlan:
    rule_count_key_to_report_count: Counter[tuple[str, str, PrintedPlaceRule]] = (
        Counter()
    )
    report_version_to_pair_count: Counter[str] = Counter()
    report_version_to_agreeing_pair_count: Counter[str] = Counter()
    planned_printed_places: list[PlannedPrintedPlace] = []
    for sitting_date in sitting_dates:
        text_rows = CRUDReport(session).get_printed_place_text_rows_by_sitting_date(
            sitting_date
        )
        report_id_to_printed_place = get_printed_places(
            CRUDSitting(session).get_copy_row_by_sitting_date(
                get_sitting_date_key(sitting_date)
            ),
            [
                PlaceableReport(
                    text_row.report_id,
                    text_row.report_type,
                    text_row.speech_number,
                    text_row.original_title,
                    text_row.subtitle,
                    text_row.content,
                )
                for text_row in text_rows
            ],
        )
        for text_row in text_rows:
            printed_place = report_id_to_printed_place[text_row.report_id]
            rule_count_key_to_report_count[
                (
                    text_row.report_version,
                    text_row.report_type,
                    printed_place.printed_place_rule,
                )
            ] += 1
            if (
                text_row.printed_place == printed_place.printed_place
                and text_row.printed_place_rule == printed_place.printed_place_rule
            ):
                continue
            planned_printed_places.append(
                PlannedPrintedPlace(
                    report_id=text_row.id,
                    sprs_report_id=text_row.report_id,
                    sitting_date=sitting_date,
                    printed_place=printed_place.printed_place,
                    printed_place_rule=printed_place.printed_place_rule,
                )
            )
        if not text_rows:
            continue
        pair_count = _get_pair_count(text_rows, report_id_to_printed_place)
        report_version_to_pair_count[text_rows[0].report_version] += (
            pair_count.pair_count
        )
        report_version_to_agreeing_pair_count[text_rows[0].report_version] += (
            pair_count.agreeing_pair_count
        )
    return PrintedPlacePlan(
        sitting_dates=sitting_dates,
        printed_places=planned_printed_places,
        rule_counts=[
            PrintedPlaceRuleCount(
                report_version=report_version,
                report_type=report_type,
                printed_place_rule=printed_place_rule,
                report_count=report_count,
            )
            for (
                report_version,
                report_type,
                printed_place_rule,
            ), report_count in sorted(rule_count_key_to_report_count.items())
        ],
        speech_number_agreements=[
            SpeechNumberAgreement(
                report_version=report_version,
                pair_count=pair_count,
                agreeing_pair_count=report_version_to_agreeing_pair_count[
                    report_version
                ],
            )
            for report_version, pair_count in sorted(
                report_version_to_pair_count.items()
            )
        ],
    )


def _validate_can_commit_printed_places(
    session: Session, sitting_dates: list[datetime]
) -> None:
    sitting_date_to_printed_places: dict[datetime, set[int]] = {}
    for printed_place_row in CRUDReport(
        session
    ).get_printed_place_rows_by_sitting_dates(sitting_dates):
        if printed_place_row.printed_place is None:
            continue
        if printed_place_row.printed_place < 0:
            raise HansardWriteCheckError(
                f"Report {printed_place_row.id} of {printed_place_row.sitting_date:%Y-%m-%d} holds the negative place {printed_place_row.printed_place}"
            )
        if printed_place_row.printed_place_rule == PrintedPlaceRule.ASSENT_FIRST:
            continue
        printed_places = sitting_date_to_printed_places.setdefault(
            printed_place_row.sitting_date, set()
        )
        if printed_place_row.printed_place in printed_places:
            raise HansardWriteCheckError(
                f"Two reports of {printed_place_row.sitting_date:%Y-%m-%d} share the place {printed_place_row.printed_place}"
            )
        printed_places.add(printed_place_row.printed_place)


def write_printed_place_plan(session: Session, plan: PrintedPlacePlan) -> None:
    sitting_date_to_printed_place_updates: dict[datetime, list[PrintedPlaceUpdate]] = {}
    for planned_printed_place in plan.printed_places:
        sitting_date_to_printed_place_updates.setdefault(
            planned_printed_place.sitting_date, []
        ).append(
            PrintedPlaceUpdate(
                planned_printed_place.report_id,
                planned_printed_place.printed_place,
                planned_printed_place.printed_place_rule,
            )
        )
    sitting_dates = sorted(sitting_date_to_printed_place_updates)
    for start in range(0, len(sitting_dates), _SITTING_BATCH):
        batch_sitting_dates = sitting_dates[start : start + _SITTING_BATCH]
        printed_place_updates = [
            printed_place_update
            for sitting_date in batch_sitting_dates
            for printed_place_update in sitting_date_to_printed_place_updates[
                sitting_date
            ]
        ]
        update_count = CRUDReport(session).set_printed_places_bulk(
            printed_place_updates
        )
        if update_count != len(printed_place_updates):
            raise HansardWriteCheckError(
                f"Updated {update_count} printed places, planned {len(printed_place_updates)}"
            )
        _validate_can_commit_printed_places(session, batch_sitting_dates)
        session.commit()
        logger.info(
            f"Committed sittings {start + 1:,} to {start + len(batch_sitting_dates):,} of {len(sitting_dates):,}"
        )

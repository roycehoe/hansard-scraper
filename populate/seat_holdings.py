from collections import Counter
from dataclasses import dataclass, field

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.seat_holding import CRUDSeatHolding
from database.seat_holding import SeatHolding
from exceptions import HansardWriteCheckError
from logs import logger
from services.seat_holding import build_seat_holding_records
from utils.seat_holding_update import SeatHoldingUpdate

_SPEAKER_BATCH = 500
_YEARS_IN_DECADE = 10


@dataclass(frozen=True)
class SeatHoldingPlan:
    seat_holdings_to_add: list[SeatHolding] = field(default_factory=list)
    seat_holding_updates: list[SeatHoldingUpdate] = field(default_factory=list)
    seat_holding_widenings: list[SeatHoldingUpdate] = field(default_factory=list)
    seat_holding_ids_to_delete: list[int] = field(default_factory=list)
    decade_to_count: Counter[int] = field(default_factory=Counter)


def get_seat_holding_plan(session: Session, speaker_ids: list[int]) -> SeatHoldingPlan:
    plan = SeatHoldingPlan()
    sorted_speaker_ids = sorted(speaker_ids)
    for start in range(0, len(sorted_speaker_ids), _SPEAKER_BATCH):
        batch_speaker_ids = sorted_speaker_ids[start : start + _SPEAKER_BATCH]
        seat_holding_records = build_seat_holding_records(
            CRUDAttendance(
                session
            ).get_seat_rows_by_speaker_ids_and_location_name_not_null(batch_speaker_ids)
        )
        division_key_and_speaker_id_to_stored = {
            (seat_holding.division_key, seat_holding.speaker_id): SeatHoldingUpdate(
                seat_holding.id,
                seat_holding.first_sitting_date,
                seat_holding.last_sitting_date,
                seat_holding.sitting_count,
            )
            for seat_holding in CRUDSeatHolding(session).get_by_speaker_ids(
                batch_speaker_ids
            )
            if seat_holding.id is not None
        }
        planned_keys = set()
        for seat_holding_record in seat_holding_records:
            key = (seat_holding_record.division_key, seat_holding_record.speaker_id)
            planned_keys.add(key)
            plan.decade_to_count[
                seat_holding_record.first_sitting_date.year
                // _YEARS_IN_DECADE
                * _YEARS_IN_DECADE
            ] += 1
            stored_bounds = division_key_and_speaker_id_to_stored.get(key)
            if stored_bounds is None:
                plan.seat_holdings_to_add.append(
                    SeatHolding(
                        division_key=seat_holding_record.division_key,
                        location_name=seat_holding_record.location_name,
                        first_sitting_date=seat_holding_record.first_sitting_date,
                        last_sitting_date=seat_holding_record.last_sitting_date,
                        sitting_count=seat_holding_record.sitting_count,
                        speaker_id=seat_holding_record.speaker_id,
                    )
                )
                continue
            built_bounds = SeatHoldingUpdate(
                stored_bounds.id,
                seat_holding_record.first_sitting_date,
                seat_holding_record.last_sitting_date,
                seat_holding_record.sitting_count,
            )
            if built_bounds != stored_bounds:
                plan.seat_holding_updates.append(built_bounds)
            widened_bounds = SeatHoldingUpdate(
                stored_bounds.id,
                min(stored_bounds.first_sitting_date, built_bounds.first_sitting_date),
                max(stored_bounds.last_sitting_date, built_bounds.last_sitting_date),
                max(stored_bounds.sitting_count, built_bounds.sitting_count),
            )
            if widened_bounds != stored_bounds:
                plan.seat_holding_widenings.append(widened_bounds)
        plan.seat_holding_ids_to_delete.extend(
            stored_bounds.id
            for key, stored_bounds in division_key_and_speaker_id_to_stored.items()
            if key not in planned_keys
        )
    return plan


def _validate_can_commit_seat_holdings(session: Session, plan: SeatHoldingPlan) -> None:
    stored_decade_to_count = {
        decade_count.decade: decade_count.seat_holding_count
        for decade_count in CRUDSeatHolding(
            session
        ).get_first_sitting_date_decade_counts()
    }
    if stored_decade_to_count != dict(plan.decade_to_count):
        raise HansardWriteCheckError(
            f"Stored seat holdings by decade {stored_decade_to_count}, the plan has {dict(plan.decade_to_count)}"
        )
    mismatched_count = CRUDSeatHolding(
        session
    ).get_count_by_division_key_not_equal_folded_location_name()
    if mismatched_count != 0:
        raise HansardWriteCheckError(
            f"{mismatched_count} seat holdings hold a division_key that differs from the folded location_name"
        )


def write_seat_holding_plan(session: Session, plan: SeatHoldingPlan) -> None:
    deleted_count = CRUDSeatHolding(session).delete_by_ids(
        plan.seat_holding_ids_to_delete
    )
    if deleted_count != len(plan.seat_holding_ids_to_delete):
        raise HansardWriteCheckError(
            f"Deleted {deleted_count} seat holdings, read {len(plan.seat_holding_ids_to_delete)}"
        )
    CRUDSeatHolding(session).add_many(plan.seat_holdings_to_add)
    CRUDSeatHolding(session).update_many(plan.seat_holding_updates)
    _validate_can_commit_seat_holdings(session, plan)


# NOTE: inserts and widens only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_seat_holdings(session: Session, sitting_ids: list[int]) -> None:
    speaker_ids = CRUDAttendance(
        session
    ).get_distinct_speaker_ids_by_sitting_ids_and_speaker_id_not_null(sitting_ids)
    plan = get_seat_holding_plan(session, speaker_ids)
    CRUDSeatHolding(session).add_many(plan.seat_holdings_to_add)
    CRUDSeatHolding(session).update_many(plan.seat_holding_widenings)
    logger.info(
        f"Seat holdings: added {len(plan.seat_holdings_to_add)} rows, widened_bounds {len(plan.seat_holding_widenings)}"
    )

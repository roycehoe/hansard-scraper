from collections import Counter
from dataclasses import dataclass, field

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.sitting_span import CRUDSittingSpan
from database.sitting_span import SittingSpan
from exceptions import HansardWriteCheckError
from services.sitting_span import build_sitting_span_records
from utils.sitting_span_update import SittingSpanUpdate

_SPEAKER_BATCH = 500
_YEARS_IN_DECADE = 10


@dataclass(frozen=True)
class SittingSpanPlan:
    sitting_spans_to_add: list[SittingSpan] = field(default_factory=list)
    sitting_span_updates: list[SittingSpanUpdate] = field(default_factory=list)
    sitting_span_widenings: list[SittingSpanUpdate] = field(default_factory=list)
    sitting_span_ids_to_delete: list[int] = field(default_factory=list)
    decade_to_count: Counter[int] = field(default_factory=Counter)


def get_sitting_span_plan(session: Session, speaker_ids: list[int]) -> SittingSpanPlan:
    plan = SittingSpanPlan()
    sorted_speaker_ids = sorted(speaker_ids)
    for start in range(0, len(sorted_speaker_ids), _SPEAKER_BATCH):
        batch_speaker_ids = sorted_speaker_ids[start : start + _SPEAKER_BATCH]
        sitting_span_records = build_sitting_span_records(
            CRUDAttendance(session).get_sitting_date_rows_by_speaker_ids(
                batch_speaker_ids
            )
        )
        speaker_id_to_stored = {
            sitting_span.speaker_id: SittingSpanUpdate(
                sitting_span.id,
                sitting_span.first_sitting_date,
                sitting_span.last_sitting_date,
                sitting_span.sitting_count,
            )
            for sitting_span in CRUDSittingSpan(session).get_by_speaker_ids(
                batch_speaker_ids
            )
            if sitting_span.id is not None
        }
        planned_speaker_ids = set()
        for sitting_span_record in sitting_span_records:
            planned_speaker_ids.add(sitting_span_record.speaker_id)
            plan.decade_to_count[
                sitting_span_record.first_sitting_date.year
                // _YEARS_IN_DECADE
                * _YEARS_IN_DECADE
            ] += 1
            stored_bounds = speaker_id_to_stored.get(sitting_span_record.speaker_id)
            if stored_bounds is None:
                plan.sitting_spans_to_add.append(
                    SittingSpan(
                        first_sitting_date=sitting_span_record.first_sitting_date,
                        last_sitting_date=sitting_span_record.last_sitting_date,
                        sitting_count=sitting_span_record.sitting_count,
                        speaker_id=sitting_span_record.speaker_id,
                    )
                )
                continue
            built_bounds = SittingSpanUpdate(
                stored_bounds.id,
                sitting_span_record.first_sitting_date,
                sitting_span_record.last_sitting_date,
                sitting_span_record.sitting_count,
            )
            if built_bounds != stored_bounds:
                plan.sitting_span_updates.append(built_bounds)
            widened_bounds = SittingSpanUpdate(
                stored_bounds.id,
                min(stored_bounds.first_sitting_date, built_bounds.first_sitting_date),
                max(stored_bounds.last_sitting_date, built_bounds.last_sitting_date),
                max(stored_bounds.sitting_count, built_bounds.sitting_count),
            )
            if widened_bounds != stored_bounds:
                plan.sitting_span_widenings.append(widened_bounds)
        plan.sitting_span_ids_to_delete.extend(
            stored_bounds.id
            for speaker_id, stored_bounds in speaker_id_to_stored.items()
            if speaker_id not in planned_speaker_ids
        )
    return plan


def _validate_can_commit_sitting_spans(session: Session, plan: SittingSpanPlan) -> None:
    stored_decade_to_count = {
        decade_count.decade: decade_count.sitting_span_count
        for decade_count in CRUDSittingSpan(
            session
        ).get_first_sitting_date_decade_counts()
    }
    if stored_decade_to_count != dict(plan.decade_to_count):
        raise HansardWriteCheckError(
            f"Stored sitting spans by decade {stored_decade_to_count}, the plan has {dict(plan.decade_to_count)}"
        )


def write_sitting_span_plan(session: Session, plan: SittingSpanPlan) -> None:
    deleted_count = CRUDSittingSpan(session).delete_by_ids(
        plan.sitting_span_ids_to_delete
    )
    if deleted_count != len(plan.sitting_span_ids_to_delete):
        raise HansardWriteCheckError(
            f"Deleted {deleted_count} sitting spans, read {len(plan.sitting_span_ids_to_delete)}"
        )
    CRUDSittingSpan(session).add_many(plan.sitting_spans_to_add)
    CRUDSittingSpan(session).update_many(plan.sitting_span_updates)
    _validate_can_commit_sitting_spans(session, plan)

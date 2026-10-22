import argparse
import json
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from populate.speaker_links import (
    get_deputy_speaker_ids,
    get_role_context_speaker_ids,
    get_sitting_deputy_speaker_ids,
)
from schemas.speaker_link_plan import SpeakerLinkPlan
from services.attendance import build_speaker_lookups
from services.speaker_link import resolve_attendance_rows, resolve_speech_rows
from settings import settings
from utils.speaker_resolution import SpeakerLookups
from utils.write_target import validate_can_write


# NOTE: stage 8 writes each pass before the next one reads, so a row an earlier pass links keeps that pass's speaker here too.
def _get_speech_plan(session: Session, lookups: SpeakerLookups, name_parliament_number_to_speaker_id: dict[tuple[str, int], int]) -> dict[int, int]:
    resolved_speech_speaker_ids = resolve_speech_rows(CRUDSpeech(session).get_speaker_rows_by_speaker_id_null(), lookups, name_parliament_number_to_speaker_id)
    logger.info(f"Speech: set speaker_id on {len(resolved_speech_speaker_ids.id_to_speaker_id)}/{resolved_speech_speaker_ids.row_count} records")
    speech_id_to_speaker_id = resolved_speech_speaker_ids.id_to_speaker_id
    for get_pass_speaker_ids in (get_role_context_speaker_ids, get_deputy_speaker_ids, get_sitting_deputy_speaker_ids):
        for speech_id, speaker_id in get_pass_speaker_ids(session, lookups, name_parliament_number_to_speaker_id).items():
            speech_id_to_speaker_id.setdefault(speech_id, speaker_id)
    return speech_id_to_speaker_id


def _validate_can_commit_speech_speaker_ids(session: Session, speech_id_to_speaker_id: dict[int, Optional[int]]) -> None:
    stored_speech_id_to_speaker_id = {
        speaker_id_row.id: speaker_id_row.speaker_id
        for speaker_id_row in CRUDSpeech(session).get_speaker_id_rows_by_ids_for_update(list(speech_id_to_speaker_id))
    }
    if len(stored_speech_id_to_speaker_id) != len(speech_id_to_speaker_id):
        raise HansardWriteCheckError(f"{len(stored_speech_id_to_speaker_id)} of {len(speech_id_to_speaker_id)} planned speech rows are stored")
    for speech_id, speaker_id in speech_id_to_speaker_id.items():
        if stored_speech_id_to_speaker_id[speech_id] != speaker_id:
            raise HansardWriteCheckError(f"Speech row {speech_id} holds speaker {stored_speech_id_to_speaker_id[speech_id]}, expected {speaker_id}")


def _validate_can_commit_attendance_speaker_ids(session: Session, attendance_id_to_speaker_id: dict[int, Optional[int]]) -> None:
    attendances = CRUDAttendance(session).get_by_ids_for_update(list(attendance_id_to_speaker_id))
    if len(attendances) != len(attendance_id_to_speaker_id):
        raise HansardWriteCheckError(f"{len(attendances)} of {len(attendance_id_to_speaker_id)} planned attendance rows are stored")
    for attendance in attendances:
        if attendance.speaker_id != attendance_id_to_speaker_id[attendance.id]:
            raise HansardWriteCheckError(f"Attendance row {attendance.id} holds speaker {attendance.speaker_id}, expected {attendance_id_to_speaker_id[attendance.id]}")


def _get_plan(session: Session) -> SpeakerLinkPlan:
    speakers = CRUDSpeaker(session).get_all()
    name_parliament_number_to_speaker_id = {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None}
    lookups = build_speaker_lookups(speakers)
    speech_id_to_speaker_id = _get_speech_plan(session, lookups, name_parliament_number_to_speaker_id)
    resolved_attendance_speaker_ids = resolve_attendance_rows(CRUDAttendance(session).get_speaker_rows_by_speaker_id_null(), lookups, name_parliament_number_to_speaker_id)
    logger.info(
        f"Attendance: set speaker_id on {len(resolved_attendance_speaker_ids.id_to_speaker_id)}/{resolved_attendance_speaker_ids.row_count} records"
    )
    plan = SpeakerLinkPlan(speech_id_to_speaker_id=speech_id_to_speaker_id, attendance_id_to_speaker_id=resolved_attendance_speaker_ids.id_to_speaker_id)
    logger.info(f"Plan: {len(plan.speech_id_to_speaker_id)} speech rows, {len(plan.attendance_id_to_speaker_id)} attendance rows to link")
    return plan


def _read_plan(plan_path: Path) -> SpeakerLinkPlan:
    return SpeakerLinkPlan.model_validate_json(plan_path.read_text())


def apply_speaker_links(plan_path: Path, is_commit: bool) -> None:
    if not is_commit:
        with Session(engine) as session:
            plan = _get_plan(session)
        plan_path.write_text(json.dumps(plan.model_dump(), indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = _read_plan(plan_path)
    with Session(engine) as session:
        _validate_can_commit_speech_speaker_ids(session, dict.fromkeys(reviewed_plan.speech_id_to_speaker_id))
        _validate_can_commit_attendance_speaker_ids(session, dict.fromkeys(reviewed_plan.attendance_id_to_speaker_id))
        plan = _get_plan(session)
        if plan != reviewed_plan:
            raise HansardWriteCheckError("The plan differs from the reviewed plan")
        CRUDSpeech(session).set_speaker_ids_bulk(plan.speech_id_to_speaker_id)
        CRUDAttendance(session).set_speaker_ids_bulk(plan.attendance_id_to_speaker_id)
        _validate_can_commit_speech_speaker_ids(session, plan.speech_id_to_speaker_id)
        _validate_can_commit_attendance_speaker_ids(session, plan.attendance_id_to_speaker_id)
        session.commit()
    logger.info(f"Committed: {len(plan.speech_id_to_speaker_id)} speech rows and {len(plan.attendance_id_to_speaker_id)} attendance rows linked")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Link the stored speech and attendance rows that stage 8 would link, checked against a reviewed plan")
    parser.add_argument("plan", type=Path, help="the plan file: written by a dry run, read by --commit")
    parser.add_argument("--commit", action="store_true", help="lock the planned rows, check the plan is unchanged, and write it")
    arguments = parser.parse_args()
    apply_speaker_links(arguments.plan, arguments.commit)

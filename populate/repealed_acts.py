from pathlib import Path

from sqlmodel import Session

from crud.repealed_act_entry import CRUDRepealedActEntry
from crud.repealed_acts_capture import CRUDRepealedActsCapture
from database.repealed_acts import RepealedActEntry, RepealedActsCapture
from schemas.repealed_acts_capture import RepealedActsCaptureManifest
from schemas.repealed_acts_plan import (
    PlannedRepealedActEntry,
    PlannedRepealedActsCapture,
    RepealedActsPlan,
)
from services.repealed_acts import build_planned_entry, get_first_planned_entries
from utils.sso_listing import parse_sso_act_listing

_MANIFEST_FILE_NAME = "captures.json"


def get_repealed_acts_plan(captures_directory: Path) -> RepealedActsPlan:
    manifest = RepealedActsCaptureManifest.model_validate_json(
        (captures_directory / _MANIFEST_FILE_NAME).read_bytes()
    )
    planned_captures: list[PlannedRepealedActsCapture] = []
    planned_entries: list[PlannedRepealedActEntry] = []
    for manifest_entry in manifest.root:
        act_act_listing_rows = parse_sso_act_listing(
            (captures_directory / manifest_entry.file_name).read_text()
        )
        planned_captures.append(
            PlannedRepealedActsCapture(
                file_name=manifest_entry.file_name,
                original_url=manifest_entry.original_url,
                archive_timestamp=manifest_entry.archive_timestamp,
                capture_url=manifest_entry.capture_url,
                row_count=len(act_act_listing_rows),
            )
        )
        planned_entries.extend(
            build_planned_entry(act_listing_row, manifest_entry.capture_url)
            for act_listing_row in act_act_listing_rows
        )
    distinct_entries = get_first_planned_entries(planned_entries)
    return RepealedActsPlan(
        captures=planned_captures,
        entries=distinct_entries,
        duplicate_count=len(planned_entries) - len(distinct_entries),
    )


def write_repealed_acts_plan(
    session: Session, plan: RepealedActsPlan, captures_directory: Path
) -> None:
    stored_capture_urls = {
        capture_row.capture_url
        for capture_row in CRUDRepealedActsCapture(session).get_rows()
    }
    CRUDRepealedActsCapture(session).add_many(
        [
            RepealedActsCapture(
                original_url=planned_capture.original_url,
                archive_timestamp=planned_capture.archive_timestamp,
                capture_url=planned_capture.capture_url,
                content=(captures_directory / planned_capture.file_name).read_text(),
            )
            for planned_capture in plan.captures
            if planned_capture.capture_url not in stored_capture_urls
        ]
    )
    capture_url_to_id = {
        capture_row.capture_url: capture_row.id
        for capture_row in CRUDRepealedActsCapture(session).get_rows()
    }
    stored_sso_codes = {
        entry_row.sso_code for entry_row in CRUDRepealedActEntry(session).get_rows()
    }
    CRUDRepealedActEntry(session).add_many(
        [
            RepealedActEntry(
                printed_title=planned_entry.printed_title,
                printed_chapter=planned_entry.printed_chapter,
                link=planned_entry.link,
                sso_code=planned_entry.sso_code,
                enactment_year=planned_entry.enactment_year,
                repeal_date=planned_entry.repeal_date,
                last_version_date=planned_entry.last_version_date,
                capture_id=capture_url_to_id[planned_entry.capture_url],
            )
            for planned_entry in plan.entries
            if planned_entry.sso_code not in stored_sso_codes
        ]
    )

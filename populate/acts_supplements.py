from pathlib import Path

from sqlmodel import Session

from crud.acts_supplement_capture import CRUDActsSupplementCapture
from crud.acts_supplement_entry import CRUDActsSupplementEntry
from database.acts_supplement import ActsSupplementCapture, ActsSupplementEntry
from schemas.acts_supplement_capture import ActsSupplementCaptureManifest
from schemas.acts_supplement_plan import (
    ActsSupplementPlan,
    PlannedActsSupplementCapture,
    PlannedActsSupplementEntry,
)
from services.acts_supplement import build_planned_entry, get_first_planned_entries
from utils.sso_listing import parse_sso_listing

_MANIFEST_FILE_NAME = "captures.json"


def get_acts_supplement_plan(captures_directory: Path) -> ActsSupplementPlan:
    manifest = ActsSupplementCaptureManifest.model_validate_json(
        (captures_directory / _MANIFEST_FILE_NAME).read_bytes()
    )
    planned_captures: list[PlannedActsSupplementCapture] = []
    planned_entries: list[PlannedActsSupplementEntry] = []
    for manifest_entry in manifest.root:
        listing_rows = parse_sso_listing(
            (captures_directory / manifest_entry.file_name).read_text()
        )
        planned_captures.append(
            PlannedActsSupplementCapture(
                file_name=manifest_entry.file_name,
                original_url=manifest_entry.original_url,
                archive_timestamp=manifest_entry.archive_timestamp,
                capture_url=manifest_entry.capture_url,
                row_count=len(listing_rows),
            )
        )
        planned_entries.extend(
            build_planned_entry(listing_row, manifest_entry.capture_url)
            for listing_row in listing_rows
        )
    distinct_entries = get_first_planned_entries(planned_entries)
    return ActsSupplementPlan(
        captures=planned_captures,
        entries=distinct_entries,
        duplicate_count=len(planned_entries) - len(distinct_entries),
    )


def write_acts_supplement_plan(
    session: Session, plan: ActsSupplementPlan, captures_directory: Path
) -> None:
    stored_capture_urls = {
        capture_row.capture_url
        for capture_row in CRUDActsSupplementCapture(session).get_rows()
    }
    CRUDActsSupplementCapture(session).add_many(
        [
            ActsSupplementCapture(
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
        for capture_row in CRUDActsSupplementCapture(session).get_rows()
    }
    stored_act_numbers_and_links = {
        (entry_row.act_number, entry_row.link)
        for entry_row in CRUDActsSupplementEntry(session).get_rows()
    }
    CRUDActsSupplementEntry(session).add_many(
        [
            ActsSupplementEntry(
                printed_title=planned_entry.printed_title,
                printed_number=planned_entry.printed_number,
                link=planned_entry.link,
                pdf_link=planned_entry.pdf_link,
                pdf_size=planned_entry.pdf_size,
                act_number=planned_entry.act_number,
                publication_date=planned_entry.publication_date,
                capture_id=capture_url_to_id[planned_entry.capture_url],
            )
            for planned_entry in plan.entries
            if (planned_entry.act_number, planned_entry.link)
            not in stored_act_numbers_and_links
        ]
    )

from pathlib import Path

from sqlmodel import Session

from crud.bills_supplement_capture import CRUDBillsSupplementCapture
from crud.bills_supplement_entry import CRUDBillsSupplementEntry
from database.bills_supplement import BillsSupplementCapture, BillsSupplementEntry
from schemas.bills_supplement_capture import BillsSupplementCaptureManifest
from schemas.bills_supplement_plan import (
    BillsSupplementPlan,
    PlannedCapture,
    PlannedEntry,
)
from services.bills_supplement import (
    build_planned_entry,
    get_first_planned_entries,
    parse_bills_supplement_listing,
)

_MANIFEST_FILE_NAME = "captures.json"


def get_bills_supplement_plan(captures_directory: Path) -> BillsSupplementPlan:
    manifest = BillsSupplementCaptureManifest.model_validate_json(
        (captures_directory / _MANIFEST_FILE_NAME).read_bytes()
    )
    planned_captures: list[PlannedCapture] = []
    planned_entries: list[PlannedEntry] = []
    for manifest_entry in manifest.root:
        listing_rows = parse_bills_supplement_listing(
            (captures_directory / manifest_entry.file_name).read_text()
        )
        planned_captures.append(
            PlannedCapture(
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
    return BillsSupplementPlan(
        captures=planned_captures,
        entries=distinct_entries,
        duplicate_count=len(planned_entries) - len(distinct_entries),
    )


def write_bills_supplement_plan(
    session: Session, plan: BillsSupplementPlan, captures_directory: Path
) -> None:
    stored_capture_urls = {
        capture_row.capture_url
        for capture_row in CRUDBillsSupplementCapture(session).get_rows()
    }
    CRUDBillsSupplementCapture(session).add_many(
        [
            BillsSupplementCapture(
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
        for capture_row in CRUDBillsSupplementCapture(session).get_rows()
    }
    stored_bill_numbers_and_links = {
        (entry_row.bill_number, entry_row.link)
        for entry_row in CRUDBillsSupplementEntry(session).get_rows()
    }
    CRUDBillsSupplementEntry(session).add_many(
        [
            BillsSupplementEntry(
                printed_title=planned_entry.printed_title,
                printed_number=planned_entry.printed_number,
                link=planned_entry.link,
                pdf_link=planned_entry.pdf_link,
                pdf_size=planned_entry.pdf_size,
                bill_number=planned_entry.bill_number,
                publication_date=planned_entry.publication_date,
                capture_id=capture_url_to_id[planned_entry.capture_url],
            )
            for planned_entry in plan.entries
            if (planned_entry.bill_number, planned_entry.link)
            not in stored_bill_numbers_and_links
        ]
    )

import argparse
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session

from crud.act import ActRow, CRUDAct
from crud.act_history_entry import ActHistoryEntryRow, CRUDActHistoryEntry
from crud.bill_report import BillReportRow, CRUDBillReport
from database.act import ActHistoryEntry
from database.init import engine
from enums import BillLinkSource
from exceptions import HansardHandKeptEntryError, HansardWriteCheckError
from logs import logger
from populate.written_tables import vacuum_analyze_written_tables
from schemas.hand_kept_act_link import HandKeptActLink
from settings import settings
from utils.data_files import get_hand_kept_act_links
from utils.write_target import validate_can_write


@dataclass(frozen=True)
class HandKeptRelabel:
    act_history_entry_id: int
    sso_code: str
    ordinal: int
    stored_bill_link_source: Optional[BillLinkSource]


def get_hand_kept_relabels(
    hand_kept_act_links: list[HandKeptActLink],
    act_rows: list[ActRow],
    act_history_entry_rows: list[ActHistoryEntryRow],
    bill_report_rows: list[BillReportRow],
) -> list[HandKeptRelabel]:
    sso_code_to_act_id = {act_row.sso_code: act_row.id for act_row in act_rows}
    act_id_and_ordinal_to_entry = {
        (entry_row.act_id, entry_row.ordinal): entry_row
        for entry_row in act_history_entry_rows
    }
    bill_id_to_report_ids: dict[int, set[int]] = {}
    for bill_report_row in bill_report_rows:
        bill_id_to_report_ids.setdefault(bill_report_row.bill_id, set()).add(
            bill_report_row.report_id
        )
    hand_kept_relabels = []
    for hand_kept_act_link in hand_kept_act_links:
        try:
            entry_row = act_id_and_ordinal_to_entry[
                (
                    sso_code_to_act_id[hand_kept_act_link.sso_code],
                    hand_kept_act_link.ordinal,
                )
            ]
        except KeyError as error:
            raise HansardHandKeptEntryError(
                f"hand_kept_act_links.json: {hand_kept_act_link.sso_code} "
                f"{hand_kept_act_link.ordinal} is not a stored Legislative History entry"
            ) from error
        if entry_row.printed_title != hand_kept_act_link.printed_title:
            raise HansardHandKeptEntryError(
                f"hand_kept_act_links.json: {hand_kept_act_link.sso_code} "
                f"{hand_kept_act_link.ordinal} stores {entry_row.printed_title!r}, "
                f"not {hand_kept_act_link.printed_title!r}"
            )
        if entry_row.bill_id is None:
            raise HansardHandKeptEntryError(
                f"hand_kept_act_links.json: {hand_kept_act_link.sso_code} "
                f"{hand_kept_act_link.ordinal} is linked to no bill"
            )
        stored_report_ids = bill_id_to_report_ids.get(entry_row.bill_id, set())
        if stored_report_ids != set(hand_kept_act_link.report_ids):
            raise HansardHandKeptEntryError(
                f"hand_kept_act_links.json: {hand_kept_act_link.sso_code} "
                f"{hand_kept_act_link.ordinal} is linked to a bill that holds reports "
                f"{sorted(stored_report_ids)}, not the listed {hand_kept_act_link.report_ids}"
            )
        if entry_row.bill_link_source == BillLinkSource.HAND_KEPT:
            continue
        hand_kept_relabels.append(
            HandKeptRelabel(
                entry_row.id,
                hand_kept_act_link.sso_code,
                hand_kept_act_link.ordinal,
                entry_row.bill_link_source,
            )
        )
    return hand_kept_relabels


def _get_similar_entry_count(
    act_history_entry_rows: list[ActHistoryEntryRow],
) -> int:
    return sum(
        1
        for entry_row in act_history_entry_rows
        if entry_row.bill_link_source == BillLinkSource.SIMILAR_TITLE_READING_DATES
    )


def _validate_can_commit_relabels(
    session: Session, hand_kept_relabels: list[HandKeptRelabel], relabelled_count: int
) -> None:
    if relabelled_count != len(hand_kept_relabels):
        raise HansardWriteCheckError(
            f"Relabelled {relabelled_count} entries, planned {len(hand_kept_relabels)}"
        )
    stored_rows = CRUDActHistoryEntry(session).get_rows()
    entry_id_to_bill_link_source = {
        entry_row.id: entry_row.bill_link_source for entry_row in stored_rows
    }
    for hand_kept_relabel in hand_kept_relabels:
        if (
            entry_id_to_bill_link_source[hand_kept_relabel.act_history_entry_id]
            != BillLinkSource.HAND_KEPT
        ):
            raise HansardWriteCheckError(
                f"Entry {hand_kept_relabel.sso_code} {hand_kept_relabel.ordinal} does not read HAND_KEPT after the write"
            )
    remaining_similar_count = _get_similar_entry_count(stored_rows)
    if remaining_similar_count != 0:
        raise HansardWriteCheckError(
            f"{remaining_similar_count} entries still carry SIMILAR_TITLE_READING_DATES after the write"
        )


def apply_hand_kept_act_links(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    hand_kept_act_links = get_hand_kept_act_links()
    with Session(engine) as session:
        act_history_entry_rows = CRUDActHistoryEntry(session).get_rows()
        hand_kept_relabels = get_hand_kept_relabels(
            hand_kept_act_links,
            CRUDAct(session).get_rows(),
            act_history_entry_rows,
            CRUDBillReport(session).get_rows(),
        )
        for hand_kept_relabel in hand_kept_relabels:
            logger.info(
                f"{hand_kept_relabel.sso_code} {hand_kept_relabel.ordinal}: "
                f"{hand_kept_relabel.stored_bill_link_source} -> {BillLinkSource.HAND_KEPT}"
            )
        logger.info(
            f"Plan: {len(hand_kept_relabels):,} of {len(hand_kept_act_links):,} hand-kept entries to relabel; "
            f"{_get_similar_entry_count(act_history_entry_rows):,} stored entries carry SIMILAR_TITLE_READING_DATES"
        )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        relabelled_count = CRUDActHistoryEntry(session).set_bill_link_sources_bulk(
            {
                hand_kept_relabel.act_history_entry_id: BillLinkSource.HAND_KEPT
                for hand_kept_relabel in hand_kept_relabels
            }
        )
        _validate_can_commit_relabels(session, hand_kept_relabels, relabelled_count)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [ActHistoryEntry.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Label the Legislative History entries of data/hand_kept_act_links.json HAND_KEPT, after checking each entry's printed title and its bill's reports against the list"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check that every planned row reads HAND_KEPT and no stored row still carries SIMILAR_TITLE_READING_DATES; without it the script only logs the pairs",
    )
    arguments = parser.parse_args()
    apply_hand_kept_act_links(arguments.commit)

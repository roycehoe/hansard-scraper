from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session

from crud.attached_file import AttachedFileKeyRow, CRUDAttachedFile
from crud.attached_file_pointer import (
    AttachedFilePointerRow,
    CRUDAttachedFilePointer,
)
from crud.report import CRUDReport
from crud.sitting import CRUDSitting, SittingFileListRow
from crud.speech import CRUDSpeech, SpeechRow
from database.attached_file import AttachedFile
from database.attached_file_pointer import AttachedFilePointer
from enums import AttachedFileKind, AttachedFilePointerShape, ParagraphTieRule
from exceptions import HansardAttachedFileError, HansardWriteCheckError
from logs import logger
from services.attached_file import (
    build_attached_file_pointers,
    build_attached_files,
    get_attached_file_ties,
    get_bad_file_link_count,
    get_file_tie_count,
    is_paragraph_tie_stale,
)

_REPORT_BATCH = 200
_SITTING_BATCH = 200


@dataclass
class AttachedFileCounts:
    kind_to_row_count: Counter[AttachedFileKind] = field(default_factory=Counter)
    shape_to_row_count: Counter[AttachedFilePointerShape] = field(
        default_factory=Counter
    )
    tie_rule_to_row_count: Counter[Optional[ParagraphTieRule]] = field(
        default_factory=Counter
    )
    pointers_without_address: int = 0
    bad_file_links: int = 0


@dataclass(frozen=True)
class AttachedFilePlan:
    sprs_report_ids: list[str] = field(default_factory=list)
    attached_files: list[AttachedFile] = field(default_factory=list)
    attached_file_pointers: list[AttachedFilePointer] = field(default_factory=list)
    counts: AttachedFileCounts = field(default_factory=AttachedFileCounts)


def _get_sitting_attached_files(
    sitting_file_list_row: SittingFileListRow,
) -> list[AttachedFile]:
    try:
        return build_attached_files(
            sitting_file_list_row.id,
            sitting_file_list_row.annexures,
            sitting_file_list_row.vernaculars,
        )
    except HansardAttachedFileError as error:
        raise HansardAttachedFileError(
            f"Sitting id {sitting_file_list_row.id}: {error}"
        ) from error


def get_attached_file_plan(
    session: Session, report_ids: list[int], sitting_ids: list[int]
) -> AttachedFilePlan:
    plan = AttachedFilePlan()
    sorted_sitting_ids = sorted(sitting_ids)
    for start in range(0, len(sorted_sitting_ids), _SITTING_BATCH):
        for sitting_file_list_row in CRUDSitting(session).get_file_list_rows_by_ids(
            sorted_sitting_ids[start : start + _SITTING_BATCH]
        ):
            attached_files = _get_sitting_attached_files(sitting_file_list_row)
            plan.attached_files.extend(attached_files)
            plan.counts.kind_to_row_count.update(
                attached_file.kind for attached_file in attached_files
            )

    sorted_report_ids = sorted(report_ids)
    for start in range(0, len(sorted_report_ids), _REPORT_BATCH):
        report_rows = CRUDReport(session).get_attached_file_report_rows_by_ids(
            sorted_report_ids[start : start + _REPORT_BATCH]
        )
        report_id_to_speech_rows: defaultdict[int, list[SpeechRow]] = defaultdict(list)
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(
            [report_row.id for report_row in report_rows]
        ):
            report_id_to_speech_rows[speech_row.report_id].append(speech_row)
        for report_row in report_rows:
            attached_file_pointers = build_attached_file_pointers(
                report_row.report_id,
                report_row.content,
                report_id_to_speech_rows[report_row.id],
            )
            plan.sprs_report_ids.append(report_row.report_id)
            plan.attached_file_pointers.extend(attached_file_pointers)
            plan.counts.shape_to_row_count.update(
                attached_file_pointer.shape
                for attached_file_pointer in attached_file_pointers
            )
            plan.counts.tie_rule_to_row_count.update(
                attached_file_pointer.paragraph_tie_rule
                for attached_file_pointer in attached_file_pointers
            )
            plan.counts.pointers_without_address += sum(
                1
                for attached_file_pointer in attached_file_pointers
                if attached_file_pointer.download_value is None
            )
            plan.counts.bad_file_links += get_bad_file_link_count(report_row.content)
    return plan


def _get_download_values(plan: AttachedFilePlan) -> set[str]:
    download_values = {
        attached_file.download_value
        for attached_file in plan.attached_files
        if attached_file.download_value is not None
    }
    download_values.update(
        attached_file_pointer.download_value
        for attached_file_pointer in plan.attached_file_pointers
        if attached_file_pointer.download_value is not None
    )
    return download_values


def _set_file_ties(session: Session, download_values: set[str]) -> int:
    sorted_download_values = sorted(download_values)
    tied_count = 0
    for start in range(0, len(sorted_download_values), _REPORT_BATCH):
        batch_download_values = sorted_download_values[start : start + _REPORT_BATCH]
        ties = get_attached_file_ties(
            CRUDAttachedFilePointer(
                session
            ).get_untied_rows_by_download_values_and_attached_file_id_null(
                batch_download_values
            ),
            CRUDAttachedFile(session).get_rows_by_download_values(
                batch_download_values
            ),
        )
        tied_count += CRUDAttachedFilePointer(session).set_attached_file_ids_bulk(ties)
    return tied_count


def _build_planned_key_row(attached_file: AttachedFile) -> AttachedFileKeyRow:
    return AttachedFileKeyRow(
        attached_file.sitting_id,
        attached_file.kind,
        attached_file.sprs_file_id,
        attached_file.download_value,
        attached_file.printed_title,
    )


def _get_file_key(
    key_row: AttachedFileKeyRow,
) -> tuple[int, AttachedFileKind, int]:
    return (key_row.sitting_id, key_row.kind, key_row.sprs_file_id)


def _get_stored_file_keys(session: Session) -> set[tuple[int, AttachedFileKind, int]]:
    return {
        _get_file_key(key_row) for key_row in CRUDAttachedFile(session).get_key_rows()
    }


def _add_new_attached_files(
    session: Session, attached_files: list[AttachedFile]
) -> None:
    stored_file_keys = _get_stored_file_keys(session)
    CRUDAttachedFile(session).add_many(
        [
            attached_file
            for attached_file in attached_files
            if _get_file_key(_build_planned_key_row(attached_file))
            not in stored_file_keys
        ]
    )


def _build_planned_pointer_row(
    attached_file_pointer: AttachedFilePointer,
) -> AttachedFilePointerRow:
    return AttachedFilePointerRow(
        attached_file_pointer.sprs_report_id,
        attached_file_pointer.ordinal,
        attached_file_pointer.printed_text,
        attached_file_pointer.href,
        attached_file_pointer.shape,
        attached_file_pointer.download_value,
        attached_file_pointer.speech_ordinal,
        attached_file_pointer.paragraph_tie_rule,
    )


def _get_stored_pointer_rows_by_report(
    session: Session, sprs_report_ids: list[str]
) -> defaultdict[str, list[AttachedFilePointerRow]]:
    sprs_report_id_to_stored_rows: defaultdict[str, list[AttachedFilePointerRow]] = (
        defaultdict(list)
    )
    for stored_row in CRUDAttachedFilePointer(session).get_rows_by_sprs_report_ids(
        sprs_report_ids
    ):
        sprs_report_id_to_stored_rows[stored_row.sprs_report_id].append(stored_row)
    return sprs_report_id_to_stored_rows


def _get_planned_pointers_by_report(
    plan: AttachedFilePlan,
) -> defaultdict[str, list[AttachedFilePointer]]:
    sprs_report_id_to_planned_pointers: defaultdict[str, list[AttachedFilePointer]] = (
        defaultdict(list)
    )
    for attached_file_pointer in plan.attached_file_pointers:
        sprs_report_id_to_planned_pointers[attached_file_pointer.sprs_report_id].append(
            attached_file_pointer
        )
    return sprs_report_id_to_planned_pointers


def _replace_differing_report_pointers(
    session: Session, plan: AttachedFilePlan
) -> None:
    sprs_report_id_to_planned_pointers = _get_planned_pointers_by_report(plan)
    sorted_sprs_report_ids = sorted(plan.sprs_report_ids)
    for start in range(0, len(sorted_sprs_report_ids), _REPORT_BATCH):
        batch_sprs_report_ids = sorted_sprs_report_ids[start : start + _REPORT_BATCH]
        sprs_report_id_to_stored_rows = _get_stored_pointer_rows_by_report(
            session, batch_sprs_report_ids
        )
        differing_sprs_report_ids = [
            sprs_report_id
            for sprs_report_id in batch_sprs_report_ids
            if sprs_report_id_to_stored_rows[sprs_report_id]
            != [
                _build_planned_pointer_row(attached_file_pointer)
                for attached_file_pointer in sprs_report_id_to_planned_pointers[
                    sprs_report_id
                ]
            ]
        ]
        if not differing_sprs_report_ids:
            continue
        stored_count = sum(
            len(sprs_report_id_to_stored_rows[sprs_report_id])
            for sprs_report_id in differing_sprs_report_ids
        )
        deleted_count = CRUDAttachedFilePointer(session).delete_by_sprs_report_ids(
            differing_sprs_report_ids
        )
        if deleted_count != stored_count:
            raise HansardWriteCheckError(
                f"Deleted {deleted_count} attached file pointers, read {stored_count}"
            )
        CRUDAttachedFilePointer(session).add_many(
            [
                attached_file_pointer
                for sprs_report_id in differing_sprs_report_ids
                for attached_file_pointer in sprs_report_id_to_planned_pointers[
                    sprs_report_id
                ]
            ]
        )


def _validate_can_write_every_sitting(session: Session, plan: AttachedFilePlan) -> None:
    file_key_to_planned_key_row = {}
    for attached_file in plan.attached_files:
        planned_key_row = _build_planned_key_row(attached_file)
        file_key_to_planned_key_row[_get_file_key(planned_key_row)] = planned_key_row
    for stored_key_row in sorted(
        CRUDAttachedFile(session).get_key_rows(), key=_get_file_key
    ):
        planned_key_row = file_key_to_planned_key_row.get(_get_file_key(stored_key_row))
        if planned_key_row is None:
            raise HansardWriteCheckError(
                f"Stored attached file {stored_key_row} is not in the plan"
            )
        if planned_key_row != stored_key_row:
            raise HansardWriteCheckError(
                f"Stored attached file {stored_key_row} differs from the plan {planned_key_row}"
            )


def get_planned_file_tie_count(
    session: Session, plan: AttachedFilePlan, is_every_sitting: bool
) -> int:
    pointer_download_values = [
        attached_file_pointer.download_value
        for attached_file_pointer in plan.attached_file_pointers
        if attached_file_pointer.download_value is not None
    ]
    if is_every_sitting:
        return get_file_tie_count(
            pointer_download_values,
            [
                attached_file.download_value
                for attached_file in plan.attached_files
                if attached_file.download_value is not None
            ],
        )
    sorted_download_values = sorted(set(pointer_download_values))
    attached_file_download_values = []
    for start in range(0, len(sorted_download_values), _REPORT_BATCH):
        attached_file_download_values.extend(
            attached_file_row.download_value
            for attached_file_row in CRUDAttachedFile(
                session
            ).get_rows_by_download_values(
                sorted_download_values[start : start + _REPORT_BATCH]
            )
        )
    return get_file_tie_count(pointer_download_values, attached_file_download_values)


def _validate_can_commit_attached_files(
    session: Session, plan: AttachedFilePlan, is_every_sitting: bool
) -> None:
    stored_file_keys = _get_stored_file_keys(session)
    for attached_file in plan.attached_files:
        planned_key = _get_file_key(_build_planned_key_row(attached_file))
        if planned_key not in stored_file_keys:
            raise HansardWriteCheckError(
                f"Planned attached file {planned_key} is not stored"
            )

    sprs_report_id_to_planned_pointers = _get_planned_pointers_by_report(plan)
    sorted_sprs_report_ids = sorted(plan.sprs_report_ids)
    tied_count = 0
    for start in range(0, len(sorted_sprs_report_ids), _REPORT_BATCH):
        batch_sprs_report_ids = sorted_sprs_report_ids[start : start + _REPORT_BATCH]
        sprs_report_id_to_stored_rows = _get_stored_pointer_rows_by_report(
            session, batch_sprs_report_ids
        )
        for sprs_report_id in batch_sprs_report_ids:
            planned_rows = [
                _build_planned_pointer_row(attached_file_pointer)
                for attached_file_pointer in sprs_report_id_to_planned_pointers[
                    sprs_report_id
                ]
            ]
            if sprs_report_id_to_stored_rows[sprs_report_id] != planned_rows:
                raise HansardWriteCheckError(
                    f"Report {sprs_report_id}: stored attached file pointers differ from the plan"
                )
        tied_count += CRUDAttachedFilePointer(
            session
        ).get_count_by_sprs_report_ids_and_attached_file_id_not_null(
            batch_sprs_report_ids
        )

    planned_tied_count = get_planned_file_tie_count(session, plan, is_every_sitting)
    if tied_count != planned_tied_count:
        raise HansardWriteCheckError(
            f"{tied_count} attached file pointers hold a file, the plan has {planned_tied_count}"
        )


def write_attached_file_plan(
    session: Session, plan: AttachedFilePlan, is_every_sitting: bool
) -> None:
    if is_every_sitting:
        _validate_can_write_every_sitting(session, plan)
    _add_new_attached_files(session, plan.attached_files)
    _replace_differing_report_pointers(session, plan)
    _set_file_ties(session, _get_download_values(plan))
    _validate_can_commit_attached_files(session, plan, is_every_sitting)


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_attached_files(
    session: Session, report_ids: list[int], sitting_ids: list[int]
) -> None:
    plan = get_attached_file_plan(session, report_ids, sitting_ids)
    CRUDAttachedFile(session).add_many(plan.attached_files)
    CRUDAttachedFilePointer(session).add_many(plan.attached_file_pointers)
    tied_count = _set_file_ties(session, _get_download_values(plan))
    logger.info(
        f"Attached files: added {len(plan.attached_files)} files and {len(plan.attached_file_pointers)} pointers, set {tied_count} ties"
    )


def get_stale_paragraph_tie_count(session: Session, report_ids: list[int]) -> int:
    sorted_report_ids = sorted(report_ids)
    stale_count = 0
    for start in range(0, len(sorted_report_ids), _REPORT_BATCH):
        report_rows = CRUDReport(session).get_attached_file_report_rows_by_ids(
            sorted_report_ids[start : start + _REPORT_BATCH]
        )
        report_id_to_ordinal_to_transcript: defaultdict[int, dict[int, str]] = (
            defaultdict(dict)
        )
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(
            [report_row.id for report_row in report_rows]
        ):
            report_id_to_ordinal_to_transcript[speech_row.report_id][
                speech_row.ordinal
            ] = speech_row.transcript
        sprs_report_id_to_stored_rows = _get_stored_pointer_rows_by_report(
            session, [report_row.report_id for report_row in report_rows]
        )
        for report_row in report_rows:
            ordinal_to_transcript = report_id_to_ordinal_to_transcript[report_row.id]
            for stored_row in sprs_report_id_to_stored_rows[report_row.report_id]:
                if stored_row.speech_ordinal is None:
                    continue
                transcript = ordinal_to_transcript.get(stored_row.speech_ordinal)
                if transcript is None or is_paragraph_tie_stale(
                    stored_row.printed_text, transcript
                ):
                    stale_count += 1
    return stale_count

from dataclasses import dataclass

from sqlmodel import Session

from crud.report import CRUDReport
from crud.report_picture import CRUDReportPicture, ReportPictureRow
from database.report_picture import ReportPicture
from exceptions import HansardReportPictureError
from schemas.report_picture_plan import ReportPicturePlan
from services.report_picture import (
    InlinePicture,
    build_report_picture,
    get_inline_pictures,
)
from utils.report_picture_update import ReportPictureUpdate


@dataclass(frozen=True)
class ReportPictureWrite:
    pictures_to_insert: list[ReportPicture]
    picture_updates: list[ReportPictureUpdate]
    row_ids_to_delete: list[int]


def _get_report_id_to_inline_pictures(
    session: Session, report_ids: list[int]
) -> dict[int, list[InlinePicture]]:
    report_content_rows = CRUDReport(session).get_content_rows_by_ids(report_ids)
    missing_report_ids = sorted(
        set(report_ids)
        - {report_content_row.id for report_content_row in report_content_rows}
    )
    if missing_report_ids:
        raise HansardReportPictureError(
            f"{len(missing_report_ids)} reports of the plan are not stored, the first is {missing_report_ids[0]}"
        )
    report_id_to_inline_pictures: dict[int, list[InlinePicture]] = {}
    for report_content_row in report_content_rows:
        if report_content_row.content is None:
            raise HansardReportPictureError(
                f"Report {report_content_row.id} of the plan has no content"
            )
        report_id_to_inline_pictures[report_content_row.id] = get_inline_pictures(
            report_content_row.content
        )
    return report_id_to_inline_pictures


def get_planned_report_pictures(
    session: Session, plan: ReportPicturePlan
) -> list[ReportPicture]:
    report_id_to_inline_pictures = _get_report_id_to_inline_pictures(
        session,
        sorted({planned_picture.report_id for planned_picture in plan.pictures}),
    )
    return [
        build_report_picture(
            planned_picture, report_id_to_inline_pictures[planned_picture.report_id]
        )
        for planned_picture in plan.pictures
    ]


def _build_update_from_row(report_picture_row: ReportPictureRow) -> ReportPictureUpdate:
    return ReportPictureUpdate(
        id=report_picture_row.id,
        kind=report_picture_row.kind,
        content_offset=report_picture_row.content_offset,
        follows_ordinal=report_picture_row.follows_ordinal,
        typed_copy=report_picture_row.typed_copy,
    )


def _build_update_from_plan(
    row_id: int, report_picture: ReportPicture
) -> ReportPictureUpdate:
    return ReportPictureUpdate(
        id=row_id,
        kind=report_picture.kind,
        content_offset=report_picture.content_offset,
        follows_ordinal=report_picture.follows_ordinal,
        typed_copy=report_picture.typed_copy,
    )


def get_report_picture_write(
    session: Session, report_pictures: list[ReportPicture]
) -> ReportPictureWrite:
    picture_key_to_report_picture_row = {
        (
            report_picture_row.report_id,
            report_picture_row.picture_index,
            report_picture_row.sha256,
        ): report_picture_row
        for report_picture_row in CRUDReportPicture(session).get_rows()
    }
    planned_picture_keys = {
        (report_picture.report_id, report_picture.picture_index, report_picture.sha256)
        for report_picture in report_pictures
    }
    pictures_to_insert: list[ReportPicture] = []
    picture_updates: list[ReportPictureUpdate] = []
    for report_picture in report_pictures:
        report_picture_row = picture_key_to_report_picture_row.get(
            (
                report_picture.report_id,
                report_picture.picture_index,
                report_picture.sha256,
            )
        )
        if report_picture_row is None:
            pictures_to_insert.append(report_picture)
            continue
        planned_update = _build_update_from_plan(report_picture_row.id, report_picture)
        if planned_update != _build_update_from_row(report_picture_row):
            picture_updates.append(planned_update)
    row_ids_to_delete = [
        report_picture_row.id
        for picture_key, report_picture_row in picture_key_to_report_picture_row.items()
        if picture_key not in planned_picture_keys
    ]
    return ReportPictureWrite(pictures_to_insert, picture_updates, row_ids_to_delete)


def write_report_picture_plan(
    session: Session, report_pictures: list[ReportPicture]
) -> None:
    report_picture_write = get_report_picture_write(session, report_pictures)
    CRUDReportPicture(session).delete_by_ids(report_picture_write.row_ids_to_delete)
    CRUDReportPicture(session).update_many(report_picture_write.picture_updates)
    CRUDReportPicture(session).add_many(report_picture_write.pictures_to_insert)

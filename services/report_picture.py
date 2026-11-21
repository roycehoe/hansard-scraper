import base64
import binascii
import hashlib
import re
from dataclasses import dataclass

from database.report_picture import ReportPicture
from enums import PictureKind
from exceptions import HansardReportPictureError
from schemas.report_picture_plan import PlannedReportPicture

_IMAGE_TAG_PATTERN = r"<img\b[^>]*>"
_DATA_SOURCE_PATTERN = r"""src\s*=\s*(["'])data:([^;,"']*);base64,(.*?)\1"""
_WHITESPACE_PATTERN = r"\s"
_BASE64_BLOCK_LENGTH = 4


@dataclass(frozen=True)
class InlinePicture:
    content_offset: int
    media_type: str
    picture_bytes: bytes


def _get_picture_bytes(encoded_picture: str, content_offset: int) -> bytes:
    stripped_picture = re.sub(_WHITESPACE_PATTERN, "", encoded_picture)
    padding = "=" * (-len(stripped_picture) % _BASE64_BLOCK_LENGTH)
    try:
        return base64.b64decode(stripped_picture + padding, validate=True)
    except binascii.Error as error:
        raise HansardReportPictureError(
            f"The inline picture at offset {content_offset} is not valid base64"
        ) from error


def get_inline_pictures(content: str) -> list[InlinePicture]:
    inline_pictures: list[InlinePicture] = []
    for tag_match in re.finditer(
        _IMAGE_TAG_PATTERN, content, re.IGNORECASE | re.DOTALL
    ):
        source_match = re.search(
            _DATA_SOURCE_PATTERN, tag_match.group(0), re.IGNORECASE | re.DOTALL
        )
        if source_match is None:
            continue
        inline_pictures.append(
            InlinePicture(
                content_offset=tag_match.start(),
                media_type=source_match.group(2).strip().lower(),
                picture_bytes=_get_picture_bytes(
                    source_match.group(3), tag_match.start()
                ),
            )
        )
    return inline_pictures


def build_report_picture(
    planned_picture: PlannedReportPicture, inline_pictures: list[InlinePicture]
) -> ReportPicture:
    try:
        inline_picture = inline_pictures[planned_picture.picture_index]
    except IndexError as error:
        raise HansardReportPictureError(
            f"Report {planned_picture.report_id} holds {len(inline_pictures)} inline pictures, the plan names picture {planned_picture.picture_index}"
        ) from error
    if inline_picture.content_offset != planned_picture.content_offset:
        raise HansardReportPictureError(
            f"Picture {planned_picture.picture_index} of report {planned_picture.report_id} starts at {inline_picture.content_offset}, the plan has {planned_picture.content_offset}"
        )
    picture_sha256 = hashlib.sha256(inline_picture.picture_bytes).hexdigest()
    if picture_sha256 != planned_picture.sha256:
        raise HansardReportPictureError(
            f"Picture {planned_picture.picture_index} of report {planned_picture.report_id} has SHA-256 {picture_sha256}, the plan has {planned_picture.sha256}"
        )
    if inline_picture.media_type != planned_picture.media_type:
        raise HansardReportPictureError(
            f"Picture {planned_picture.picture_index} of report {planned_picture.report_id} is {inline_picture.media_type}, the plan has {planned_picture.media_type}"
        )
    if (
        planned_picture.kind == PictureKind.OTHER
        and planned_picture.typed_copy is not None
    ):
        raise HansardReportPictureError(
            f"Picture {planned_picture.picture_index} of report {planned_picture.report_id} is kind OTHER and has a typed copy"
        )
    if planned_picture.kind != PictureKind.OTHER and planned_picture.typed_copy is None:
        raise HansardReportPictureError(
            f"Picture {planned_picture.picture_index} of report {planned_picture.report_id} is kind {planned_picture.kind.value} and has no typed copy"
        )
    return ReportPicture(
        kind=planned_picture.kind,
        picture_index=planned_picture.picture_index,
        content_offset=planned_picture.content_offset,
        follows_ordinal=planned_picture.follows_ordinal,
        media_type=inline_picture.media_type,
        size_bytes=len(inline_picture.picture_bytes),
        sha256=picture_sha256,
        picture_bytes=inline_picture.picture_bytes,
        typed_copy=None
        if planned_picture.typed_copy is None
        else planned_picture.typed_copy.model_dump(),
        report_id=planned_picture.report_id,
    )

import re
from typing import Optional

from pydantic import ValidationError

from database.attached_file import AttachedFile
from enums import AttachedFileKind
from exceptions import HansardAttachedFileError
from schemas.attached_file_list import (
    LIST_PATH_MARKER,
    HansardAnnexureEntries,
    HansardAnnexureEntry,
    HansardVernacularEntries,
    HansardVernacularEntry,
)

_PLACEHOLDER_VALUE_RE = re.compile(r"^\d{8}/(?:annex|vernacular)-null$")


def get_annexure_entries(annexures: Optional[str]) -> list[HansardAnnexureEntry]:
    if annexures is None:
        return []
    try:
        return HansardAnnexureEntries.model_validate_json(annexures).root
    except ValidationError as error:
        first_error = error.errors()[0]
        raise HansardAttachedFileError(
            f"annexureList could not be read: {first_error['msg']} at {first_error['loc']}"
        ) from error


def get_vernacular_entries(vernaculars: Optional[str]) -> list[HansardVernacularEntry]:
    if vernaculars is None:
        return []
    try:
        return HansardVernacularEntries.model_validate_json(vernaculars).root
    except ValidationError as error:
        first_error = error.errors()[0]
        raise HansardAttachedFileError(
            f"vernacularList could not be read: {first_error['msg']} at {first_error['loc']}"
        ) from error


def _get_download_value(file_path: str) -> Optional[str]:
    download_value = file_path.split(LIST_PATH_MARKER, 1)[1]
    if _PLACEHOLDER_VALUE_RE.match(download_value):
        return None
    return download_value


def build_attached_files(
    sitting_id: int, annexures: Optional[str], vernaculars: Optional[str]
) -> list[AttachedFile]:
    attached_files = [
        AttachedFile(
            kind=AttachedFileKind.ANNEX,
            sprs_file_id=entry.annexure_id,
            printed_title=entry.annexure_title,
            printed_file_path=entry.file_path,
            file_name=entry.file_name,
            section_type=entry.section_type,
            download_value=_get_download_value(entry.file_path),
            sitting_id=sitting_id,
        )
        for entry in get_annexure_entries(annexures)
    ]
    attached_files.extend(
        AttachedFile(
            kind=AttachedFileKind.VERNACULAR,
            sprs_file_id=entry.vernacular_id,
            printed_title=entry.vernacular_title,
            printed_file_path=entry.file_path,
            file_name=entry.file_name,
            section_type=None,
            download_value=_get_download_value(entry.file_path),
            sitting_id=sitting_id,
        )
        for entry in get_vernacular_entries(vernaculars)
    )

    key_to_attached_file: dict[tuple[AttachedFileKind, str, str], AttachedFile] = {}
    for attached_file in sorted(
        attached_files, key=lambda attached_file: attached_file.sprs_file_id
    ):
        key_to_attached_file.setdefault(
            (
                attached_file.kind,
                attached_file.printed_title,
                attached_file.printed_file_path,
            ),
            attached_file,
        )
    return list(key_to_attached_file.values())

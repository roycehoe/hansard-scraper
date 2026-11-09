import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from crud.speech import SpeechRow
from database.attached_file import AttachedFile
from database.attached_file_pointer import AttachedFilePointer
from enums import AttachedFileKind, AttachedFilePointerShape
from exceptions import HansardAttachedFileError
from schemas.attached_file_list import (
    LIST_PATH_MARKER,
    HansardAnnexureEntries,
    HansardAnnexureEntry,
    HansardVernacularEntries,
    HansardVernacularEntry,
)

_PLACEHOLDER_VALUE_RE = re.compile(r"^\d{8}/(?:annex|vernacular)-null$")
_DOWNLOAD_PREFIX = "/search/search/download?value="
_ABSOLUTE_DOWNLOAD_PREFIX = "https://sprs.parl.gov.sg/search/search/download?value="
_DATED_VALUE_RE = re.compile(r"^\d{8}/(?:annex|vernacular)-.+", re.DOTALL)
_PDFS_VALUE_RE = re.compile(r"^PDFs/.+", re.DOTALL)
_SECTION_FILE_VALUE_RE = re.compile(
    r"^\d+_\d{8}_S\d+_T\d+\.pdf\s*$", re.DOTALL | re.IGNORECASE
)
_BAD_HREF_RE = re.compile(r"\s*(?:\d+|\.)\s*")
_FILE_LINK_TEXT_RE = re.compile(r"vernacular|annex|appendix|please refer")
_ZERO_WIDTH_SPACE = "\u200b"
_NO_BREAK_SPACE = "\xa0"
_MARKDOWN_MARKER_RE = re.compile(r"\*\*|_")
_WHITESPACE_RE = re.compile(r"\s+")


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


def _normalize_text(text: str) -> str:
    text = text.replace(_ZERO_WIDTH_SPACE, "").replace(_NO_BREAK_SPACE, " ")
    text = _MARKDOWN_MARKER_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _get_link_value(href: str) -> Optional[str]:
    if href.startswith(_DOWNLOAD_PREFIX):
        return href[len(_DOWNLOAD_PREFIX) :]
    if href.startswith(_ABSOLUTE_DOWNLOAD_PREFIX):
        return href[len(_ABSOLUTE_DOWNLOAD_PREFIX) :]
    return None


def _get_pointer_shape(value: str) -> Optional[AttachedFilePointerShape]:
    if _DATED_VALUE_RE.match(value):
        return AttachedFilePointerShape.DATED
    if _PDFS_VALUE_RE.match(value):
        return AttachedFilePointerShape.PDFS
    if _SECTION_FILE_VALUE_RE.match(value):
        return AttachedFilePointerShape.SECTION_FILE
    return None


@dataclass(frozen=True)
class _PointerLink:
    tag: Tag
    href: str
    value: str
    shape: AttachedFilePointerShape


def _get_pointer_links(soup: BeautifulSoup) -> list[_PointerLink]:
    pointer_links = []
    for tag in soup.select("a[href]"):
        href = str(tag["href"])
        value = _get_link_value(href)
        if value is None:
            continue
        shape = _get_pointer_shape(value)
        if shape is None:
            continue
        pointer_links.append(_PointerLink(tag, href, value, shape))
    return pointer_links


def build_attached_file_pointers(
    sprs_report_id: str, content: Optional[str], speech_rows: list[SpeechRow]
) -> list[AttachedFilePointer]:
    if content is None:
        return []
    soup = BeautifulSoup(content, "html.parser")
    return [
        AttachedFilePointer(
            ordinal=ordinal,
            printed_text=pointer_link.tag.get_text(),
            href=pointer_link.href,
            shape=pointer_link.shape,
            download_value=None
            if _PLACEHOLDER_VALUE_RE.match(pointer_link.value)
            else pointer_link.value,
            sprs_report_id=sprs_report_id,
        )
        for ordinal, pointer_link in enumerate(_get_pointer_links(soup), 1)
    ]


def get_bad_file_link_count(content: Optional[str]) -> int:
    if content is None:
        return 0
    soup = BeautifulSoup(content, "html.parser")
    return sum(
        1
        for tag in soup.select("a[href]")
        if _BAD_HREF_RE.fullmatch(str(tag["href"]))
        and _FILE_LINK_TEXT_RE.search(_normalize_text(tag.get_text()).lower())
    )

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from crud.attached_file import AttachedFileRow
from crud.attached_file_pointer import AttachedFilePointerUntiedRow
from crud.speech import SpeechRow
from database.attached_file import AttachedFile
from database.attached_file_pointer import AttachedFilePointer
from enums import AttachedFileKind, AttachedFilePointerShape, ParagraphTieRule
from exceptions import HansardAttachedFileError
from schemas.attached_file_list import (
    LIST_PATH_MARKER,
    HansardAnnexureEntries,
    HansardAnnexureEntry,
    HansardVernacularEntries,
    HansardVernacularEntry,
)
from utils.attached_file_tie import AttachedFilePointerTie

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
_POINTER_POSITION_RE = re.compile("\x01(\\d+)\x02")


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


@dataclass(frozen=True)
class _ParagraphTie:
    speech_ordinal: Optional[int]
    paragraph_tie_rule: Optional[ParagraphTieRule]


def _get_occurrence_ordinals(
    words: str, ordinal_to_normalized_transcript: dict[int, str]
) -> list[int]:
    occurrence_ordinals = []
    for ordinal, normalized_transcript in ordinal_to_normalized_transcript.items():
        start = 0
        while True:
            position = normalized_transcript.find(words, start)
            if position == -1:
                break
            occurrence_ordinals.append(ordinal)
            start = position + len(words)
    return occurrence_ordinals


def _get_paragraph_tie_rule(text_count: int, pointer_count: int) -> ParagraphTieRule:
    if text_count == 1:
        return ParagraphTieRule.ONLY_OCCURRENCE
    if text_count == pointer_count:
        return ParagraphTieRule.EVERY_OCCURRENCE_A_LINK
    return ParagraphTieRule.OCCURRENCE_BESIDE_PLAIN_TEXT


def _get_paragraph_ties(
    pointer_links: list[_PointerLink],
    soup: BeautifulSoup,
    speech_rows: list[SpeechRow],
) -> list[_ParagraphTie]:
    pointer_words = [
        _normalize_text(pointer_link.tag.get_text()) for pointer_link in pointer_links
    ]
    for pointer_index, pointer_link in enumerate(pointer_links):
        pointer_link.tag.insert_before(f"\x01{pointer_index}\x02")

    parts = _POINTER_POSITION_RE.split(soup.get_text())
    whole_text = parts[0]
    pointer_index_to_offset: dict[int, int] = {}
    for part_index in range(1, len(parts), 2):
        pointer_index_to_offset[int(parts[part_index])] = len(whole_text)
        whole_text += parts[part_index + 1]

    normalized_whole_text = _normalize_text(whole_text)
    words_to_pointer_count = Counter(pointer_words)
    ordinal_to_normalized_transcript = {
        speech_row.ordinal: _normalize_text(speech_row.transcript)
        for speech_row in speech_rows
    }
    paragraph_ties = []
    for pointer_index, words in enumerate(pointer_words):
        if not words:
            paragraph_ties.append(_ParagraphTie(None, None))
            continue
        text_count = normalized_whole_text.count(words)
        occurrence_ordinals = _get_occurrence_ordinals(
            words, ordinal_to_normalized_transcript
        )
        occurrence_index = _normalize_text(
            whole_text[: pointer_index_to_offset[pointer_index]]
        ).count(words)
        if len(occurrence_ordinals) != text_count:
            paragraph_ties.append(_ParagraphTie(None, None))
            continue
        if occurrence_index >= len(occurrence_ordinals):
            paragraph_ties.append(_ParagraphTie(None, None))
            continue
        paragraph_ties.append(
            _ParagraphTie(
                occurrence_ordinals[occurrence_index],
                _get_paragraph_tie_rule(text_count, words_to_pointer_count[words]),
            )
        )
    return paragraph_ties


def build_attached_file_pointers(
    sprs_report_id: str, content: Optional[str], speech_rows: list[SpeechRow]
) -> list[AttachedFilePointer]:
    if content is None:
        return []
    soup = BeautifulSoup(content, "html.parser")
    pointer_links = _get_pointer_links(soup)
    attached_file_pointers = [
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
        for ordinal, pointer_link in enumerate(pointer_links, 1)
    ]
    paragraph_ties = _get_paragraph_ties(pointer_links, soup, speech_rows)
    for attached_file_pointer, paragraph_tie in zip(
        attached_file_pointers, paragraph_ties, strict=True
    ):
        attached_file_pointer.speech_ordinal = paragraph_tie.speech_ordinal
        attached_file_pointer.paragraph_tie_rule = paragraph_tie.paragraph_tie_rule
    return attached_file_pointers


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


def get_attached_file_ties(
    attached_file_pointer_untied_rows: list[AttachedFilePointerUntiedRow],
    attached_file_rows: list[AttachedFileRow],
) -> list[AttachedFilePointerTie]:
    download_value_to_attached_file_ids: defaultdict[str, list[int]] = defaultdict(list)
    for attached_file_row in attached_file_rows:
        download_value_to_attached_file_ids[attached_file_row.download_value].append(
            attached_file_row.id
        )
    ties = []
    for attached_file_pointer_untied_row in attached_file_pointer_untied_rows:
        attached_file_ids = download_value_to_attached_file_ids[
            attached_file_pointer_untied_row.download_value
        ]
        if len(attached_file_ids) != 1:
            continue
        ties.append(
            AttachedFilePointerTie(
                attached_file_pointer_untied_row.id, attached_file_ids[0]
            )
        )
    return ties


def is_paragraph_tie_stale(printed_text: str, transcript: str) -> bool:
    return _normalize_text(printed_text) not in _normalize_text(transcript)


def get_file_tie_count(
    pointer_download_values: list[str], attached_file_download_values: list[str]
) -> int:
    download_value_to_file_count = Counter(attached_file_download_values)
    return sum(
        1
        for download_value in pointer_download_values
        if download_value_to_file_count[download_value] == 1
    )

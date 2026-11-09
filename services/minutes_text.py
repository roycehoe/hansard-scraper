import io
import re
import struct
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError, PyPdfError

from enums import MinutesFileFormat, MinutesStatus
from exceptions import HansardMinutesFileError

_PDF_SIGNATURE = b"%PDF"
_OLE2_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")
_PAGE_SEPARATOR = "\n"

_HEADER_SECTOR_SHIFT_OFFSET = 0x1E
_HEADER_MINI_SECTOR_SHIFT_OFFSET = 0x20
_HEADER_FAT_SECTOR_COUNT_OFFSET = 0x2C
_HEADER_FIRST_DIRECTORY_SECTOR_OFFSET = 0x30
_HEADER_MINI_STREAM_CUTOFF_OFFSET = 0x38
_HEADER_FIRST_MINI_FAT_SECTOR_OFFSET = 0x3C
_HEADER_FIRST_DIFAT_SECTOR_OFFSET = 0x44
_HEADER_DIFAT_SECTOR_COUNT_OFFSET = 0x48
_HEADER_DIFAT_ENTRIES_OFFSET = 0x4C
_HEADER_DIFAT_ENTRY_COUNT = 109
_MAX_REGULAR_SECTOR = 0xFFFFFFFA
_DIRECTORY_ENTRY_SIZE = 128
_DIRECTORY_NAME_LENGTH_OFFSET = 64
_DIRECTORY_START_SECTOR_OFFSET = 116
_DIRECTORY_SIZE_OFFSET = 120
_ROOT_ENTRY_NAME = "Root Entry"
_WORD_DOCUMENT_STREAM_NAME = "WordDocument"
_ZERO_TABLE_STREAM_NAME = "0Table"
_ONE_TABLE_STREAM_NAME = "1Table"
_FIB_FLAGS_OFFSET = 0x0A
_FIB_IS_ENCRYPTED_FLAG = 0x0100
_FIB_IS_ONE_TABLE_FLAG = 0x0200
_FIB_CHARACTER_COUNT_OFFSET = 0x4C
_FIB_CLX_OFFSET = 0x1A2
_FIB_CLX_LENGTH_OFFSET = 0x1A6
_CLX_PRC_MARKER = 0x01
_CLX_PCDT_MARKER = 0x02
_PIECE_DESCRIPTOR_SIZE = 8
_PIECE_ENTRY_SIZE = 12
_PIECE_POSITION_SIZE = 4
_PIECE_IS_EIGHT_BIT_FLAG = 0x40000000
_PIECE_OFFSET_MASK = 0x3FFFFFFF
_EIGHT_BIT_ENCODING = "cp1252"
_SIXTEEN_BIT_ENCODING = "utf-16-le"
_WORD_PARAGRAPH_MARK = "\r"
_HEAD_CHARACTER_COUNT = 1_500
_HEAD_DATE_PATTERN = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+),?\s+(\d{4})",
    re.IGNORECASE,
)
_HEAD_DATE_FORMAT = "%d %B %Y"
_HEAD_TITLE_PATTERN = re.compile(r"votes\s+and\s+proceedings", re.IGNORECASE)


@dataclass(frozen=True)
class MinutesTextOutcome:
    status: MinutesStatus
    status_note: Optional[str]


@dataclass(frozen=True)
class _DirectoryEntry:
    start_sector: int
    size: int


@dataclass(frozen=True)
class _Ole2Container:
    content: bytes
    sector_size: int
    mini_sector_size: int
    mini_stream_cutoff: int
    fat: tuple[int, ...]
    mini_fat: tuple[int, ...]
    directory: dict[str, _DirectoryEntry]


def get_minutes_file_format(content: bytes) -> MinutesFileFormat:
    if content.startswith(_PDF_SIGNATURE):
        return MinutesFileFormat.PDF
    if content.startswith(_OLE2_SIGNATURE):
        return MinutesFileFormat.WORD
    raise HansardMinutesFileError("The file is neither a PDF nor a Word file")


def get_minutes_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        page_texts = [
            page.extract_text(extraction_mode="layout") for page in reader.pages
        ]
    except FileNotDecryptedError as error:
        raise HansardMinutesFileError("The PDF is encrypted") from error
    except PdfReadError as error:
        raise HansardMinutesFileError("The PDF cannot be read") from error
    except PyPdfError as error:
        raise HansardMinutesFileError("The PDF cannot be read") from error
    except ValueError as error:
        raise HansardMinutesFileError("The PDF cannot be read") from error
    except KeyError as error:
        raise HansardMinutesFileError("The PDF cannot be read") from error
    except IndexError as error:
        raise HansardMinutesFileError("The PDF cannot be read") from error
    if not page_texts:
        raise HansardMinutesFileError("The PDF holds no pages")
    for number, page_text in enumerate(page_texts, 1):
        if not page_text.strip():
            raise HansardMinutesFileError(f"PDF page {number} holds no text")
    return _PAGE_SEPARATOR.join(page_texts)


def _read_exact(content: bytes, start: int, length: int) -> bytes:
    piece = content[start : start + length]
    if len(piece) != length:
        raise IndexError("The file ends inside a structure")
    return piece


def _read_uint16(content: bytes, offset: int) -> int:
    return struct.unpack_from("<H", content, offset)[0]


def _read_uint32(content: bytes, offset: int) -> int:
    return struct.unpack_from("<I", content, offset)[0]


def _read_sector(content: bytes, sector_size: int, sector: int) -> bytes:
    return _read_exact(content, (sector + 1) * sector_size, sector_size)


def _get_fat_sectors(content: bytes, sector_size: int) -> list[int]:
    fat_sector_count = _read_uint32(content, _HEADER_FAT_SECTOR_COUNT_OFFSET)
    fat_sectors = list(
        struct.unpack_from(
            f"<{_HEADER_DIFAT_ENTRY_COUNT}I", content, _HEADER_DIFAT_ENTRIES_OFFSET
        )
    )
    difat_sector = _read_uint32(content, _HEADER_FIRST_DIFAT_SECTOR_OFFSET)
    for _ in range(_read_uint32(content, _HEADER_DIFAT_SECTOR_COUNT_OFFSET)):
        difat_entries = struct.unpack(
            f"<{sector_size // 4}I", _read_sector(content, sector_size, difat_sector)
        )
        fat_sectors.extend(difat_entries[:-1])
        difat_sector = difat_entries[-1]
    return [sector for sector in fat_sectors if sector <= _MAX_REGULAR_SECTOR][
        :fat_sector_count
    ]


def _get_chain_sectors(
    fat: tuple[int, ...], first_sector: int, sector_limit: int
) -> list[int]:
    chain = []
    sector = first_sector
    while sector <= _MAX_REGULAR_SECTOR:
        chain.append(sector)
        if len(chain) > sector_limit:
            raise HansardMinutesFileError("The Word file holds a sector chain loop")
        sector = fat[sector]
    return chain


def _read_chain(
    content: bytes, fat: tuple[int, ...], first_sector: int, sector_size: int
) -> bytes:
    chain = _get_chain_sectors(fat, first_sector, len(fat))
    return b"".join(_read_sector(content, sector_size, sector) for sector in chain)


def _read_directory(directory_bytes: bytes) -> dict[str, _DirectoryEntry]:
    directory = {}
    for entry_start in range(0, len(directory_bytes), _DIRECTORY_ENTRY_SIZE):
        name_length = _read_uint16(
            directory_bytes, entry_start + _DIRECTORY_NAME_LENGTH_OFFSET
        )
        name = _read_exact(directory_bytes, entry_start, name_length).decode(
            _SIXTEEN_BIT_ENCODING
        )
        directory[name.rstrip("\x00")] = _DirectoryEntry(
            start_sector=_read_uint32(
                directory_bytes, entry_start + _DIRECTORY_START_SECTOR_OFFSET
            ),
            size=_read_uint32(directory_bytes, entry_start + _DIRECTORY_SIZE_OFFSET),
        )
    return directory


def _open_container(content: bytes) -> _Ole2Container:
    sector_size = 1 << _read_uint16(content, _HEADER_SECTOR_SHIFT_OFFSET)
    fat_bytes = b"".join(
        _read_sector(content, sector_size, sector)
        for sector in _get_fat_sectors(content, sector_size)
    )
    fat = struct.unpack(f"<{len(fat_bytes) // 4}I", fat_bytes)
    first_mini_fat_sector = _read_uint32(content, _HEADER_FIRST_MINI_FAT_SECTOR_OFFSET)
    mini_fat_bytes = _read_chain(content, fat, first_mini_fat_sector, sector_size)
    return _Ole2Container(
        content=content,
        sector_size=sector_size,
        mini_sector_size=1 << _read_uint16(content, _HEADER_MINI_SECTOR_SHIFT_OFFSET),
        mini_stream_cutoff=_read_uint32(content, _HEADER_MINI_STREAM_CUTOFF_OFFSET),
        fat=fat,
        mini_fat=struct.unpack(f"<{len(mini_fat_bytes) // 4}I", mini_fat_bytes),
        directory=_read_directory(
            _read_chain(
                content,
                fat,
                _read_uint32(content, _HEADER_FIRST_DIRECTORY_SECTOR_OFFSET),
                sector_size,
            )
        ),
    )


def _read_stream(container: _Ole2Container, name: str) -> bytes:
    entry = container.directory[name]
    if entry.size >= container.mini_stream_cutoff:
        stream = _read_chain(
            container.content, container.fat, entry.start_sector, container.sector_size
        )
        return _read_exact(stream, 0, entry.size)
    root_entry = container.directory[_ROOT_ENTRY_NAME]
    mini_stream = _read_chain(
        container.content, container.fat, root_entry.start_sector, container.sector_size
    )
    chain = _get_chain_sectors(
        container.mini_fat, entry.start_sector, len(container.mini_fat)
    )
    stream = b"".join(
        _read_exact(
            mini_stream, sector * container.mini_sector_size, container.mini_sector_size
        )
        for sector in chain
    )
    return _read_exact(stream, 0, entry.size)


def _get_piece_table(clx: bytes) -> bytes:
    position = 0
    while clx[position] == _CLX_PRC_MARKER:
        position += 3 + _read_uint16(clx, position + 1)
    if clx[position] != _CLX_PCDT_MARKER:
        raise HansardMinutesFileError("The Word file holds no piece table")
    piece_table_length = _read_uint32(clx, position + 1)
    return _read_exact(clx, position + 5, piece_table_length)


def _decode_pieces(word_document: bytes, piece_table: bytes) -> str:
    piece_count = (len(piece_table) - _PIECE_POSITION_SIZE) // _PIECE_ENTRY_SIZE
    positions = struct.unpack_from(f"<{piece_count + 1}I", piece_table)
    descriptors_start = _PIECE_POSITION_SIZE * (piece_count + 1)
    pieces = []
    for index in range(piece_count):
        character_offset = _read_uint32(
            piece_table, descriptors_start + index * _PIECE_DESCRIPTOR_SIZE + 2
        )
        character_count = positions[index + 1] - positions[index]
        if character_offset & _PIECE_IS_EIGHT_BIT_FLAG:
            start = (character_offset & _PIECE_OFFSET_MASK) // 2
            pieces.append(
                _read_exact(word_document, start, character_count).decode(
                    _EIGHT_BIT_ENCODING
                )
            )
            continue
        pieces.append(
            _read_exact(word_document, character_offset, character_count * 2).decode(
                _SIXTEEN_BIT_ENCODING
            )
        )
    return "".join(pieces)


def _read_word_text(content: bytes) -> str:
    container = _open_container(content)
    word_document = _read_stream(container, _WORD_DOCUMENT_STREAM_NAME)
    flags = _read_uint16(word_document, _FIB_FLAGS_OFFSET)
    if flags & _FIB_IS_ENCRYPTED_FLAG:
        raise HansardMinutesFileError("The Word file is encrypted")
    table_name = (
        _ONE_TABLE_STREAM_NAME
        if flags & _FIB_IS_ONE_TABLE_FLAG
        else _ZERO_TABLE_STREAM_NAME
    )
    table = _read_stream(container, table_name)
    clx_start = _read_uint32(word_document, _FIB_CLX_OFFSET)
    clx_length = _read_uint32(word_document, _FIB_CLX_LENGTH_OFFSET)
    piece_table = _get_piece_table(_read_exact(table, clx_start, clx_length))
    character_count = struct.unpack_from("<i", word_document, _FIB_CHARACTER_COUNT_OFFSET)[
        0
    ]
    text = _decode_pieces(word_document, piece_table)[:character_count]
    # NOTE: only the paragraph mark becomes a newline; tabs carry the column layout of the lists
    return text.replace(_WORD_PARAGRAPH_MARK, "\n")


def get_minutes_word_text(content: bytes) -> str:
    try:
        return _read_word_text(content)
    except struct.error as error:
        raise HansardMinutesFileError("The Word file cannot be read") from error
    except IndexError as error:
        raise HansardMinutesFileError("The Word file cannot be read") from error
    except UnicodeDecodeError as error:
        raise HansardMinutesFileError("The Word file cannot be read") from error
    except KeyError as error:
        raise HansardMinutesFileError("The Word file cannot be read") from error


def get_minutes_head_dates(extracted_text: str) -> list[date]:
    head_dates: set[date] = set()
    for match in _HEAD_DATE_PATTERN.finditer(extracted_text[:_HEAD_CHARACTER_COUNT]):
        try:
            head_dates.add(
                datetime.strptime(" ".join(match.groups()), _HEAD_DATE_FORMAT).date()
            )
        except ValueError:
            continue
    return sorted(head_dates)


def is_minutes_head(extracted_text: str) -> bool:
    return (
        _HEAD_TITLE_PATTERN.search(extracted_text[:_HEAD_CHARACTER_COUNT]) is not None
    )


def get_minutes_text_outcome(
    sitting_date: date, extracted_text: str
) -> MinutesTextOutcome:
    head_dates = get_minutes_head_dates(extracted_text)
    if not head_dates or sitting_date in head_dates:
        return MinutesTextOutcome(MinutesStatus.TEXT_STORED, None)
    dates_text = ", ".join(
        f"{head_date.day} {head_date:%B} {head_date.year}" for head_date in head_dates
    )
    return MinutesTextOutcome(
        MinutesStatus.NEEDS_REVIEW,
        f"The file's head prints {dates_text}, not the sitting date",
    )

import argparse
import hashlib
import random
import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import TypeAdapter
from sqlmodel import Session

from crud.division import CRUDDivision
from crud.division_vote import CRUDDivisionVote, DivisionVoteLinkRow
from crud.minutes import CRUDMinutes
from crud.minutes_division import CRUDMinutesDivision
from crud.minutes_index_capture import CRUDMinutesIndexCapture
from crud.party_affiliation import CRUDPartyAffiliation
from crud.report import CRUDReport, ReportTypeRow
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechParseRow
from database.division import Division
from database.init import build_read_only_engine
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from enums import (
    DivisionCheckPlantKind,
    DivisionCheckRule,
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    DivisionVoteNameRule,
    MinutesDivisionPairing,
    MinutesIndexSource,
    MinutesStatus,
)
from exceptions import HansardDivisionCheckError
from logs import logger
from populate.minutes_divisions import get_pairable_hansard_divisions
from schemas.division_check_sample import (
    DivisionCheckCandidate,
    DivisionCheckKey,
    DivisionCheckPacket,
    DivisionCheckPlant,
)
from services.division import get_report_divisions
from services.division_pairing import PairableHansardDivision
from services.minutes_index import (
    MinutesIndexRow,
    parse_archive_index_page,
    parse_live_index_page,
)
from settings import settings
from utils.database_label import get_database_label
from utils.sitting_dates import get_decade_label

_ROWS_PER_GROUP = 50
_PLANT_COUNT_PER_KIND = 5
_REPORT_BATCH = 200
_SOURCE_TEXT_LIMIT = 400
_PACKET_ID_BITS = 64
_READ_ISOLATION_LEVEL = "REPEATABLE READ"
_MAX_BATCH_PACKETS = 100
_MAX_BATCH_CHARACTERS = 160_000
_BATCHES_DIRECTORY_NAME = "batches"
_PACKETS_FILE_NAME = "packets.json"
_KEY_FILE_NAME = "key.json"
_KEY_HASH_FILE_NAME = "key.sha256"
_SUMMARY_FILE_NAME = "draw-summary.txt"
_LINE_SEPARATOR = "\n"
_GROUP_SEPARATOR = "|"
_CLAIM_CHOICE_SEPARATOR = ": "
_NO_FILE_FORMAT = "NO_FILE"
_ERA_PRE = "pre"
_ERA_TABLE = "table"
_ERA_PARAGRAPH = "paragraph"
_SIDE_WITHOUT_PRINTED_COUNT_GROUP = "side without a printed count"
_PRINTED_COUNT_LINE_PREFIX = "Printed count line: "
_ERA_OPENING_PATTERN = re.compile(
    r"the\s+(?:house|committee)\s+divided|division\s+taken|question\s+put\W*\s*ayes",
    re.IGNORECASE,
)
_ERA_BLOCK_PATTERN = re.compile(r"<pre|<table", re.IGNORECASE)
_DIGIT_PATTERN = re.compile(r"\d")
_CLAIMED_HANSARD_DIVISION_PATTERN = re.compile(r"Hansard division (\d+)")
_SOURCE_HANSARD_DIVISION_PATTERN = re.compile(r"^\d+\. ", re.MULTILINE)
_CLAIMED_PARLIAMENT_PATTERN = re.compile(r"^(.*) \| Parliament (\d+)$")
_CLAIMED_SITTING_DATE_PATTERN = re.compile(r"sitting date (\d{4}-\d{2}-\d{2})")
_CLAIMED_PARTY_PATTERN = re.compile(r"^party (.*), uncertain (?:True|False)$")
_SOURCE_SPANS_MARKER = "; spans: "
_SOURCE_SPAN_SEPARATOR = "; "
_SOURCE_SPAN_PARTY_PATTERN = re.compile(r"^(.*) from \d{4}-\d{2}-\d{2} \(")
_NO_PAIRED_DIVISION_CLAIM = "no Hansard division paired"
_THIS_DIVISION_MARK = " (this one)"
_DIGIT_BASE = 10


@dataclass(frozen=True)
class PlantedCandidate:
    candidate: DivisionCheckCandidate
    kind: DivisionCheckPlantKind
    planted_claim: str


@dataclass(frozen=True)
class DivisionCheckPacketsAndKey:
    packets: list[DivisionCheckPacket]
    key: DivisionCheckKey


@dataclass(frozen=True)
class _PacketDraft:
    source_text: str
    data_claim: str
    database_key: str
    plant_kind: Optional[DivisionCheckPlantKind]


@dataclass
class _ReaderBatch:
    packets: list[DivisionCheckPacket]
    character_count: int
    database_keys: set[str]


def _get_group(sitting_date: date, group_label: str) -> str:
    return f"{get_decade_label(sitting_date)}{_GROUP_SEPARATOR}{group_label}"


def _format_counts(division: Division) -> str:
    return f"Ayes {division.ayes}, Noes {division.noes}, Abstentions {division.abstentions}, Absent {division.absent}, Paired {division.paired}"


def _get_report_type_rows(
    session: Session, divisions: list[Division]
) -> dict[str, ReportTypeRow]:
    sprs_report_ids = sorted(
        {
            division.sprs_report_id
            for division in divisions
            if division.sprs_report_id is not None
        }
    )
    return {
        type_row.report_id: type_row
        for start in range(0, len(sprs_report_ids), _REPORT_BATCH)
        for type_row in CRUDReport(session).get_type_rows_by_report_ids(
            sprs_report_ids[start : start + _REPORT_BATCH]
        )
    }


def _get_report_parse_rows(
    session: Session, report_ids: list[int]
) -> Iterator[dict[int, list[SpeechParseRow]]]:
    for start in range(0, len(report_ids), _REPORT_BATCH):
        report_id_to_parse_rows: defaultdict[int, list[SpeechParseRow]] = defaultdict(
            list
        )
        for parse_row in CRUDSpeech(session).get_parse_rows_by_report_ids(
            report_ids[start : start + _REPORT_BATCH]
        ):
            report_id_to_parse_rows[parse_row.report_id].append(parse_row)
        yield report_id_to_parse_rows


def _get_transcript(parse_rows: list[SpeechParseRow], ordinal: int) -> str:
    for parse_row in parse_rows:
        if parse_row.ordinal == ordinal:
            return parse_row.transcript
    raise HansardDivisionCheckError(f"No speech row has the ordinal {ordinal}")


def _get_count_source_candidates(
    session: Session, rule: DivisionCheckRule, count_source: DivisionCountSource
) -> list[DivisionCheckCandidate]:
    divisions = CRUDDivision(session).get_by_count_source(count_source)
    sprs_report_id_to_type_row = _get_report_type_rows(session, divisions)
    report_ids = sorted(type_row.id for type_row in sprs_report_id_to_type_row.values())
    candidates: list[DivisionCheckCandidate] = []
    for report_id_to_parse_rows in _get_report_parse_rows(session, report_ids):
        for division in divisions:
            if division.sprs_report_id is None:
                raise HansardDivisionCheckError(
                    f"Division {division.id} holds no report"
                )
            if division.speech_ordinal is None:
                raise HansardDivisionCheckError(
                    f"Division {division.id} holds no speech row"
                )
            type_row = sprs_report_id_to_type_row[division.sprs_report_id]
            report_parse_rows = report_id_to_parse_rows.get(type_row.id)
            if report_parse_rows is None:
                continue
            candidates.append(
                DivisionCheckCandidate(
                    rule=rule,
                    group=_get_group(division.sitting_date, type_row.report_type),
                    source_text=_get_transcript(
                        report_parse_rows, division.speech_ordinal
                    ),
                    data_claim=_format_counts(division),
                    database_key=f"division:{division.id}",
                )
            )
    return candidates


def _get_merge_candidates(session: Session) -> list[DivisionCheckCandidate]:
    divisions = CRUDDivision(session).get_by_count_source(
        DivisionCountSource.PRINTED_LINE
    )
    sprs_report_id_and_number_to_division = {
        (division.sprs_report_id, division.report_division_number): division
        for division in divisions
    }
    sprs_report_id_to_type_row = _get_report_type_rows(session, divisions)
    report_id_to_type_row = {
        type_row.id: type_row for type_row in sprs_report_id_to_type_row.values()
    }
    candidates: list[DivisionCheckCandidate] = []
    for report_id_to_parse_rows in _get_report_parse_rows(
        session, sorted(report_id_to_type_row)
    ):
        for report_id, parse_rows in report_id_to_parse_rows.items():
            type_row = report_id_to_type_row[report_id]
            for parsed_division in get_report_divisions(parse_rows).divisions:
                if parsed_division.merged_total_ordinal is None:
                    continue
                division = sprs_report_id_and_number_to_division.get(
                    (type_row.report_id, parsed_division.report_division_number)
                )
                if division is None:
                    continue
                if division.speech_ordinal is None:
                    raise HansardDivisionCheckError(
                        f"Division {division.id} holds no speech row"
                    )
                candidates.append(
                    DivisionCheckCandidate(
                        rule=DivisionCheckRule.PRINTED_AND_SPOKEN_MERGE,
                        group=_get_group(division.sitting_date, type_row.report_type),
                        source_text=_LINE_SEPARATOR.join(
                            [
                                _get_transcript(parse_rows, division.speech_ordinal),
                                _get_transcript(
                                    parse_rows, parsed_division.merged_total_ordinal
                                ),
                            ]
                        ),
                        data_claim=_format_counts(division),
                        database_key=f"division:{division.id}",
                    )
                )
    return candidates


def _get_file_format_label(minutes: Minutes) -> str:
    if minutes.file_format is None:
        return _NO_FILE_FORMAT
    return minutes.file_format


def _get_index_capture_id(minutes: Minutes) -> int:
    if minutes.index_capture_id is None:
        raise HansardDivisionCheckError(
            f"Minutes {minutes.id} names an index source and no index capture"
        )
    return minutes.index_capture_id


def _get_capture_index_rows(content: str, is_live_page: bool) -> list[MinutesIndexRow]:
    if is_live_page:
        return parse_live_index_page(content, settings.minutes_media_url)
    return parse_archive_index_page(content, settings.minutes_index_url)


def _get_printed_index_row(
    minutes: Minutes, capture_index_rows: list[MinutesIndexRow]
) -> MinutesIndexRow:
    printed_index_rows = {
        index_row
        for index_row in capture_index_rows
        if index_row.file_url == minutes.file_url
    }
    if len(printed_index_rows) != 1:
        raise HansardDivisionCheckError(
            f"Minutes {minutes.id} matches {len(printed_index_rows)} rows of its index capture"
        )
    return next(iter(printed_index_rows))


def _get_index_row_candidates(
    session: Session, stored_minutes: list[Minutes]
) -> list[DivisionCheckCandidate]:
    indexed_minutes = [
        minutes
        for minutes in stored_minutes
        if minutes.index_source == MinutesIndexSource.LIVE_PAGE
        or minutes.index_source == MinutesIndexSource.ARCHIVE_INDEX_CAPTURE
    ]
    capture_id_to_is_live_page = {
        _get_index_capture_id(minutes): minutes.index_source
        == MinutesIndexSource.LIVE_PAGE
        for minutes in indexed_minutes
    }
    capture_ids = sorted(capture_id_to_is_live_page)
    capture_id_to_index_rows = {
        content_row.id: _get_capture_index_rows(
            content_row.content, capture_id_to_is_live_page[content_row.id]
        )
        for start in range(0, len(capture_ids), _REPORT_BATCH)
        for content_row in CRUDMinutesIndexCapture(session).get_content_rows_by_ids(
            capture_ids[start : start + _REPORT_BATCH]
        )
    }
    candidates: list[DivisionCheckCandidate] = []
    for minutes in indexed_minutes:
        printed_index_row = _get_printed_index_row(
            minutes, capture_id_to_index_rows[_get_index_capture_id(minutes)]
        )
        candidates.append(
            DivisionCheckCandidate(
                rule=DivisionCheckRule.INDEX_ROW,
                group=_get_group(
                    minutes.sitting_date,
                    f"{minutes.index_source}{_GROUP_SEPARATOR}{_get_file_format_label(minutes)}",
                ),
                source_text=f"{printed_index_row.printed_text}; links to {printed_index_row.file_url}",
                data_claim=f"sitting date {minutes.sitting_date}; label {minutes.printed_label}; address {minutes.file_url}",
                database_key=f"minutes:{minutes.id}",
            )
        )
    return candidates


def _get_file_head_date_candidates(
    stored_minutes: list[Minutes],
) -> list[DivisionCheckCandidate]:
    return [
        DivisionCheckCandidate(
            rule=DivisionCheckRule.FILE_HEAD_DATE,
            group=_get_group(minutes.sitting_date, _get_file_format_label(minutes)),
            source_text=minutes.extracted_text[:_SOURCE_TEXT_LIMIT],
            data_claim=f"sitting date {minutes.sitting_date}",
            database_key=f"minutes:{minutes.id}",
        )
        for minutes in stored_minutes
        if minutes.index_source == MinutesIndexSource.ARCHIVE_FILE_LISTING
        and minutes.extracted_text is not None
    ]


def _get_minutes_side_candidates(
    session: Session, stored_minutes: list[Minutes]
) -> list[DivisionCheckCandidate]:
    minutes_id_to_minutes = {minutes.id: minutes for minutes in stored_minutes}
    minutes_divisions = [
        minutes_division
        for minutes_division in CRUDMinutesDivision(session).get_all()
        if minutes_division.list_status == DivisionListStatus.STORED
    ]
    division_id_to_vote_lines: defaultdict[int, list[str]] = defaultdict(list)
    for vote_row in CRUDDivisionVote(session).get_rows_by_division_ids_and_list_source(
        [minutes_division.division_id for minutes_division in minutes_divisions],
        DivisionVoteListSource.MINUTES,
    ):
        division_id_to_vote_lines[vote_row.division_id].append(
            f"{vote_row.vote_choice}{_CLAIM_CHOICE_SEPARATOR}{vote_row.printed_name}"
        )
    return [
        DivisionCheckCandidate(
            rule=DivisionCheckRule.MINUTES_DIVISION_AND_SIDE,
            group=_get_group(
                minutes_id_to_minutes[minutes_division.minutes_id].sitting_date,
                _get_file_format_label(
                    minutes_id_to_minutes[minutes_division.minutes_id]
                ),
            ),
            source_text=minutes_division.printed_list or "",
            data_claim=_LINE_SEPARATOR.join(
                division_id_to_vote_lines[minutes_division.division_id]
            ),
            database_key=f"minutes_division:{minutes_division.id}",
        )
        for minutes_division in minutes_divisions
    ]


def _get_pairing_claim(
    pairing: MinutesDivisionPairing,
    division_id: int,
    hansard_division_ids: list[int],
) -> str:
    if division_id in hansard_division_ids:
        return f"pairing {pairing}, Hansard division {hansard_division_ids.index(division_id) + 1}"
    return f"pairing {pairing}, {_NO_PAIRED_DIVISION_CLAIM}"


def _get_pairing_candidates(
    session: Session, stored_minutes: list[Minutes]
) -> list[DivisionCheckCandidate]:
    minutes_id_to_minutes = {minutes.id: minutes for minutes in stored_minutes}
    minutes_divisions = CRUDMinutesDivision(session).get_all()
    sitting_dates = sorted(
        {
            minutes_id_to_minutes[minutes_division.minutes_id].sitting_date
            for minutes_division in minutes_divisions
        }
    )
    pairable_hansard_divisions = sorted(
        get_pairable_hansard_divisions(session, sitting_dates),
        key=lambda hansard_division: (
            hansard_division.sitting_date,
            hansard_division.speech_number,
            hansard_division.speech_ordinal,
        ),
    )
    division_id_to_printed_counts = {
        division.id: division.printed_counts
        for division in CRUDDivision(
            session
        ).get_by_sitting_dates_and_sprs_report_id_not_null(sitting_dates)
    }
    sprs_report_id_to_title = {
        title_row.report_id: title_row.title
        for title_row in CRUDReport(session).get_title_rows_by_report_ids(
            sorted(
                {
                    hansard_division.sprs_report_id
                    for hansard_division in pairable_hansard_divisions
                }
            )
        )
    }
    sitting_date_to_hansard_divisions: defaultdict[
        date, list[PairableHansardDivision]
    ] = defaultdict(list)
    for hansard_division in pairable_hansard_divisions:
        sitting_date_to_hansard_divisions[hansard_division.sitting_date].append(
            hansard_division
        )
    sitting_date_to_minutes_divisions: defaultdict[date, list[MinutesDivision]] = (
        defaultdict(list)
    )
    for minutes_division in sorted(
        minutes_divisions, key=lambda minutes_division: minutes_division.ordinal
    ):
        sitting_date_to_minutes_divisions[
            minutes_id_to_minutes[minutes_division.minutes_id].sitting_date
        ].append(minutes_division)
    candidates: list[DivisionCheckCandidate] = []
    for minutes_division in minutes_divisions:
        minutes = minutes_id_to_minutes[minutes_division.minutes_id]
        hansard_divisions = sitting_date_to_hansard_divisions[minutes.sitting_date]
        candidates.append(
            DivisionCheckCandidate(
                rule=DivisionCheckRule.PAIRING,
                group=_get_group(minutes.sitting_date, _get_file_format_label(minutes)),
                source_text=_LINE_SEPARATOR.join(
                    [
                        f"Minutes of {minutes.sitting_date}, divisions in order:",
                        *[
                            f"Minutes division {date_minutes_division.ordinal}{_THIS_DIVISION_MARK if date_minutes_division.ordinal == minutes_division.ordinal else ''}: {date_minutes_division.printed_counts}"
                            for date_minutes_division in sitting_date_to_minutes_divisions[
                                minutes.sitting_date
                            ]
                        ],
                        "Hansard divisions of the date, in order of report speech number and row:",
                        *[
                            f"{number}. {division_id_to_printed_counts[hansard_division.division_id]} ({sprs_report_id_to_title[hansard_division.sprs_report_id]}, speech {hansard_division.speech_number}, row {hansard_division.speech_ordinal})"
                            for number, hansard_division in enumerate(
                                hansard_divisions, 1
                            )
                        ],
                    ]
                ),
                data_claim=_get_pairing_claim(
                    minutes_division.pairing,
                    minutes_division.division_id,
                    [
                        hansard_division.division_id
                        for hansard_division in hansard_divisions
                    ],
                ),
                database_key=f"minutes_division:{minutes_division.id}",
            )
        )
    return candidates


def _get_layout_era(content: Optional[str]) -> str:
    if content is None:
        return _ERA_PARAGRAPH
    opening_match = _ERA_OPENING_PATTERN.search(content)
    if opening_match is None:
        return _ERA_PARAGRAPH
    block_match = _ERA_BLOCK_PATTERN.search(content, opening_match.end())
    if block_match is None:
        return _ERA_PARAGRAPH
    if block_match.group(0).lower() == "<pre":
        return _ERA_PRE
    return _ERA_TABLE


def _has_names_under_side_without_printed_count(
    division: Division, vote_choices: set[DivisionVoteChoice]
) -> bool:
    if division.list_status != DivisionListStatus.STORED:
        return False
    return (division.absent is None and DivisionVoteChoice.ABSENT in vote_choices) or (
        division.paired is None and DivisionVoteChoice.PAIRED in vote_choices
    )


def _get_layout_era_candidates(session: Session) -> list[DivisionCheckCandidate]:
    divisions = CRUDDivision(session).get_by_list_statuses(
        [
            DivisionListStatus.STORED,
            DivisionListStatus.COUNTS_DISAGREE,
            DivisionListStatus.LAYOUT_UNREADABLE,
        ]
    )
    sprs_report_id_to_type_row = _get_report_type_rows(session, divisions)
    report_id_to_content = {
        content_row.id: content_row.content
        for start in range(0, len(sprs_report_id_to_type_row), _REPORT_BATCH)
        for content_row in CRUDReport(session).get_content_rows_by_ids(
            sorted(type_row.id for type_row in sprs_report_id_to_type_row.values())[
                start : start + _REPORT_BATCH
            ]
        )
    }
    division_id_to_vote_lines: defaultdict[int, list[str]] = defaultdict(list)
    division_id_to_vote_choices: defaultdict[int, set[DivisionVoteChoice]] = (
        defaultdict(set)
    )
    for vote_row in CRUDDivisionVote(session).get_rows_by_division_ids_and_list_source(
        [division.id for division in divisions if division.id is not None],
        DivisionVoteListSource.HANSARD,
    ):
        division_id_to_vote_lines[vote_row.division_id].append(
            f"{vote_row.vote_choice}{_CLAIM_CHOICE_SEPARATOR}{vote_row.printed_name}"
        )
        division_id_to_vote_choices[vote_row.division_id].add(vote_row.vote_choice)
    return [
        DivisionCheckCandidate(
            rule=DivisionCheckRule.HANSARD_LIST_BY_LAYOUT_ERA,
            group=_get_group(
                division.sitting_date,
                _SIDE_WITHOUT_PRINTED_COUNT_GROUP
                if _has_names_under_side_without_printed_count(
                    division, division_id_to_vote_choices[division.id]
                )
                else _get_layout_era(
                    report_id_to_content[
                        sprs_report_id_to_type_row[division.sprs_report_id].id
                    ]
                ),
            ),
            source_text=_LINE_SEPARATOR.join(
                [
                    f"{_PRINTED_COUNT_LINE_PREFIX}{division.printed_counts}",
                    division.printed_list or "",
                ]
            ),
            data_claim=_LINE_SEPARATOR.join(
                [
                    f"list status {division.list_status}",
                    *division_id_to_vote_lines[division.id],
                ]
            ),
            database_key=f"division:{division.id}",
        )
        for division in divisions
        if division.id is not None and division.sprs_report_id is not None
    ]


def _get_name_rule(rule: DivisionCheckRule) -> Optional[DivisionVoteNameRule]:
    if rule == DivisionCheckRule.NAME_TIER_EXACT:
        return DivisionVoteNameRule.EXACT
    if rule == DivisionCheckRule.NAME_TIER_INVERTED:
        return DivisionVoteNameRule.INVERTED
    if rule == DivisionCheckRule.NAME_TIER_BIN_FREE:
        return DivisionVoteNameRule.BIN_FREE
    if rule == DivisionCheckRule.NAME_TIER_SAME_WORDS:
        return DivisionVoteNameRule.SAME_WORDS
    if rule == DivisionCheckRule.NAME_TIER_HAND_LIST:
        return DivisionVoteNameRule.HAND_LIST
    return None


def _get_vote_key(vote_row: DivisionVoteLinkRow) -> str:
    return f"division_vote:{vote_row.division_id}:{vote_row.list_source}:{vote_row.ordinal}"


def _get_name_tier_candidates(
    session: Session, rule: DivisionCheckRule, name_rule: DivisionVoteNameRule
) -> list[DivisionCheckCandidate]:
    speaker_id_to_speaker = {
        speaker.id: speaker for speaker in CRUDSpeaker(session).get_all()
    }
    return [
        DivisionCheckCandidate(
            rule=rule,
            group=_get_group(vote_row.sitting_date, vote_row.list_source),
            source_text=vote_row.printed_name,
            data_claim=f"{speaker_id_to_speaker[vote_row.speaker_id].name} | Parliament {speaker_id_to_speaker[vote_row.speaker_id].parliament_number}",
            database_key=_get_vote_key(vote_row),
        )
        for vote_row in CRUDDivisionVote(
            session
        ).get_link_rows_by_name_rule_and_speaker_id_not_null(name_rule)
    ]


def _get_party_on_date_candidates(session: Session) -> list[DivisionCheckCandidate]:
    speaker_id_to_speaker = {
        speaker.id: speaker for speaker in CRUDSpeaker(session).get_all()
    }
    vote_rows = CRUDDivisionVote(
        session
    ).get_link_rows_by_speaker_id_not_null_and_party_not_null()
    speaker_id_to_span_texts: defaultdict[int, list[str]] = defaultdict(list)
    for span in sorted(
        CRUDPartyAffiliation(session).get_by_speaker_ids(
            sorted({vote_row.speaker_id for vote_row in vote_rows})
        ),
        key=lambda span: span.started_on,
    ):
        speaker_id_to_span_texts[span.speaker_id].append(
            f"{span.party} from {span.started_on} ({span.started_on_precision}, upper bound {span.is_started_on_upper_bound})"
        )
    return [
        DivisionCheckCandidate(
            rule=DivisionCheckRule.PARTY_ON_DATE,
            group=_get_group(vote_row.sitting_date, vote_row.list_source),
            source_text=f"{speaker_id_to_speaker[vote_row.speaker_id].name} on {vote_row.sitting_date}; ballot party {speaker_id_to_speaker[vote_row.speaker_id].party}; spans: {'; '.join(speaker_id_to_span_texts[vote_row.speaker_id]) or 'none'}",
            data_claim=f"party {vote_row.party}, uncertain {vote_row.is_party_uncertain}",
            database_key=_get_vote_key(vote_row),
        )
        for vote_row in vote_rows
    ]


def get_division_check_candidates(
    session: Session, rule: DivisionCheckRule
) -> list[DivisionCheckCandidate]:
    if rule == DivisionCheckRule.PRINTED_LINE:
        return _get_count_source_candidates(
            session, rule, DivisionCountSource.PRINTED_LINE
        )
    if rule == DivisionCheckRule.SPOKEN_TOTAL:
        return _get_count_source_candidates(
            session, rule, DivisionCountSource.SPOKEN_TOTAL
        )
    if rule == DivisionCheckRule.PRINTED_AND_SPOKEN_MERGE:
        return _get_merge_candidates(session)
    if rule == DivisionCheckRule.HANSARD_LIST_BY_LAYOUT_ERA:
        return _get_layout_era_candidates(session)
    if rule == DivisionCheckRule.PARTY_ON_DATE:
        return _get_party_on_date_candidates(session)
    name_rule = _get_name_rule(rule)
    if name_rule is not None:
        return _get_name_tier_candidates(session, rule, name_rule)
    stored_minutes = CRUDMinutes(session).get_by_statuses(list(MinutesStatus))
    if rule == DivisionCheckRule.INDEX_ROW:
        return _get_index_row_candidates(session, stored_minutes)
    if rule == DivisionCheckRule.FILE_HEAD_DATE:
        return _get_file_head_date_candidates(stored_minutes)
    if rule == DivisionCheckRule.MINUTES_DIVISION_AND_SIDE:
        return _get_minutes_side_candidates(session, stored_minutes)
    if rule == DivisionCheckRule.PAIRING:
        return _get_pairing_candidates(session, stored_minutes)
    raise HansardDivisionCheckError(f"No frame is built for {rule}")


def draw_candidates(
    candidates: list[DivisionCheckCandidate], seed: int
) -> list[DivisionCheckCandidate]:
    group_to_candidates: defaultdict[str, list[DivisionCheckCandidate]] = defaultdict(
        list
    )
    for candidate in sorted(candidates, key=lambda candidate: candidate.database_key):
        group_to_candidates[candidate.group].append(candidate)
    drawn_candidates: list[DivisionCheckCandidate] = []
    for group in sorted(group_to_candidates):
        group_candidates = group_to_candidates[group]
        drawn_candidates.extend(
            random.Random(f"{seed}{_GROUP_SEPARATOR}{group}").sample(
                group_candidates, min(len(group_candidates), _ROWS_PER_GROUP)
            )
        )
    return drawn_candidates


def get_plant_kinds(rule: DivisionCheckRule) -> tuple[DivisionCheckPlantKind, ...]:
    if (
        rule == DivisionCheckRule.PRINTED_LINE
        or rule == DivisionCheckRule.SPOKEN_TOTAL
        or rule == DivisionCheckRule.PRINTED_AND_SPOKEN_MERGE
    ):
        return (DivisionCheckPlantKind.WRONG_COUNT_DIGIT,)
    if rule == DivisionCheckRule.INDEX_ROW or rule == DivisionCheckRule.FILE_HEAD_DATE:
        return (DivisionCheckPlantKind.WRONG_DATE,)
    if (
        rule == DivisionCheckRule.MINUTES_DIVISION_AND_SIDE
        or rule == DivisionCheckRule.HANSARD_LIST_BY_LAYOUT_ERA
    ):
        return (DivisionCheckPlantKind.SWAPPED_SIDE,)
    if rule == DivisionCheckRule.PAIRING:
        return (DivisionCheckPlantKind.WRONG_PAIR,)
    if rule == DivisionCheckRule.PARTY_ON_DATE:
        return (DivisionCheckPlantKind.WRONG_PARTY,)
    if _get_name_rule(rule) is not None:
        return (DivisionCheckPlantKind.WRONG_PERSON,)
    raise HansardDivisionCheckError(f"No plant kind is set for {rule}")


def get_sibling_rules(rule: DivisionCheckRule) -> tuple[DivisionCheckRule, ...]:
    if rule == DivisionCheckRule.PRINTED_LINE:
        return (DivisionCheckRule.SPOKEN_TOTAL,)
    if rule == DivisionCheckRule.SPOKEN_TOTAL:
        return (DivisionCheckRule.PRINTED_LINE,)
    if _get_name_rule(rule) is None:
        return ()
    return tuple(
        other_rule
        for other_rule in DivisionCheckRule
        if other_rule != rule and _get_name_rule(other_rule) is not None
    )


def get_sibling_candidates(
    session: Session, rule: DivisionCheckRule
) -> list[DivisionCheckCandidate]:
    return [
        candidate
        for sibling_rule in get_sibling_rules(rule)
        for candidate in get_division_check_candidates(session, sibling_rule)
    ]


def _swap_sides(data_claim: str) -> Optional[str]:
    claim_lines = data_claim.split(_LINE_SEPARATOR)
    choice_and_name_lines = [
        claim_line.split(_CLAIM_CHOICE_SEPARATOR, 1)
        for claim_line in claim_lines
        if _CLAIM_CHOICE_SEPARATOR in claim_line
    ]
    first_line = choice_and_name_lines[0] if choice_and_name_lines else None
    if first_line is None:
        return None
    for second_line in choice_and_name_lines:
        if second_line[0] == first_line[0]:
            continue
        swapped_lines = [
            _CLAIM_CHOICE_SEPARATOR.join([first_line[0], second_line[1]])
            if claim_line == _CLAIM_CHOICE_SEPARATOR.join(first_line)
            else _CLAIM_CHOICE_SEPARATOR.join([second_line[0], first_line[1]])
            if claim_line == _CLAIM_CHOICE_SEPARATOR.join(second_line)
            else claim_line
            for claim_line in claim_lines
        ]
        return _LINE_SEPARATOR.join(swapped_lines)
    return None


def _change_count_digit(data_claim: str) -> Optional[str]:
    digit_match = _DIGIT_PATTERN.search(data_claim)
    if digit_match is None:
        return None
    changed_digit = (int(digit_match.group(0)) + 1) % _DIGIT_BASE
    return (
        data_claim[: digit_match.start()]
        + str(changed_digit)
        + data_claim[digit_match.end() :]
    )


def _replace_person(
    candidate: DivisionCheckCandidate, candidates: list[DivisionCheckCandidate]
) -> Optional[str]:
    claim_match = _CLAIMED_PARLIAMENT_PATTERN.match(candidate.data_claim)
    if claim_match is None:
        return None
    other_claims = sorted(
        {
            other_candidate.data_claim
            for other_candidate in candidates
            if other_candidate.data_claim.endswith(
                f" | Parliament {claim_match.group(2)}"
            )
            and other_candidate.data_claim != candidate.data_claim
        }
    )
    if not other_claims:
        return None
    return random.Random(candidate.database_key).choice(other_claims)


def _replace_pair(candidate: DivisionCheckCandidate) -> Optional[str]:
    hansard_division_count = len(
        _SOURCE_HANSARD_DIVISION_PATTERN.findall(candidate.source_text)
    )
    claim_match = _CLAIMED_HANSARD_DIVISION_PATTERN.search(candidate.data_claim)
    if claim_match is None:
        if _NO_PAIRED_DIVISION_CLAIM not in candidate.data_claim:
            return None
        if hansard_division_count == 0:
            return None
        return f"pairing {MinutesDivisionPairing.PAIRED}, Hansard division {random.Random(candidate.database_key).randint(1, hansard_division_count)}"
    other_numbers = [
        number
        for number in range(1, hansard_division_count + 1)
        if number != int(claim_match.group(1))
    ]
    if not other_numbers:
        return None
    return (
        candidate.data_claim[: claim_match.start(1)]
        + str(random.Random(candidate.database_key).choice(other_numbers))
        + candidate.data_claim[claim_match.end(1) :]
    )


def _replace_date(
    candidate: DivisionCheckCandidate, candidates: list[DivisionCheckCandidate]
) -> Optional[str]:
    claim_match = _CLAIMED_SITTING_DATE_PATTERN.search(candidate.data_claim)
    if claim_match is None:
        return None
    claimed_date = date.fromisoformat(claim_match.group(1))
    other_dates: set[date] = set()
    for other_candidate in candidates:
        other_match = _CLAIMED_SITTING_DATE_PATTERN.search(other_candidate.data_claim)
        if other_match is not None:
            other_dates.add(date.fromisoformat(other_match.group(1)))
    other_dates.discard(claimed_date)
    if not other_dates:
        return None
    nearest_date = min(
        other_dates,
        key=lambda other_date: (abs((other_date - claimed_date).days), other_date),
    )
    return (
        candidate.data_claim[: claim_match.start(1)]
        + nearest_date.isoformat()
        + candidate.data_claim[claim_match.end(1) :]
    )


def _replace_party(
    candidate: DivisionCheckCandidate, candidates: list[DivisionCheckCandidate]
) -> Optional[str]:
    claim_match = _CLAIMED_PARTY_PATTERN.match(candidate.data_claim)
    if claim_match is None:
        return None
    claimed_party = claim_match.group(1)
    _, _, spans_text = candidate.source_text.partition(_SOURCE_SPANS_MARKER)
    span_parties = [
        span_match.group(1)
        for span_text in spans_text.split(_SOURCE_SPAN_SEPARATOR)
        for span_match in [_SOURCE_SPAN_PARTY_PATTERN.match(span_text)]
        if span_match is not None and span_match.group(1) != claimed_party
    ]
    if span_parties:
        other_party = span_parties[0]
    else:
        frame_parties: set[str] = set()
        for other_candidate in candidates:
            other_match = _CLAIMED_PARTY_PATTERN.match(other_candidate.data_claim)
            if other_match is not None:
                frame_parties.add(other_match.group(1))
        frame_parties.discard(claimed_party)
        if not frame_parties:
            return None
        other_party = random.Random(candidate.database_key).choice(
            sorted(frame_parties)
        )
    return (
        candidate.data_claim[: claim_match.start(1)]
        + other_party
        + candidate.data_claim[claim_match.end(1) :]
    )


def build_plant_claim(
    kind: DivisionCheckPlantKind,
    candidate: DivisionCheckCandidate,
    candidates: list[DivisionCheckCandidate],
) -> Optional[str]:
    if kind == DivisionCheckPlantKind.SWAPPED_SIDE:
        return _swap_sides(candidate.data_claim)
    if kind == DivisionCheckPlantKind.WRONG_COUNT_DIGIT:
        return _change_count_digit(candidate.data_claim)
    if kind == DivisionCheckPlantKind.WRONG_PERSON:
        return _replace_person(candidate, candidates)
    if kind == DivisionCheckPlantKind.WRONG_DATE:
        return _replace_date(candidate, candidates)
    if kind == DivisionCheckPlantKind.WRONG_PARTY:
        return _replace_party(candidate, candidates)
    if kind == DivisionCheckPlantKind.WRONG_PAIR:
        return _replace_pair(candidate)
    raise HansardDivisionCheckError(f"No plant is built for {kind}")


def _get_usable_plants(
    kind: DivisionCheckPlantKind,
    pool: list[DivisionCheckCandidate],
    claim_candidates: list[DivisionCheckCandidate],
) -> list[PlantedCandidate]:
    return [
        PlantedCandidate(candidate, kind, planted_claim)
        for candidate in pool
        for planted_claim in [build_plant_claim(kind, candidate, claim_candidates)]
        if planted_claim is not None and planted_claim != candidate.data_claim
    ]


def _draw_copy_plants(
    kind: DivisionCheckPlantKind,
    candidates: list[DivisionCheckCandidate],
    drawn_candidates: list[DivisionCheckCandidate],
    seed: int,
    copy_count: int,
) -> list[PlantedCandidate]:
    copy_plants = _get_usable_plants(
        kind,
        sorted(drawn_candidates, key=lambda candidate: candidate.database_key),
        candidates,
    )
    return random.Random(
        f"{seed}{_GROUP_SEPARATOR}copy{_GROUP_SEPARATOR}{kind}"
    ).sample(copy_plants, min(len(copy_plants), copy_count))


def draw_plants(
    candidates: list[DivisionCheckCandidate],
    drawn_candidates: list[DivisionCheckCandidate],
    kinds: tuple[DivisionCheckPlantKind, ...],
    seed: int,
    load_sibling_candidates: Callable[[], list[DivisionCheckCandidate]],
) -> list[PlantedCandidate]:
    drawn_keys = {candidate.database_key for candidate in drawn_candidates}
    outside_candidates = sorted(
        (
            candidate
            for candidate in candidates
            if candidate.database_key not in drawn_keys
        ),
        key=lambda candidate: candidate.database_key,
    )
    planted_candidates: list[PlantedCandidate] = []
    for kind in kinds:
        usable_plants = _get_usable_plants(kind, outside_candidates, candidates)
        if len(usable_plants) < _PLANT_COUNT_PER_KIND:
            sibling_candidates = load_sibling_candidates()
            usable_plants = usable_plants + _get_usable_plants(
                kind,
                sorted(
                    sibling_candidates, key=lambda candidate: candidate.database_key
                ),
                candidates + sibling_candidates,
            )
        kind_planted_candidates = random.Random(
            f"{seed}{_GROUP_SEPARATOR}plant{_GROUP_SEPARATOR}{kind}"
        ).sample(usable_plants, min(len(usable_plants), _PLANT_COUNT_PER_KIND))
        if len(kind_planted_candidates) < _PLANT_COUNT_PER_KIND:
            kind_planted_candidates = kind_planted_candidates + _draw_copy_plants(
                kind,
                candidates,
                drawn_candidates,
                seed,
                _PLANT_COUNT_PER_KIND - len(kind_planted_candidates),
            )
        if not kind_planted_candidates:
            raise HansardDivisionCheckError(
                f"No row of the frame or its sibling frames can take a {kind} plant; the check would carry no planted error"
            )
        planted_candidates.extend(kind_planted_candidates)
    return planted_candidates


def build_packets_and_key(
    rule: DivisionCheckRule,
    seed: int,
    drawn_candidates: list[DivisionCheckCandidate],
    planted_candidates: list[PlantedCandidate],
) -> DivisionCheckPacketsAndKey:
    packet_drafts = [
        _PacketDraft(
            candidate.source_text, candidate.data_claim, candidate.database_key, None
        )
        for candidate in drawn_candidates
    ] + [
        _PacketDraft(
            planted.candidate.source_text,
            planted.planted_claim,
            planted.candidate.database_key,
            planted.kind,
        )
        for planted in planted_candidates
    ]
    generator = random.Random(seed)
    generator.shuffle(packet_drafts)
    packets: list[DivisionCheckPacket] = []
    plants: list[DivisionCheckPlant] = []
    packet_id_to_database_key: dict[str, str] = {}
    for packet_draft in packet_drafts:
        packet_id = f"{generator.getrandbits(_PACKET_ID_BITS):016x}"
        while packet_id in packet_id_to_database_key:
            packet_id = f"{generator.getrandbits(_PACKET_ID_BITS):016x}"
        packets.append(
            DivisionCheckPacket(
                packet_id=packet_id,
                source_text=packet_draft.source_text,
                data_claim=packet_draft.data_claim,
            )
        )
        packet_id_to_database_key[packet_id] = packet_draft.database_key
        if packet_draft.plant_kind is not None:
            plants.append(
                DivisionCheckPlant(packet_id=packet_id, kind=packet_draft.plant_kind)
            )
    return DivisionCheckPacketsAndKey(
        packets,
        DivisionCheckKey(
            seed=seed,
            rule=rule,
            plants=plants,
            packet_id_to_database_key=packet_id_to_database_key,
        ),
    )


def get_summary_lines(
    rule: DivisionCheckRule,
    seed: int,
    database_label: str,
    candidates: list[DivisionCheckCandidate],
    drawn_candidates: list[DivisionCheckCandidate],
    planted_candidates: list[PlantedCandidate],
) -> list[str]:
    group_to_size: defaultdict[str, int] = defaultdict(int)
    for candidate in candidates:
        group_to_size[candidate.group] += 1
    group_to_draw_size: defaultdict[str, int] = defaultdict(int)
    for candidate in drawn_candidates:
        group_to_draw_size[candidate.group] += 1
    applicable_kinds = get_plant_kinds(rule)
    drawn_keys = {candidate.database_key for candidate in drawn_candidates}
    lines = [
        f"rule\t{rule}",
        f"seed\t{seed}",
        f"database\t{database_label}",
        f"candidates\t{len(candidates)}",
        f"drawn\t{len(drawn_candidates)}",
        "group\tsize\tdrawn",
        *[
            f"{group}\t{group_to_size[group]}\t{group_to_draw_size[group]}"
            for group in sorted(group_to_size)
        ],
    ]
    for kind in DivisionCheckPlantKind:
        if kind not in applicable_kinds:
            lines.append(f"plant kind {kind}: not used for this rule")
            continue
        kind_planted_candidates = [
            planted for planted in planted_candidates if planted.kind == kind
        ]
        lines.append(
            f"plant kind {kind}: {len(kind_planted_candidates)} planted, {sum(planted.candidate.rule != rule for planted in kind_planted_candidates)} from the frames of sibling rules, {sum(planted.candidate.database_key in drawn_keys for planted in kind_planted_candidates)} copies of sampled rows"
        )
    return lines


def _is_packet_allowed_in_batch(
    batch: _ReaderBatch, packet: DivisionCheckPacket, database_key: str
) -> bool:
    return (
        len(batch.packets) < _MAX_BATCH_PACKETS
        and batch.character_count + len(packet.source_text) + len(packet.data_claim)
        <= _MAX_BATCH_CHARACTERS
        and database_key not in batch.database_keys
    )


def _claim_batch_for_packet(
    batches: list[_ReaderBatch], packet: DivisionCheckPacket, database_key: str
) -> _ReaderBatch:
    for batch in batches:
        if _is_packet_allowed_in_batch(batch, packet, database_key):
            return batch
    new_batch = _ReaderBatch([], 0, set())
    batches.append(new_batch)
    return new_batch


def get_reader_batches(
    packets: list[DivisionCheckPacket], packet_id_to_database_key: dict[str, str]
) -> list[list[DivisionCheckPacket]]:
    batches: list[_ReaderBatch] = []
    for packet in packets:
        database_key = packet_id_to_database_key[packet.packet_id]
        batch = _claim_batch_for_packet(batches, packet, database_key)
        batch.packets.append(packet)
        batch.character_count += len(packet.source_text) + len(packet.data_claim)
        batch.database_keys.add(database_key)
    return [batch.packets for batch in batches]


def write_check_files(
    output_directory: Path,
    packets: list[DivisionCheckPacket],
    key: DivisionCheckKey,
    summary_lines: list[str],
) -> None:
    output_directory.mkdir(parents=True)
    (output_directory / _PACKETS_FILE_NAME).write_bytes(
        TypeAdapter(list[DivisionCheckPacket]).dump_json(packets, indent=2)
    )
    key_bytes = key.model_dump_json(indent=2).encode("utf-8")
    (output_directory / _KEY_FILE_NAME).write_bytes(key_bytes)
    (output_directory / _KEY_HASH_FILE_NAME).write_text(
        f"{hashlib.sha256(key_bytes).hexdigest()}\n", encoding="utf-8"
    )
    (output_directory / _SUMMARY_FILE_NAME).write_text(
        _LINE_SEPARATOR.join(summary_lines) + _LINE_SEPARATOR, encoding="utf-8"
    )
    for batch_number, batch_packets in enumerate(
        get_reader_batches(packets, key.packet_id_to_database_key), start=1
    ):
        batch_directory = (
            output_directory / _BATCHES_DIRECTORY_NAME / f"batch-{batch_number:02d}"
        )
        batch_directory.mkdir(parents=True)
        (batch_directory / _PACKETS_FILE_NAME).write_bytes(
            TypeAdapter(list[DivisionCheckPacket]).dump_json(batch_packets, indent=2)
        )


def draw_division_check_sample(
    rule: DivisionCheckRule, seed: int, output_directory: Path
) -> None:
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_READ_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        candidates = get_division_check_candidates(session, rule)
        drawn_candidates = draw_candidates(candidates, seed)
        planted_candidates = draw_plants(
            candidates,
            drawn_candidates,
            get_plant_kinds(rule),
            seed,
            lambda: get_sibling_candidates(session, rule),
        )
    packets_and_key = build_packets_and_key(
        rule, seed, drawn_candidates, planted_candidates
    )
    summary_lines = get_summary_lines(
        rule,
        seed,
        get_database_label(settings.database_url),
        candidates,
        drawn_candidates,
        planted_candidates,
    )
    write_check_files(
        output_directory, packets_and_key.packets, packets_and_key.key, summary_lines
    )
    logger.info(
        f"Wrote {len(packets_and_key.packets)} packets, {len(packets_and_key.key.plants)} planted, to {output_directory}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Draw one division check sample for one rule, read only: packets for the readers, a sealed key and its SHA-256"
    )
    parser.add_argument(
        "--rule",
        type=DivisionCheckRule,
        choices=list(DivisionCheckRule),
        required=True,
        help="the rule whose stored facts are sampled",
    )
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="an integer recorded in the summary; the same seed draws the same packets",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="where to write the files; the directory must not exist yet",
    )
    arguments = parser.parse_args()
    draw_division_check_sample(
        arguments.rule, arguments.seed, arguments.output_directory
    )

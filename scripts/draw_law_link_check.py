import argparse
import hashlib
import math
import random
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.act_history_entry import ActHistoryEntryRow, CRUDActHistoryEntry
from crud.bill import BillRow, CRUDBill
from crud.bill_key import BillKeyRow, CRUDBillKey
from crud.bill_report import BillReportSittingDateReportTypeRow, CRUDBillReport
from crud.bill_report_speaker import BillReportSpeakerRow, CRUDBillReportSpeaker
from crud.bill_stage_line import BillStageLineRow, CRUDBillStageLine
from crud.report import CRUDReport, ReportPlacementRow
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechParseRow
from database.init import build_read_only_engine
from enums import BillLinkSource, BillStage, LawLinkCheckRule
from exceptions import HansardLawLinkCheckError
from logs import logger
from schemas.law_link_check_packet import LawLinkCheckPacket, LawLinkCheckPackets
from schemas.law_link_check_plant_key import LawLinkCheckPlant, LawLinkCheckPlantKey
from settings import settings
from utils.database_label import get_database_label

_DEFAULT_SEED = 20_261_120
_GROUP_SAMPLE_SIZE = 50
_PLANTS_PER_RULE = 5
_YEARS_PER_DECADE = 10
_DRAW_ISOLATION_LEVEL = "REPEATABLE READ"
_PACKET_ID_LENGTH = 12
_PACKET_ID_LIMIT = 16**_PACKET_ID_LENGTH
_BATCH_PACKET_LIMIT = 50
_BATCH_CHARACTER_LIMIT = 80_000
_RECORDS_DIRECTORY_NAME = "records"
_BATCHES_DIRECTORY_NAME = "batches"
_PACKETS_FILE_NAME = "packets.json"
_SUMMARY_FILE_NAME = "draw-summary.txt"
_BATCH_FILE_NAME = "packets-{batch_number:03d}.md"
_NO_DATE_TEXT = "not printed"
_ACT_RULES = frozenset(
    {
        LawLinkCheckRule.ACT_FIRST_READING_DATE,
        LawLinkCheckRule.ACT_THIRD_READING_DATE,
        LawLinkCheckRule.ACT_LOOSE_TITLE_READING_DATES,
        LawLinkCheckRule.ACT_HAND_KEPT,
    }
)
_BATCH_LEGEND = (
    "For each packet below, decide whether the data says what the source text and the rule support. "
    "Answer RIGHT, WRONG or RECORD_DOES_NOT_SAY, with a one-sentence note. "
    "Make no link and clear no flag."
)
_RULE_TO_RULE_TEXT = {
    LawLinkCheckRule.ACT_FIRST_READING_DATE: "The Act entry's title, read as a Bill title, equals the Bill's title, and one of the Bill's reports is dated within a day of the entry's first reading date.",
    LawLinkCheckRule.ACT_THIRD_READING_DATE: "The Act entry's title, read as a Bill title, equals the Bill's title, and one of the Bill's reports is dated within a day of the entry's third reading date.",
    LawLinkCheckRule.ACT_LOOSE_TITLE_READING_DATES: "The titles are equal once the words amendment and any number are left out, and exactly one Bill with that title has reports within a day of the entry's first and third reading dates.",
    LawLinkCheckRule.ACT_HAND_KEPT: "A person matched this entry to this Bill by hand, from the printed titles and the Bill's reports.",
    LawLinkCheckRule.MEMBER: "A Member row stands for the speech rows credited to a Member in one report of a Bill. It shows the first of them.",
    LawLinkCheckRule.STAGE_FIRST_READING: "A procedural or unclassified line that prints 'read a first time' proves the first reading.",
    LawLinkCheckRule.STAGE_SECOND_READING_ORDER: "A procedural or unclassified line that prints 'Order for Second Reading read' proves the order for the second reading.",
    LawLinkCheckRule.STAGE_SECOND_READING_AGREED: "A procedural or unclassified line that prints 'Bill accordingly read a Second time' proves the House agreed the second reading.",
    LawLinkCheckRule.STAGE_THIRD_READING: "A procedural or unclassified line that prints 'Bill' and then 'read a Third time', and is not a motion to read it, proves the third reading.",
}


@dataclass(frozen=True)
class LawLinkCheckInputs:
    bill_id_to_bill: dict[int, BillRow]
    bill_id_to_bill_key: dict[int, BillKeyRow]
    bill_id_to_bill_report_rows: dict[int, list[BillReportSittingDateReportTypeRow]]
    sprs_report_id_to_bill_report_row: dict[str, BillReportSittingDateReportTypeRow]
    act_history_entry_id_to_row: dict[int, ActHistoryEntryRow]
    bill_report_speaker_id_to_row: dict[int, BillReportSpeakerRow]
    bill_stage_line_id_to_row: dict[int, BillStageLineRow]
    speaker_id_to_name: dict[int, str]


@dataclass(frozen=True)
class LawLinkCheckCandidate:
    rule: LawLinkCheckRule
    group: str
    row_id: int


@dataclass(frozen=True)
class PlantedChoice:
    candidate: LawLinkCheckCandidate
    rule: LawLinkCheckRule
    claimed_row_id: int


@dataclass(frozen=True)
class PacketRequest:
    rule: LawLinkCheckRule
    group: str
    row_id: int
    claimed_row_id: int
    is_planted: bool


@dataclass(frozen=True)
class LawLinkCheckTexts:
    report_id_to_placement_row: dict[int, ReportPlacementRow]
    report_id_and_ordinal_to_speech_row: dict[tuple[int, int], SpeechParseRow]


@dataclass(frozen=True)
class PacketText:
    source_text: str
    data_says: str
    stored_value: str
    claimed_value: str


@dataclass(frozen=True)
class LawLinkCheck:
    packets: list[LawLinkCheckPacket]
    plant_key: LawLinkCheckPlantKey
    rule_lines: list[str]


def read_law_link_check_inputs(session: Session) -> LawLinkCheckInputs:
    bill_report_rows = CRUDBillReport(session).get_sitting_date_report_type_rows()
    bill_id_to_bill_report_rows: dict[
        int, list[BillReportSittingDateReportTypeRow]
    ] = {}
    for bill_report_row in bill_report_rows:
        bill_id_to_bill_report_rows.setdefault(bill_report_row.bill_id, []).append(
            bill_report_row
        )
    return LawLinkCheckInputs(
        bill_id_to_bill={
            bill_row.id: bill_row for bill_row in CRUDBill(session).get_rows()
        },
        bill_id_to_bill_key={
            bill_key_row.bill_id: bill_key_row
            for bill_key_row in CRUDBillKey(session).get_rows()
        },
        bill_id_to_bill_report_rows=bill_id_to_bill_report_rows,
        sprs_report_id_to_bill_report_row={
            bill_report_row.sprs_report_id: bill_report_row
            for bill_report_row in bill_report_rows
        },
        act_history_entry_id_to_row={
            entry_row.id: entry_row
            for entry_row in CRUDActHistoryEntry(session).get_rows()
        },
        bill_report_speaker_id_to_row={
            member_row.id: member_row
            for member_row in CRUDBillReportSpeaker(session).get_rows()
        },
        bill_stage_line_id_to_row={
            stage_line_row.id: stage_line_row
            for stage_line_row in CRUDBillStageLine(session).get_rows()
        },
        speaker_id_to_name={
            speaker.id: speaker.name
            for speaker in CRUDSpeaker(session).get_all()
            if speaker.id is not None
        },
    )


def _get_decade_group(sitting_date: datetime, report_type: str) -> str:
    decade = sitting_date.year // _YEARS_PER_DECADE * _YEARS_PER_DECADE
    return f"{decade}s {report_type}"


def _get_report_group(sprs_report_id: str, inputs: LawLinkCheckInputs) -> str:
    try:
        bill_report_row = inputs.sprs_report_id_to_bill_report_row[sprs_report_id]
    except KeyError as error:
        raise HansardLawLinkCheckError(
            f"Report {sprs_report_id} holds member or stage rows, but no bill holds the report"
        ) from error
    return _get_decade_group(bill_report_row.sitting_date, bill_report_row.report_type)


def _get_act_group(entry_id: int, bill_id: int, inputs: LawLinkCheckInputs) -> str:
    try:
        bill_row = inputs.bill_id_to_bill[bill_id]
        bill_key_row = inputs.bill_id_to_bill_key[bill_id]
        key_report_row = inputs.sprs_report_id_to_bill_report_row[bill_key_row.bill_key]
    except KeyError as error:
        raise HansardLawLinkCheckError(
            f"Act entry {entry_id} links to bill {bill_id}, which has no key report; run apply_bill_speakers first"
        ) from error
    return _get_decade_group(bill_row.first_sitting_date, key_report_row.report_type)


def _get_act_rule(
    bill_link_source: Optional[BillLinkSource],
) -> Optional[LawLinkCheckRule]:
    if bill_link_source == BillLinkSource.FIRST_READING_DATE:
        return LawLinkCheckRule.ACT_FIRST_READING_DATE
    if bill_link_source == BillLinkSource.THIRD_READING_DATE:
        return LawLinkCheckRule.ACT_THIRD_READING_DATE
    if bill_link_source == BillLinkSource.LOOSE_TITLE_READING_DATES:
        return LawLinkCheckRule.ACT_LOOSE_TITLE_READING_DATES
    if bill_link_source == BillLinkSource.HAND_KEPT:
        return LawLinkCheckRule.ACT_HAND_KEPT
    return None


def _get_stage_rule(stage: BillStage) -> LawLinkCheckRule:
    if stage == BillStage.FIRST_READING:
        return LawLinkCheckRule.STAGE_FIRST_READING
    if stage == BillStage.SECOND_READING_ORDER:
        return LawLinkCheckRule.STAGE_SECOND_READING_ORDER
    if stage == BillStage.SECOND_READING_AGREED:
        return LawLinkCheckRule.STAGE_SECOND_READING_AGREED
    if stage == BillStage.THIRD_READING:
        return LawLinkCheckRule.STAGE_THIRD_READING
    raise HansardLawLinkCheckError(f"No law link check rule is named for stage {stage}")


def get_candidates(inputs: LawLinkCheckInputs) -> list[LawLinkCheckCandidate]:
    candidates = []
    for entry_id in sorted(inputs.act_history_entry_id_to_row):
        entry_row = inputs.act_history_entry_id_to_row[entry_id]
        if entry_row.bill_link_source == BillLinkSource.SIMILAR_TITLE_READING_DATES:
            raise HansardLawLinkCheckError(
                f"Act entry {entry_id} still carries SIMILAR_TITLE_READING_DATES; run apply_hand_kept_act_links --commit before the draw"
            )
        if entry_row.bill_id is None:
            continue
        rule = _get_act_rule(entry_row.bill_link_source)
        if rule is None:
            continue
        candidates.append(
            LawLinkCheckCandidate(
                rule, _get_act_group(entry_id, entry_row.bill_id, inputs), entry_id
            )
        )
    for member_row in inputs.bill_report_speaker_id_to_row.values():
        candidates.append(
            LawLinkCheckCandidate(
                LawLinkCheckRule.MEMBER,
                _get_report_group(member_row.sprs_report_id, inputs),
                member_row.id,
            )
        )
    for stage_line_row in inputs.bill_stage_line_id_to_row.values():
        candidates.append(
            LawLinkCheckCandidate(
                _get_stage_rule(stage_line_row.stage),
                _get_report_group(stage_line_row.sprs_report_id, inputs),
                stage_line_row.id,
            )
        )
    return candidates


def get_drawn_candidates(
    candidates: list[LawLinkCheckCandidate], generator: random.Random
) -> list[LawLinkCheckCandidate]:
    rule_to_group_to_candidates: dict[
        LawLinkCheckRule, dict[str, list[LawLinkCheckCandidate]]
    ] = {}
    for candidate in sorted(candidates, key=lambda candidate: candidate.row_id):
        rule_to_group_to_candidates.setdefault(candidate.rule, {}).setdefault(
            candidate.group, []
        ).append(candidate)
    drawn_candidates: list[LawLinkCheckCandidate] = []
    for rule in LawLinkCheckRule:
        group_to_candidates = rule_to_group_to_candidates.get(rule, {})
        for group in sorted(group_to_candidates):
            group_candidates = group_to_candidates[group]
            if len(group_candidates) <= _GROUP_SAMPLE_SIZE:
                drawn_candidates.extend(group_candidates)
                continue
            interval = Fraction(len(group_candidates), _GROUP_SAMPLE_SIZE)
            # NOTE: only random() is called, the one method Python keeps stable across versions for a seed
            start = Fraction(generator.random()) * interval
            drawn_candidates.extend(
                group_candidates[math.floor(start + pick_index * interval)]
                for pick_index in range(_GROUP_SAMPLE_SIZE)
            )
    return drawn_candidates


def get_plant_pool(
    rule: LawLinkCheckRule,
    candidates: list[LawLinkCheckCandidate],
    drawn_candidates: list[LawLinkCheckCandidate],
) -> list[LawLinkCheckCandidate]:
    drawn_candidate_set = set(drawn_candidates)
    pool = sorted(
        (
            candidate
            for candidate in candidates
            if candidate.rule == rule and candidate not in drawn_candidate_set
        ),
        key=lambda candidate: candidate.row_id,
    )
    if len(pool) >= _PLANTS_PER_RULE or rule not in _ACT_RULES:
        return pool
    return sorted(
        (
            candidate
            for candidate in candidates
            if candidate.rule == LawLinkCheckRule.ACT_FIRST_READING_DATE
            and candidate not in drawn_candidate_set
        ),
        key=lambda candidate: candidate.row_id,
    )


def _get_linked_bill(entry_id: int, inputs: LawLinkCheckInputs) -> BillRow:
    bill_id = inputs.act_history_entry_id_to_row[entry_id].bill_id
    if bill_id is None:
        raise HansardLawLinkCheckError(f"Act entry {entry_id} links to no bill")
    return inputs.bill_id_to_bill[bill_id]


def get_claimable_row_ids(
    rule: LawLinkCheckRule, row_id: int, inputs: LawLinkCheckInputs
) -> list[int]:
    if rule in _ACT_RULES:
        title_key = _get_linked_bill(row_id, inputs).title_key
        return [
            entry_id
            for entry_id in sorted(inputs.act_history_entry_id_to_row)
            if inputs.act_history_entry_id_to_row[entry_id].bill_id is not None
            and _get_linked_bill(entry_id, inputs).title_key != title_key
        ]
    if rule == LawLinkCheckRule.MEMBER:
        member_row = inputs.bill_report_speaker_id_to_row[row_id]
        return [
            other_id
            for other_id in sorted(inputs.bill_report_speaker_id_to_row)
            if inputs.bill_report_speaker_id_to_row[other_id].sprs_report_id
            == member_row.sprs_report_id
            and inputs.bill_report_speaker_id_to_row[other_id].speaker_id
            != member_row.speaker_id
        ]
    stage = inputs.bill_stage_line_id_to_row[row_id].stage
    return [
        other_id
        for other_id in sorted(inputs.bill_stage_line_id_to_row)
        if inputs.bill_stage_line_id_to_row[other_id].stage != stage
    ]


def get_rule_planted_choices(
    rule: LawLinkCheckRule,
    candidates: list[LawLinkCheckCandidate],
    drawn_candidates: list[LawLinkCheckCandidate],
    inputs: LawLinkCheckInputs,
    generator: random.Random,
) -> list[PlantedChoice]:
    pool = get_plant_pool(rule, candidates, drawn_candidates)
    planted_choices = []
    while len(planted_choices) < _PLANTS_PER_RULE:
        if not pool:
            raise HansardLawLinkCheckError(
                f"No row is left to plant {_PLANTS_PER_RULE} errors in for {rule}"
            )
        candidate = pool.pop(int(generator.random() * len(pool)))
        claimable_row_ids = get_claimable_row_ids(rule, candidate.row_id, inputs)
        if not claimable_row_ids:
            continue
        planted_choices.append(
            PlantedChoice(
                candidate,
                rule,
                claimable_row_ids[int(generator.random() * len(claimable_row_ids))],
            )
        )
    return planted_choices


def get_planted_choices(
    candidates: list[LawLinkCheckCandidate],
    drawn_candidates: list[LawLinkCheckCandidate],
    inputs: LawLinkCheckInputs,
    generator: random.Random,
) -> list[PlantedChoice]:
    return [
        planted_choice
        for rule in LawLinkCheckRule
        for planted_choice in get_rule_planted_choices(
            rule, candidates, drawn_candidates, inputs, generator
        )
    ]


def get_packet_requests(
    drawn_candidates: list[LawLinkCheckCandidate],
    planted_choices: list[PlantedChoice],
) -> list[PacketRequest]:
    return [
        PacketRequest(
            candidate.rule, candidate.group, candidate.row_id, candidate.row_id, False
        )
        for candidate in drawn_candidates
    ] + [
        PacketRequest(
            planted_choice.rule,
            planted_choice.candidate.group,
            planted_choice.candidate.row_id,
            planted_choice.claimed_row_id,
            True,
        )
        for planted_choice in planted_choices
    ]


def get_request_report_ids(
    request: PacketRequest, inputs: LawLinkCheckInputs
) -> list[int]:
    if request.rule in _ACT_RULES:
        return [
            bill_report_row.report_id
            for entry_id in (request.row_id, request.claimed_row_id)
            for bill_report_row in inputs.bill_id_to_bill_report_rows[
                _get_linked_bill(entry_id, inputs).id
            ]
        ]
    if request.rule == LawLinkCheckRule.MEMBER:
        return [
            inputs.sprs_report_id_to_bill_report_row[
                inputs.bill_report_speaker_id_to_row[request.row_id].sprs_report_id
            ].report_id
        ]
    return [
        inputs.sprs_report_id_to_bill_report_row[
            inputs.bill_stage_line_id_to_row[request.row_id].sprs_report_id
        ].report_id
    ]


def read_law_link_check_texts(
    session: Session, requests: list[PacketRequest], inputs: LawLinkCheckInputs
) -> LawLinkCheckTexts:
    report_ids = sorted(
        {
            report_id
            for request in requests
            for report_id in get_request_report_ids(request, inputs)
        }
    )
    member_report_ids = sorted(
        {
            report_id
            for request in requests
            if request.rule == LawLinkCheckRule.MEMBER
            for report_id in get_request_report_ids(request, inputs)
        }
    )
    return LawLinkCheckTexts(
        report_id_to_placement_row={
            placement_row.id: placement_row
            for placement_row in CRUDReport(session).get_placement_rows_by_ids(
                report_ids
            )
        },
        report_id_and_ordinal_to_speech_row={
            (speech_row.report_id, speech_row.ordinal): speech_row
            for speech_row in CRUDSpeech(session).get_parse_rows_by_report_ids(
                member_report_ids
            )
        },
    )


def _get_date_text(value: Optional[date]) -> str:
    return _NO_DATE_TEXT if value is None else value.isoformat()


def _get_report_line(report_id: int, texts: LawLinkCheckTexts) -> str:
    placement_row = texts.report_id_to_placement_row[report_id]
    return f"{placement_row.title}, {placement_row.sitting_date:%d %B %Y}, report type {placement_row.report_type}"


def build_act_packet_text(
    request: PacketRequest, inputs: LawLinkCheckInputs, texts: LawLinkCheckTexts
) -> PacketText:
    entry_row = inputs.act_history_entry_id_to_row[request.row_id]
    bill_row = _get_linked_bill(request.row_id, inputs)
    claimed_bill_row = _get_linked_bill(request.claimed_row_id, inputs)
    return PacketText(
        source_text="\n".join(
            [
                entry_row.printed_text,
                "",
                f"Dates the rule read: first reading {_get_date_text(entry_row.first_reading_date)}, second reading {_get_date_text(entry_row.second_reading_date)}, third reading {_get_date_text(entry_row.third_reading_date)}.",
            ]
        ),
        data_says="\n".join(
            [
                f"Linked to the Bill {claimed_bill_row.title}.",
                "The Bill's reports:",
                *(
                    f"- {_get_report_line(bill_report_row.report_id, texts)}"
                    for bill_report_row in inputs.bill_id_to_bill_report_rows[
                        claimed_bill_row.id
                    ]
                ),
            ]
        ),
        stored_value=bill_row.title,
        claimed_value=claimed_bill_row.title,
    )


def build_member_packet_text(
    request: PacketRequest, inputs: LawLinkCheckInputs, texts: LawLinkCheckTexts
) -> PacketText:
    member_row = inputs.bill_report_speaker_id_to_row[request.row_id]
    claimed_member_row = inputs.bill_report_speaker_id_to_row[request.claimed_row_id]
    report_id = inputs.sprs_report_id_to_bill_report_row[
        member_row.sprs_report_id
    ].report_id
    try:
        speech_row = texts.report_id_and_ordinal_to_speech_row[
            (report_id, member_row.first_ordinal)
        ]
    except KeyError as error:
        raise HansardLawLinkCheckError(
            f"Member row {member_row.id} names ordinal {member_row.first_ordinal}, which its report does not hold"
        ) from error
    claimed_name = inputs.speaker_id_to_name[claimed_member_row.speaker_id]
    return PacketText(
        source_text="\n".join(
            [
                f"Report: {_get_report_line(report_id, texts)}",
                f"{speech_row.speaker}: {speech_row.transcript}",
            ]
        ),
        data_says="\n".join(
            [
                f"Member: {claimed_name}",
                f"Speech rows credited in this report: {member_row.speech_count}, the first printed as {member_row.printed_speaker}.",
            ]
        ),
        stored_value=inputs.speaker_id_to_name[member_row.speaker_id],
        claimed_value=claimed_name,
    )


def build_stage_packet_text(
    request: PacketRequest, inputs: LawLinkCheckInputs, texts: LawLinkCheckTexts
) -> PacketText:
    stage_line_row = inputs.bill_stage_line_id_to_row[request.row_id]
    claimed_stage_line_row = inputs.bill_stage_line_id_to_row[request.claimed_row_id]
    report_id = inputs.sprs_report_id_to_bill_report_row[
        stage_line_row.sprs_report_id
    ].report_id
    return PacketText(
        source_text="\n".join(
            [
                f"Report: {_get_report_line(report_id, texts)}",
                stage_line_row.printed_text,
            ]
        ),
        data_says=f"Stage: {claimed_stage_line_row.stage.value}",
        stored_value=stage_line_row.stage.value,
        claimed_value=claimed_stage_line_row.stage.value,
    )


def build_packet_text(
    request: PacketRequest, inputs: LawLinkCheckInputs, texts: LawLinkCheckTexts
) -> PacketText:
    if request.rule in _ACT_RULES:
        return build_act_packet_text(request, inputs, texts)
    if request.rule == LawLinkCheckRule.MEMBER:
        return build_member_packet_text(request, inputs, texts)
    return build_stage_packet_text(request, inputs, texts)


def get_packet_ids(count: int, generator: random.Random) -> list[str]:
    packet_ids = [
        f"{int(generator.random() * _PACKET_ID_LIMIT):0{_PACKET_ID_LENGTH}x}"
        for _ in range(count)
    ]
    if len(set(packet_ids)) != count:
        raise HansardLawLinkCheckError(
            "Two packets drew the same id; draw again with another seed"
        )
    return packet_ids


def get_rule_lines(
    candidates: list[LawLinkCheckCandidate],
    drawn_candidates: list[LawLinkCheckCandidate],
    planted_choices: list[PlantedChoice],
) -> list[str]:
    rule_to_candidate_count = Counter(candidate.rule for candidate in candidates)
    rule_to_drawn_count = Counter(candidate.rule for candidate in drawn_candidates)
    rule_to_plant_count = Counter(
        planted_choice.rule for planted_choice in planted_choices
    )
    rule_to_group_count = Counter(
        rule
        for rule, _ in {(candidate.rule, candidate.group) for candidate in candidates}
    )
    return [
        "rule\tcandidates\tgroups\tdrawn\tplants",
        *(
            f"{rule.value}\t{rule_to_candidate_count[rule]}\t{rule_to_group_count[rule]}\t{rule_to_drawn_count[rule]}\t{rule_to_plant_count[rule]}"
            for rule in LawLinkCheckRule
        ),
    ]


def get_law_link_check(session: Session, seed: int) -> LawLinkCheck:
    generator = random.Random(seed)
    inputs = read_law_link_check_inputs(session)
    candidates = get_candidates(inputs)
    drawn_candidates = get_drawn_candidates(candidates, generator)
    planted_choices = get_planted_choices(
        candidates, drawn_candidates, inputs, generator
    )
    requests = get_packet_requests(drawn_candidates, planted_choices)
    texts = read_law_link_check_texts(session, requests, inputs)
    shuffle_keys = [generator.random() for _ in requests]
    shuffled_requests = [
        requests[request_index]
        for request_index in sorted(range(len(requests)), key=shuffle_keys.__getitem__)
    ]
    packets = []
    plants = []
    for packet_id, request in zip(
        get_packet_ids(len(shuffled_requests), generator),
        shuffled_requests,
        strict=True,
    ):
        packet_text = build_packet_text(request, inputs, texts)
        packets.append(
            LawLinkCheckPacket(
                packet_id=packet_id,
                rule=request.rule,
                group=request.group,
                row_id=request.row_id,
                source_text=packet_text.source_text,
                data_says=packet_text.data_says,
                rule_text=_RULE_TO_RULE_TEXT[request.rule],
            )
        )
        if request.is_planted:
            plants.append(
                LawLinkCheckPlant(
                    packet_id=packet_id,
                    rule=request.rule,
                    original=packet_text.stored_value,
                    planted=packet_text.claimed_value,
                )
            )
    return LawLinkCheck(
        packets,
        LawLinkCheckPlantKey(plants=plants),
        get_rule_lines(candidates, drawn_candidates, planted_choices),
    )


def render_packet(packet: LawLinkCheckPacket) -> str:
    return "\n".join(
        [
            f"## Packet {packet.packet_id}",
            "",
            f"Rule: {packet.rule_text}",
            "",
            "### Source text",
            "",
            packet.source_text,
            "",
            "### What the data says",
            "",
            packet.data_says,
        ]
    )


def get_batches(rendered_packets: list[str]) -> list[list[str]]:
    batches = []
    batch: list[str] = []
    batch_length = 0
    for rendered_packet in rendered_packets:
        if batch and (
            len(batch) == _BATCH_PACKET_LIMIT
            or batch_length + len(rendered_packet) > _BATCH_CHARACTER_LIMIT
        ):
            batches.append(batch)
            batch = []
            batch_length = 0
        batch.append(rendered_packet)
        batch_length += len(rendered_packet)
    if batch:
        batches.append(batch)
    return batches


def write_law_link_check_files(
    law_link_check: LawLinkCheck,
    summary_lines: list[str],
    output_directory: Path,
    key_path: Path,
    hash_path: Path,
) -> str:
    key_bytes = law_link_check.plant_key.model_dump_json(indent=2).encode("utf-8")
    digest = hashlib.sha256(key_bytes).hexdigest()
    with key_path.open("xb") as key_file:
        key_file.write(key_bytes)
    with hash_path.open("x", encoding="utf-8") as hash_file:
        hash_file.write(f"{digest}\n")
    records_directory = output_directory / _RECORDS_DIRECTORY_NAME
    batches_directory = output_directory / _BATCHES_DIRECTORY_NAME
    records_directory.mkdir(parents=True)
    batches_directory.mkdir()
    (records_directory / _PACKETS_FILE_NAME).write_text(
        LawLinkCheckPackets(law_link_check.packets).model_dump_json(indent=1),
        encoding="utf-8",
    )
    (records_directory / _SUMMARY_FILE_NAME).write_text(
        "\n".join([*summary_lines, f"key_sha256: {digest}"]) + "\n", encoding="utf-8"
    )
    for batch_number, batch in enumerate(
        get_batches([render_packet(packet) for packet in law_link_check.packets]),
        start=1,
    ):
        (
            batches_directory / _BATCH_FILE_NAME.format(batch_number=batch_number)
        ).write_text("\n\n".join([_BATCH_LEGEND, *batch]) + "\n", encoding="utf-8")
    return digest


def draw_law_link_check(
    seed: int, output_directory: Path, key_path: Path, hash_path: Path
) -> None:
    database_label = get_database_label(settings.database_url)
    logger.info(f"Drawing the law link check, read only, from {database_label}")
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_DRAW_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        read_at = datetime.now(timezone.utc)
        law_link_check = get_law_link_check(session, seed)

    summary_lines = [
        f"database_label: {database_label}",
        f"read_at: {read_at.isoformat()}",
        f"seed: {seed}",
        f"group_sample_size: {_GROUP_SAMPLE_SIZE}",
        f"plants_per_rule: {_PLANTS_PER_RULE}",
        f"packets: {len(law_link_check.packets)}",
        *law_link_check.rule_lines,
    ]
    digest = write_law_link_check_files(
        law_link_check, summary_lines, output_directory, key_path, hash_path
    )
    for line in summary_lines:
        logger.info(line)
    logger.info(f"Key SHA-256 {digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Draw the law link accuracy check from the database, read only: packets for the readers, a sealed plant key and its hash"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=_DEFAULT_SEED,
        help="the seed of the draw, the plants and the packet order; recorded in the summary file",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="write records/ and batches/ here; the directory must not exist yet",
    )
    parser.add_argument(
        "--key-output",
        type=Path,
        required=True,
        help="the sealed plant key, kept outside the output directory; written with mode x, so it may not exist yet",
    )
    parser.add_argument(
        "--hash-output",
        type=Path,
        required=True,
        help="the one-line SHA-256 file to commit before any reader starts; written with mode x, so it may not exist yet",
    )
    arguments = parser.parse_args()
    draw_law_link_check(
        arguments.seed,
        arguments.output_directory,
        arguments.key_output,
        arguments.hash_output,
    )

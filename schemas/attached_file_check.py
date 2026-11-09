from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel

from enums import (
    AttachedFileCheckAnswer,
    AttachedFileCheckPlantKind,
    AttachedFileKind,
    ParagraphTieRule,
)


class AttachedFileCheckPacket(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    sprs_report_id: str
    pointer_ordinal: int
    paragraph_tie_rule: ParagraphTieRule
    speech_ordinal: int
    attached_file_id: Optional[int]
    report_title: str
    link_words: str
    source_paragraph: str
    row_speaker: Optional[str]
    row_transcript: str
    file_kind: Optional[AttachedFileKind]
    file_title: Optional[str]


class AttachedFileCheckPackets(RootModel[list[AttachedFileCheckPacket]]):
    model_config = ConfigDict(frozen=True)


class AttachedFileCheckPlant(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    kind: AttachedFileCheckPlantKind
    true_speech_ordinal: Optional[int]
    true_attached_file_id: Optional[int]
    is_row_holding_link_words: Optional[bool]


class AttachedFileCheckKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    round_number: int
    seed: int
    packet_id_to_pointer_id: dict[str, int]
    plants: list[AttachedFileCheckPlant]


class AttachedFileCheckVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    paragraph_answer: AttachedFileCheckAnswer
    file_answer: Optional[AttachedFileCheckAnswer]
    note: str


class AttachedFileCheckFlag(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    round_number: int
    sprs_report_id: str
    pointer_ordinal: int
    speech_ordinal: int
    attached_file_id: Optional[int]
    link_words: str
    source_paragraph: str
    row_transcript: str
    file_title: Optional[str]
    paragraph_tie_rule: ParagraphTieRule
    sonnet: AttachedFileCheckVerdict
    opus: AttachedFileCheckVerdict


class AttachedFileCheckFlags(RootModel[list[AttachedFileCheckFlag]]):
    model_config = ConfigDict(frozen=True)

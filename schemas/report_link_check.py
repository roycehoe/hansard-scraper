from datetime import date

from pydantic import BaseModel, ConfigDict, RootModel

from enums import (
    ReportLinkPlantKind,
    ReportLinkRule,
    ReportLinkType,
    ReportLinkVerdict,
)


class ReportLinkCheckReportText(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    sitting_date: date
    opening_text: str


class ReportLinkCheckSameTitleReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    sitting_date: date
    opening_text: str
    closing_text: str
    is_link_target: bool


class ReportLinkCheckPacket(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    group: str
    rule: ReportLinkRule
    link_type: ReportLinkType
    source_report_id: str
    target_report_id: str
    printed_citation: str
    paragraph: str
    source_report: ReportLinkCheckReportText
    target_report: ReportLinkCheckReportText
    same_title_reports: list[ReportLinkCheckSameTitleReport]


class ReportLinkCheckPackets(RootModel[list[ReportLinkCheckPacket]]):
    model_config = ConfigDict(frozen=True)


class ReportLinkCheckPlant(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    kind: ReportLinkPlantKind
    true_target_report_id: str


class ReportLinkCheckKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    seed: int
    plants: list[ReportLinkCheckPlant]


class ReportLinkCheckVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    verdict: ReportLinkVerdict
    note: str


class ReportLinkCheckFlag(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    group: str
    rule: ReportLinkRule
    link_type: ReportLinkType
    source_report_id: str
    target_report_id: str
    printed_citation: str
    paragraph: str
    what_the_data_says: str
    reader_notes: list[str]


class ReportLinkCheckFlags(RootModel[list[ReportLinkCheckFlag]]):
    model_config = ConfigDict(frozen=True)

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import Session, col, delete, select

from database.report import Report
from database.report_participant import ReportParticipant
from enums import OfficeSource, ParticipantRole, ParticipantRoleSource


@dataclass(frozen=True)
class ReportParticipantRow:
    report_id: int
    ordinal: int
    role: ParticipantRole
    role_source: ParticipantRoleSource
    printed_name: str
    office_source: Optional[OfficeSource]
    speaker_id: Optional[int]


@dataclass(frozen=True)
class ReportParticipantOfficeDateRow:
    office_printed: str
    sitting_date: datetime


class CRUDReportParticipant:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, report_participants: list[ReportParticipant]) -> None:
        self.session.add_all(report_participants)
        self.session.flush()

    def get_rows_by_report_ids(
        self, report_ids: list[int]
    ) -> list[ReportParticipantRow]:
        statement = (
            select(
                ReportParticipant.report_id,
                ReportParticipant.ordinal,
                ReportParticipant.role,
                ReportParticipant.role_source,
                ReportParticipant.printed_name,
                ReportParticipant.office_source,
                ReportParticipant.speaker_id,
            )
            .where(col(ReportParticipant.report_id).in_(report_ids))
            .order_by(ReportParticipant.report_id, ReportParticipant.ordinal)
        )
        return [
            ReportParticipantRow(*row) for row in self.session.exec(statement).all()
        ]

    def get_office_printed_sitting_date_rows(
        self,
    ) -> list[ReportParticipantOfficeDateRow]:
        statement = (
            select(ReportParticipant.office_printed, Report.sitting_date)
            .join(Report, col(Report.id) == ReportParticipant.report_id)
            .where(col(ReportParticipant.office_printed).is_not(None))
            .order_by(ReportParticipant.id)
        )
        return [
            ReportParticipantOfficeDateRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def get_distinct_office_printed(self) -> list[str]:
        statement = (
            select(ReportParticipant.office_printed)
            .distinct()
            .where(col(ReportParticipant.office_printed).is_not(None))
            .order_by(ReportParticipant.office_printed)
        )
        return list(self.session.exec(statement).all())

    def get_distinct_office_printed_by_report_ids(
        self, report_ids: list[int]
    ) -> list[str]:
        statement = (
            select(ReportParticipant.office_printed)
            .distinct()
            .where(col(ReportParticipant.report_id).in_(report_ids))
            .where(col(ReportParticipant.office_printed).is_not(None))
            .order_by(ReportParticipant.office_printed)
        )
        return list(self.session.exec(statement).all())

    def delete_by_report_ids(self, report_ids: list[int]) -> int:
        statement = delete(ReportParticipant).where(
            col(ReportParticipant.report_id).in_(report_ids)
        )

        return self.session.exec(statement).rowcount

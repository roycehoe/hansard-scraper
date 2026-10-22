from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from enums import RefreshRunStatus


def _get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RefreshRun(SQLModel, table=True):
    __tablename__ = "refresh_run"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{status.value}'" for status in RefreshRunStatus) + ")",
            name="ck_refresh_run_status",
        ),
        Index("ix_refresh_run_started_at", "started_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    website_responses_added: int = 0
    sitting_date_responses_added: int = 0
    sittings_added: int = 0
    reports_added: int = 0
    speeches_added: int = 0
    speeches_linked: int = 0
    speeches_named_unlinked: int = 0
    attendances_added: int = 0
    attendances_linked: int = 0
    reports_held_without_text: int = 0
    reports_without_speech_rows: int = 0
    reports_rechecked: int = 0
    reports_changed: int = 0
    latest_sitting_date_with_text: Optional[date] = None
    figures: Optional[dict[str, object]] = Field(default=None, sa_column=Column(JSONB, nullable=True))
    halt_reason: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    failure_reason: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    started_at: datetime = Field(default_factory=_get_utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    finished_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    status: RefreshRunStatus = Field(default=RefreshRunStatus.RUNNING, sa_column=Column(Text, nullable=False))

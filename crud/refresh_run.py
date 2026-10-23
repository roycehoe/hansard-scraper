from datetime import datetime
from typing import Optional

from sqlmodel import Session, col, select

from database.refresh_run import RefreshRun
from enums import RefreshRunStatus


class CRUDRefreshRun:
    def __init__(self, session: Session):
        self.session = session

    def create(self, refresh_run: RefreshRun) -> None:
        self.session.add(refresh_run)
        self.session.commit()

    # NOTE: commits, unlike the data updates, so a run's row survives a rollback of its data
    def update(self, refresh_run: RefreshRun) -> None:
        self.session.add(refresh_run)
        self.session.commit()

    # NOTE: populate_existing, because a locked read of a row already in the session would keep its stale status
    def get_by_id_for_update(self, refresh_run_id: int) -> Optional[RefreshRun]:
        statement = (
            select(RefreshRun)
            .where(RefreshRun.id == refresh_run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self.session.exec(statement).first()

    def get_by_status_and_started_at_before(self, status: RefreshRunStatus, started_before: datetime) -> list[RefreshRun]:
        statement = (
            select(RefreshRun)
            .where(RefreshRun.status == status)
            .where(col(RefreshRun.started_at) < started_before)
        )
        return list(self.session.exec(statement).all())

    def get_by_status_and_started_at_from(self, status: RefreshRunStatus, started_from: datetime) -> list[RefreshRun]:
        statement = (
            select(RefreshRun)
            .where(RefreshRun.status == status)
            .where(col(RefreshRun.started_at) >= started_from)
        )
        return list(self.session.exec(statement).all())

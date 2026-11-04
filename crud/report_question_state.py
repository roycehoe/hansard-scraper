from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from database.report_question_state import ReportQuestionState
from enums import QuestionState


@dataclass(frozen=True)
class ReportQuestionStateRow:
    report_id: int
    state: QuestionState


class CRUDReportQuestionState:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, report_question_states: list[ReportQuestionState]) -> None:
        self.session.add_all(report_question_states)
        self.session.flush()

    def get_rows_by_report_ids(
        self, report_ids: list[int]
    ) -> list[ReportQuestionStateRow]:
        statement = select(
            ReportQuestionState.report_id, ReportQuestionState.state
        ).where(col(ReportQuestionState.report_id).in_(report_ids))
        return [
            ReportQuestionStateRow(*row) for row in self.session.exec(statement).all()
        ]

    def delete_by_report_ids(self, report_ids: list[int]) -> int:
        statement = delete(ReportQuestionState).where(
            col(ReportQuestionState.report_id).in_(report_ids)
        )

        return self.session.exec(statement).rowcount

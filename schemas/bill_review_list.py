from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import BillEra, BillReviewItemKind


class BillReviewItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: BillReviewItemKind
    era: BillEra
    bill_number: Optional[str]
    printed_title: Optional[str]
    bill_title: Optional[str]
    report_ids: list[int]
    detail: str


class BillEraDoneTests(BaseModel):
    model_config = ConfigDict(frozen=True)

    era: BillEra
    hansard_bill_count: int
    supplement_bill_number_count: int
    numbered_bill_count: int
    debate_complete_bill_count: int
    passed_bill_count: int
    outcome_resolved_bill_count: int
    unclassed_passed_bill_count: int
    unclassed_outcome_resolved_bill_count: int
    repealed_act_linked_bill_count: int
    repealed_act_only_resolved_bill_count: int
    budget_report_count: int
    budget_report_linked_count: int
    review_item_count: int


class BillReviewList(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[BillReviewItem]
    done_tests: list[BillEraDoneTests]

from dataclasses import replace
from datetime import date, datetime
from typing import Optional

import pytest

from crud.report import ReportLinkReportRow
from enums import (
    ReportLinkRule,
    ReportLinkType,
    ReportLinkUnplacedReason,
    ReportType,
    ReportVersion,
)
from exceptions import HansardHandKeptEntryError
from schemas.report_link_title_correction import ReportLinkTitleCorrection
from services.report_link import (
    SHIPPED_REPORT_LINK_RULES,
    PlannedReportLink,
    ReportLinkPlan,
    build_report_link_plan,
    get_part_number,
)
from utils.printed_citation import PrintedCitation, ResumptionHeading

_SOURCE_ID = 1
_SOURCE_REPORT_ID = "SRC#1"
_TARGET_ID = 2
_TARGET_REPORT_ID = "TGT#2"
_TITLE = "Title A"
_TARGET_DAY = date(2020, 3, 3)
_SOURCE_DAY = date(2020, 3, 10)
_LOWEST_ORDINAL = 2
_UNPLACED_ORDINAL = 4
_NEWER_SYSTEM_PART_NUMBER = 7
_OLDER_SYSTEM_PART_NUMBER = 21
_CERTAIN_RULES = (
    ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE,
    ReportLinkRule.SAME_TITLE_ON_PRINTED_DATE,
    ReportLinkRule.LAST_PART_ON_PRINTED_DATE,
)
_EXTENDED_RULES = (
    *_CERTAIN_RULES,
    ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE,
    ReportLinkRule.HAND_KEPT_TITLE_ON_PRINTED_DATE,
)


def _build_report(
    id: int,
    report_id: str,
    report_type: ReportType,
    day: date,
    title: str,
    original_title: Optional[str] = None,
    report_version: ReportVersion = ReportVersion.SPRS3,
    html_file_name: Optional[str] = None,
) -> ReportLinkReportRow:
    return ReportLinkReportRow(
        id=id,
        report_id=report_id,
        report_type=report_type,
        report_version=report_version,
        sitting_date=datetime(day.year, day.month, day.day),
        original_title=title if original_title is None else original_title,
        title=title,
        html_file_name=html_file_name,
    )


def _build_source(
    report_type: ReportType = ReportType.ORAL_ANSWER, day: date = _SOURCE_DAY
) -> ReportLinkReportRow:
    return _build_report(
        _SOURCE_ID, _SOURCE_REPORT_ID, report_type, day, "Source title"
    )


def _build_target(
    report_type: ReportType = ReportType.ORAL_ANSWER,
    title: str = _TITLE,
    day: date = _TARGET_DAY,
) -> ReportLinkReportRow:
    return _build_report(_TARGET_ID, _TARGET_REPORT_ID, report_type, day, title)


def _build_citation(
    printed_title: Optional[str] = _TITLE,
    printed_date: Optional[date] = _TARGET_DAY,
    ordinal: int = 1,
    report_id: int = _SOURCE_ID,
) -> PrintedCitation:
    return PrintedCitation(
        report_id=report_id,
        ordinal=ordinal,
        printed_citation=f"{printed_title}, {printed_date}",
        printed_title=printed_title,
        printed_date=printed_date,
        paragraph=f"paragraph {ordinal}",
    )


def _build_heading(
    printed_date: Optional[date] = _TARGET_DAY, ordinal: int = 1
) -> ResumptionHeading:
    return ResumptionHeading(
        report_id=_SOURCE_ID,
        ordinal=ordinal,
        printed_citation=f"Resumption of debate on {printed_date}",
        printed_date=printed_date,
        paragraph=f"heading {ordinal}",
    )


def _build_title_correction(
    report_id: str, printed_title: str, corrected_title: str
) -> ReportLinkTitleCorrection:
    return ReportLinkTitleCorrection(
        report_id=report_id,
        printed_title=printed_title,
        corrected_title=corrected_title,
        reason="A reason.",
    )


def _build_plan(
    report_rows: list[ReportLinkReportRow],
    printed_citations: Optional[list[PrintedCitation]] = None,
    resumption_headings: Optional[list[ResumptionHeading]] = None,
    title_corrections: Optional[list[ReportLinkTitleCorrection]] = None,
    shipped_rules: tuple[ReportLinkRule, ...] = SHIPPED_REPORT_LINK_RULES,
) -> ReportLinkPlan:
    return build_report_link_plan(
        [] if printed_citations is None else printed_citations,
        [] if resumption_headings is None else resumption_headings,
        report_rows,
        [] if title_corrections is None else title_corrections,
        shipped_rules,
    )


def _build_part(
    id: int, part_number: int, title: str = "Debate", **fields: object
) -> ReportLinkReportRow:
    part = _build_report(
        id,
        f"PART#{part_number}",
        ReportType.MOTION,
        _TARGET_DAY,
        title,
        html_file_name=f"{part_number}_debate.html",
    )
    return replace(part, **fields)


def _get_only_link(plan: ReportLinkPlan) -> PlannedReportLink:
    assert len(plan.planned_links) == 1
    return plan.planned_links[0]


def _get_only_reason(plan: ReportLinkPlan) -> ReportLinkUnplacedReason:
    assert plan.planned_links == []
    assert len(plan.unplaced_citations) == 1
    return plan.unplaced_citations[0].reason


def test_one_exact_target_links_under_the_printed_title_rule() -> None:
    plan = _build_plan([_build_source(), _build_target()], [_build_citation()])

    planned_link = _get_only_link(plan)
    assert planned_link.link_type == ReportLinkType.REPLY
    assert planned_link.rule == ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE
    assert planned_link.source_report_id == _SOURCE_REPORT_ID
    assert planned_link.target_report_id == _TARGET_REPORT_ID
    assert plan.unplaced_citations == []


def test_two_exact_targets_give_several_reports_with_title() -> None:
    second_target = _build_report(
        3, "TGT#3", ReportType.ORAL_ANSWER, _TARGET_DAY, _TITLE
    )

    plan = _build_plan(
        [_build_source(), _build_target(), second_target], [_build_citation()]
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.SEVERAL_REPORTS_WITH_TITLE


def test_no_exact_target_gives_no_report_with_title() -> None:
    plan = _build_plan(
        [_build_source(), _build_target(title="Other title")], [_build_citation()]
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.NO_REPORT_WITH_TITLE


def test_no_report_on_the_printed_date_gives_no_sitting() -> None:
    plan = _build_plan([_build_source()], [_build_citation()])

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.NO_SITTING_ON_PRINTED_DATE


@pytest.mark.parametrize(
    ("printed_title", "printed_date"),
    [(None, _TARGET_DAY), (_TITLE, None)],
)
def test_a_citation_without_title_or_date_is_unplaced(
    printed_title: Optional[str], printed_date: Optional[date]
) -> None:
    plan = _build_plan(
        [_build_source(), _build_target()],
        [_build_citation(printed_title, printed_date)],
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.NO_TITLE_OR_DATE


def test_a_citation_naming_its_own_report_is_not_linked_to_it() -> None:
    source = _build_source()

    plan = _build_plan(
        [source], [_build_citation(source.original_title, _SOURCE_DAY)]
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.NO_REPORT_WITH_TITLE


def test_citation_title_compares_to_original_title_with_whitespace_collapsed() -> None:
    target = replace(_build_target(title="Other title"), original_title="Title  A\n")

    plan = _build_plan([_build_source(), target], [_build_citation()])

    assert _get_only_link(plan).target_report_id == _TARGET_REPORT_ID


def test_a_clarification_dated_after_the_target_is_a_correction() -> None:
    plan = _build_plan(
        [_build_source(ReportType.CLARIFICATION), _build_target()],
        [_build_citation()],
    )

    assert _get_only_link(plan).link_type == ReportLinkType.CORRECTION


def test_an_answer_citing_a_later_clarification_is_a_correction() -> None:
    plan = _build_plan(
        [
            _build_source(ReportType.ORAL_ANSWER, _TARGET_DAY),
            _build_target(ReportType.CLARIFICATION, day=_SOURCE_DAY),
        ],
        [_build_citation(printed_date=_SOURCE_DAY)],
    )

    assert _get_only_link(plan).link_type == ReportLinkType.CORRECTION


def test_a_written_statement_correcting_a_clarification_is_a_correction() -> None:
    plan = _build_plan(
        [
            _build_source(ReportType.WRITTEN_STATEMENT),
            _build_target(ReportType.CLARIFICATION),
        ],
        [_build_citation()],
    )

    assert _get_only_link(plan).link_type == ReportLinkType.CORRECTION


def test_an_answer_citing_an_earlier_clarification_is_a_reply() -> None:
    plan = _build_plan(
        [
            _build_source(ReportType.WRITTEN_ANSWER, date(2020, 7, 5)),
            _build_target(ReportType.CLARIFICATION, day=date(2020, 5, 8)),
        ],
        [_build_citation(printed_date=date(2020, 5, 8))],
    )

    assert _get_only_link(plan).link_type == ReportLinkType.REPLY


def test_a_clarification_citing_a_budget_report_is_a_correction() -> None:
    plan = _build_plan(
        [_build_source(ReportType.CLARIFICATION), _build_target(ReportType.BUDGET)],
        [_build_citation()],
    )

    assert _get_only_link(plan).link_type == ReportLinkType.CORRECTION


def test_a_motion_citing_an_answer_is_not_an_answer_source() -> None:
    plan = _build_plan(
        [_build_source(ReportType.MOTION), _build_target()], [_build_citation()]
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.SOURCE_NOT_AN_ANSWER


def test_duplicate_citations_keep_the_lowest_ordinal() -> None:
    plan = _build_plan(
        [_build_source(), _build_target()],
        [_build_citation(ordinal=_LOWEST_ORDINAL), _build_citation(ordinal=5)],
    )

    planned_link = _get_only_link(plan)
    assert planned_link.ordinal == _LOWEST_ORDINAL
    assert planned_link.paragraph == f"paragraph {_LOWEST_ORDINAL}"


def test_a_pair_printed_from_both_sides_is_two_links() -> None:
    source = _build_source()
    target = _build_target()
    reverse_citation = _build_citation(
        source.original_title, _SOURCE_DAY, report_id=_TARGET_ID
    )

    plan = _build_plan(
        [source, target],
        [_build_citation(), reverse_citation],
    )

    assert {
        (planned_link.source_report_id, planned_link.target_report_id)
        for planned_link in plan.planned_links
    } == {
        (_SOURCE_REPORT_ID, _TARGET_REPORT_ID),
        (_TARGET_REPORT_ID, _SOURCE_REPORT_ID),
    }


def test_one_report_with_the_same_title_is_a_continuation() -> None:
    plan = _build_plan(
        [
            _build_report(
                _SOURCE_ID, _SOURCE_REPORT_ID, ReportType.MOTION, _SOURCE_DAY, "Debate"
            ),
            _build_part(_TARGET_ID, 1),
        ],
        resumption_headings=[_build_heading()],
    )

    planned_link = _get_only_link(plan)
    assert planned_link.link_type == ReportLinkType.CONTINUATION
    assert planned_link.rule == ReportLinkRule.SAME_TITLE_ON_PRINTED_DATE
    assert planned_link.paragraph == "heading 1"


def _build_debate_source() -> ReportLinkReportRow:
    return _build_report(
        _SOURCE_ID, _SOURCE_REPORT_ID, ReportType.MOTION, _SOURCE_DAY, "Debate"
    )


def test_several_newer_system_parts_take_the_highest_part_number() -> None:
    plan = _build_plan(
        [
            _build_debate_source(),
            _build_part(2, 3, report_id="PART#3"),
            _build_part(3, 11, report_id="PART#11"),
        ],
        resumption_headings=[_build_heading()],
    )

    planned_link = _get_only_link(plan)
    assert planned_link.target_report_id == "PART#11"
    assert planned_link.rule == ReportLinkRule.LAST_PART_ON_PRINTED_DATE


def test_several_older_system_parts_take_the_highest_leading_number() -> None:
    plan = _build_plan(
        [
            _build_debate_source(),
            _build_part(
                2,
                3,
                report_id="OLD-A",
                report_version=ReportVersion.SPRS2,
                html_file_name="3_debate.html",
            ),
            _build_part(
                3,
                12,
                report_id="OLD-B",
                report_version=ReportVersion.SPRS2,
                html_file_name="12_debate.html",
            ),
        ],
        resumption_headings=[_build_heading()],
    )

    assert _get_only_link(plan).target_report_id == "OLD-B"


def test_mixed_newer_system_types_give_no_link() -> None:
    plan = _build_plan(
        [
            _build_debate_source(),
            _build_part(2, 1),
            _build_part(3, 2, report_type=ReportType.BILL),
        ],
        resumption_headings=[_build_heading()],
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.MIXED_REPORT_TYPES_IN_PARTS


def test_a_missing_part_number_gives_no_link() -> None:
    plan = _build_plan(
        [
            _build_debate_source(),
            _build_part(
                2,
                1,
                report_id="OLD-A",
                report_version=ReportVersion.SPRS2,
                html_file_name=None,
            ),
            _build_part(
                3,
                2,
                report_id="OLD-B",
                report_version=ReportVersion.SPRS2,
                html_file_name="2_debate.html",
            ),
        ],
        resumption_headings=[_build_heading()],
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.NO_PART_NUMBER


def test_a_tied_part_number_gives_no_link() -> None:
    plan = _build_plan(
        [
            _build_debate_source(),
            _build_part(2, 4, report_id="PART-A#4"),
            _build_part(3, 4, report_id="PART-B#4"),
        ],
        resumption_headings=[_build_heading()],
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.TIED_PART_NUMBER


def test_a_printed_date_on_or_after_the_source_is_not_a_continuation() -> None:
    plan = _build_plan(
        [_build_debate_source(), _build_part(_TARGET_ID, 1)],
        resumption_headings=[_build_heading(_SOURCE_DAY)],
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.PRINTED_DATE_NOT_BEFORE_SOURCE


def test_an_unplaced_heading_carries_the_source_title_and_its_paragraph() -> None:
    plan = _build_plan(
        [_build_debate_source()], resumption_headings=[_build_heading()]
    )

    unplaced_citation = plan.unplaced_citations[0]
    assert unplaced_citation.reason == ReportLinkUnplacedReason.NO_SITTING_ON_PRINTED_DATE
    assert unplaced_citation.printed_title == "Debate"
    assert unplaced_citation.paragraph == "heading 1"
    assert unplaced_citation.source_report_id == _SOURCE_REPORT_ID


def test_continuation_compares_title_not_original_title() -> None:
    part = replace(_build_part(_TARGET_ID, 1), original_title="Different original")

    plan = _build_plan(
        [_build_debate_source(), part], resumption_headings=[_build_heading()]
    )

    assert _get_only_link(plan).target_report_id == "PART#1"


def test_key_rule_links_a_title_that_differs_in_case_and_punctuation() -> None:
    target = replace(_build_target(title="Other"), original_title="TITLE, A")

    certain_plan = _build_plan(
        [_build_source(), target], [_build_citation()], shipped_rules=_CERTAIN_RULES
    )
    extended_plan = _build_plan(
        [_build_source(), target], [_build_citation()], shipped_rules=_EXTENDED_RULES
    )

    assert _get_only_reason(certain_plan) == ReportLinkUnplacedReason.NO_REPORT_WITH_TITLE
    assert _get_only_link(extended_plan).rule == ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE


def test_key_rule_is_skipped_when_exact_candidates_are_several() -> None:
    first_target = _build_target()
    second_target = _build_report(
        3, "TGT#3", ReportType.ORAL_ANSWER, _TARGET_DAY, _TITLE
    )
    key_target = replace(
        _build_report(4, "TGT#4", ReportType.ORAL_ANSWER, _TARGET_DAY, "Other"),
        original_title="title a",
    )

    plan = _build_plan(
        [_build_source(), first_target, second_target, key_target],
        [_build_citation()],
        shipped_rules=_EXTENDED_RULES,
    )

    assert _get_only_reason(plan) == ReportLinkUnplacedReason.SEVERAL_REPORTS_WITH_TITLE


def test_key_rule_takes_the_last_of_several_parts_and_keeps_its_name() -> None:
    plan = _build_plan(
        [
            _build_debate_source(),
            _build_part(2, 3, title="DEBATE.", report_id="PART#3"),
            _build_part(3, 11, title="debate", report_id="PART#11"),
        ],
        resumption_headings=[_build_heading()],
        shipped_rules=_EXTENDED_RULES,
    )

    planned_link = _get_only_link(plan)
    assert planned_link.target_report_id == "PART#11"
    assert planned_link.rule == ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE


def test_a_title_variant_on_the_printed_date_leaves_no_certain_continuation() -> None:
    report_rows = [
        _build_debate_source(),
        _build_part(2, 3, report_id="PART#3"),
        _build_part(3, 11, title="Debate.", report_id="PART#11"),
    ]

    certain_plan = _build_plan(
        report_rows,
        resumption_headings=[_build_heading()],
        shipped_rules=_CERTAIN_RULES,
    )
    extended_plan = _build_plan(
        report_rows,
        resumption_headings=[_build_heading()],
        shipped_rules=_EXTENDED_RULES,
    )

    assert _get_only_reason(certain_plan) == ReportLinkUnplacedReason.SEVERAL_REPORTS_WITH_TITLE
    planned_link = _get_only_link(extended_plan)
    assert planned_link.target_report_id == "PART#11"
    assert planned_link.rule == ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE


def test_hand_kept_entry_links_when_the_exact_title_found_several() -> None:
    first_target = _build_target()
    second_target = _build_report(
        3, "TGT#3", ReportType.ORAL_ANSWER, _TARGET_DAY, _TITLE
    )
    corrected_target = _build_report(
        4, "TGT#4", ReportType.ORAL_ANSWER, _TARGET_DAY, "Corrected title"
    )

    plan = _build_plan(
        [_build_source(), first_target, second_target, corrected_target],
        [_build_citation()],
        title_corrections=[
            _build_title_correction(_SOURCE_REPORT_ID, _TITLE, "Corrected title")
        ],
        shipped_rules=_EXTENDED_RULES,
    )

    planned_link = _get_only_link(plan)
    assert planned_link.target_report_id == "TGT#4"
    assert planned_link.rule == ReportLinkRule.HAND_KEPT_TITLE_ON_PRINTED_DATE


def test_hand_kept_continuation_with_two_corrected_reports_gets_no_link() -> None:
    source = _build_report(
        _SOURCE_ID, _SOURCE_REPORT_ID, ReportType.MOTION, _SOURCE_DAY, "Misspelt"
    )

    plan = _build_plan(
        [
            source,
            _build_part(2, 1, title="Fixed", report_id="PART#1"),
            _build_part(3, 2, title="Fixed", report_id="PART#2"),
        ],
        resumption_headings=[_build_heading()],
        title_corrections=[
            _build_title_correction(_SOURCE_REPORT_ID, "Misspelt", "Fixed")
        ],
        shipped_rules=_EXTENDED_RULES,
    )

    assert plan.planned_links == []
    assert len(plan.unplaced_citations) == 1


def test_a_hand_kept_entry_the_report_no_longer_prints_raises() -> None:
    with pytest.raises(HansardHandKeptEntryError) as error:
        _build_plan(
            [_build_source(), _build_target()],
            [_build_citation()],
            title_corrections=[
                _build_title_correction(_SOURCE_REPORT_ID, "Not printed", "Fixed")
            ],
            shipped_rules=_EXTENDED_RULES,
        )

    assert "report_link_title_corrections.json" in str(error.value)
    assert "Not printed" in str(error.value)


def test_an_unplaced_citation_carries_its_paragraph() -> None:
    plan = _build_plan([_build_source()], [_build_citation(ordinal=_UNPLACED_ORDINAL)])

    unplaced_citation = plan.unplaced_citations[0]
    assert unplaced_citation.paragraph == f"paragraph {_UNPLACED_ORDINAL}"
    assert unplaced_citation.ordinal == _UNPLACED_ORDINAL


def test_the_certain_rules_do_not_fire_the_looser_rules() -> None:
    target = replace(_build_target(title="Other"), original_title="TITLE, A")

    plan = _build_plan(
        [_build_source(), target],
        [_build_citation()],
        title_corrections=[
            _build_title_correction(_SOURCE_REPORT_ID, _TITLE, "Other")
        ],
        shipped_rules=_CERTAIN_RULES,
    )

    assert plan.planned_links == []


def test_a_repeat_call_gives_an_equal_plan() -> None:
    report_rows = [_build_source(), _build_target()]
    printed_citations = [_build_citation(), _build_citation(ordinal=2)]

    assert _build_plan(report_rows, printed_citations) == _build_plan(
        report_rows, printed_citations
    )


def test_planned_links_are_sorted_by_source_target_and_type() -> None:
    other_target = _build_report(
        3, "AAA#3", ReportType.ORAL_ANSWER, date(2020, 3, 4), "Title B"
    )

    plan = _build_plan(
        [_build_source(), _build_target(), other_target],
        [
            _build_citation(),
            _build_citation("Title B", date(2020, 3, 4), ordinal=2),
        ],
    )

    assert [planned_link.target_report_id for planned_link in plan.planned_links] == [
        "AAA#3",
        _TARGET_REPORT_ID,
    ]


def test_get_part_number_reads_the_trailing_number_of_a_newer_system_id() -> None:
    assert get_part_number(_build_part(1, _NEWER_SYSTEM_PART_NUMBER)) == (
        _NEWER_SYSTEM_PART_NUMBER
    )


def test_get_part_number_reads_the_leading_number_of_an_older_system_file() -> None:
    older_part = _build_part(
        1,
        1,
        report_version=ReportVersion.SPRS2,
        html_file_name=f"{_OLDER_SYSTEM_PART_NUMBER}_debate.html",
    )

    assert get_part_number(older_part) == _OLDER_SYSTEM_PART_NUMBER

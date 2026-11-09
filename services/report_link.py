import re
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence, Union

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
from utils.printed_citation import PrintedCitation, ResumptionHeading
from utils.title_key import get_title_key

SHIPPED_REPORT_LINK_RULES = (
    ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE,
    ReportLinkRule.SAME_TITLE_ON_PRINTED_DATE,
    ReportLinkRule.LAST_PART_ON_PRINTED_DATE,
)
_NEWER_SYSTEM_PART_NUMBER_RE = re.compile(r"(\d+)#?$")
_OLDER_SYSTEM_PART_NUMBER_RE = re.compile(r"^(\d+)")


@dataclass(frozen=True)
class PlannedReportLink:
    link_type: ReportLinkType
    rule: ReportLinkRule
    printed_citation: str
    source_report_id: str
    target_report_id: str
    ordinal: int
    paragraph: str


@dataclass(frozen=True)
class UnplacedCitation:
    source_report_id: str
    ordinal: int
    printed_citation: str
    printed_title: Optional[str]
    printed_date: Optional[date]
    reason: ReportLinkUnplacedReason
    paragraph: str


@dataclass(frozen=True)
class ReportLinkPlan:
    planned_links: list[PlannedReportLink]
    unplaced_citations: list[UnplacedCitation]


@dataclass(frozen=True)
class _RuleMatch:
    target: ReportLinkReportRow
    rule: ReportLinkRule


def _is_correction_report(report_type: str) -> bool:
    return (
        report_type == ReportType.CLARIFICATION
        or report_type == ReportType.WRITTEN_STATEMENT
    )


def _is_answer_report(report_type: str) -> bool:
    return (
        report_type == ReportType.ORAL_ANSWER
        or report_type == ReportType.WRITTEN_ANSWER
        or report_type == ReportType.WRITTEN_ANSWER_NOT_AVAILABLE
    )


def _get_collapsed_title(title: str) -> str:
    return " ".join(title.split())


def get_part_number(report_row: ReportLinkReportRow) -> Optional[int]:
    if report_row.report_version == ReportVersion.SPRS3:
        part_match = _NEWER_SYSTEM_PART_NUMBER_RE.search(report_row.report_id)
    else:
        part_match = _OLDER_SYSTEM_PART_NUMBER_RE.match(
            report_row.html_file_name or ""
        )
    return None if part_match is None else int(part_match.group(1))


def _get_part_match(
    parts: list[ReportLinkReportRow], rule: ReportLinkRule
) -> Union[_RuleMatch, ReportLinkUnplacedReason]:
    if len(parts) == 1:
        return _RuleMatch(parts[0], rule)
    if (
        parts[0].report_version == ReportVersion.SPRS3
        and len({part.report_type for part in parts}) > 1
    ):
        return ReportLinkUnplacedReason.MIXED_REPORT_TYPES_IN_PARTS
    part_numbers = [get_part_number(part) for part in parts]
    known_part_numbers = [
        part_number for part_number in part_numbers if part_number is not None
    ]
    if len(known_part_numbers) != len(parts):
        return ReportLinkUnplacedReason.NO_PART_NUMBER
    highest_part_number = max(known_part_numbers)
    if known_part_numbers.count(highest_part_number) > 1:
        return ReportLinkUnplacedReason.TIED_PART_NUMBER
    return _RuleMatch(parts[known_part_numbers.index(highest_part_number)], rule)


def _get_citation_match(
    printed_citation: PrintedCitation,
    source: ReportLinkReportRow,
    sitting_day_to_report_rows: dict[date, list[ReportLinkReportRow]],
    report_title_to_corrected_title: dict[tuple[str, str], str],
    shipped_rules: Sequence[ReportLinkRule],
) -> Union[_RuleMatch, ReportLinkUnplacedReason]:
    printed_title = printed_citation.printed_title
    if printed_title is None:
        return ReportLinkUnplacedReason.NO_TITLE_OR_DATE
    if printed_citation.printed_date is None:
        return ReportLinkUnplacedReason.NO_TITLE_OR_DATE
    day_report_rows = sitting_day_to_report_rows.get(printed_citation.printed_date)
    if day_report_rows is None:
        return ReportLinkUnplacedReason.NO_SITTING_ON_PRINTED_DATE
    candidates = [
        report_row for report_row in day_report_rows if report_row.id != source.id
    ]
    exact_candidates = [
        report_row
        for report_row in candidates
        if _get_collapsed_title(report_row.original_title) == printed_title
    ]
    if (
        len(exact_candidates) == 1
        and ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE in shipped_rules
    ):
        return _RuleMatch(
            exact_candidates[0], ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE
        )
    key_candidates = [
        report_row
        for report_row in candidates
        if get_title_key(report_row.original_title) == get_title_key(printed_title)
    ]
    if (
        not exact_candidates
        and len(key_candidates) == 1
        and ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE in shipped_rules
    ):
        return _RuleMatch(key_candidates[0], ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE)
    corrected_title = report_title_to_corrected_title.get((source.report_id, printed_title))
    if (
        corrected_title is not None
        and ReportLinkRule.HAND_KEPT_TITLE_ON_PRINTED_DATE in shipped_rules
    ):
        corrected_candidates = [
            report_row
            for report_row in candidates
            if _get_collapsed_title(report_row.original_title)
            == _get_collapsed_title(corrected_title)
        ]
        if len(corrected_candidates) == 1:
            return _RuleMatch(
                corrected_candidates[0], ReportLinkRule.HAND_KEPT_TITLE_ON_PRINTED_DATE
            )
    if len(exact_candidates) > 1:
        return ReportLinkUnplacedReason.SEVERAL_REPORTS_WITH_TITLE
    if (
        len(key_candidates) > 1
        and ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE in shipped_rules
    ):
        return ReportLinkUnplacedReason.SEVERAL_REPORTS_WITH_TITLE
    return ReportLinkUnplacedReason.NO_REPORT_WITH_TITLE


def _get_continuation_match(
    heading: ResumptionHeading,
    source: ReportLinkReportRow,
    sitting_day_to_report_rows: dict[date, list[ReportLinkReportRow]],
    report_title_to_corrected_title: dict[tuple[str, str], str],
    shipped_rules: Sequence[ReportLinkRule],
) -> Union[_RuleMatch, ReportLinkUnplacedReason]:
    if heading.printed_date is None:
        return ReportLinkUnplacedReason.NO_TITLE_OR_DATE
    if heading.printed_date >= source.sitting_date.date():
        return ReportLinkUnplacedReason.PRINTED_DATE_NOT_BEFORE_SOURCE
    day_report_rows = sitting_day_to_report_rows.get(heading.printed_date)
    if day_report_rows is None:
        return ReportLinkUnplacedReason.NO_SITTING_ON_PRINTED_DATE
    same_title = [
        report_row for report_row in day_report_rows if report_row.title == source.title
    ]
    if (
        len(same_title) == 1
        and ReportLinkRule.SAME_TITLE_ON_PRINTED_DATE in shipped_rules
    ):
        return _RuleMatch(same_title[0], ReportLinkRule.SAME_TITLE_ON_PRINTED_DATE)
    if (
        len(same_title) > 1
        and ReportLinkRule.LAST_PART_ON_PRINTED_DATE in shipped_rules
    ):
        return _get_part_match(same_title, ReportLinkRule.LAST_PART_ON_PRINTED_DATE)
    key_titled = [
        report_row
        for report_row in day_report_rows
        if get_title_key(report_row.title) == get_title_key(source.title)
    ]
    if (
        not same_title
        and key_titled
        and ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE in shipped_rules
    ):
        return _get_part_match(key_titled, ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE)
    corrected_title = report_title_to_corrected_title.get((source.report_id, source.title))
    if (
        corrected_title is not None
        and ReportLinkRule.HAND_KEPT_TITLE_ON_PRINTED_DATE in shipped_rules
    ):
        corrected_titled = [
            report_row
            for report_row in day_report_rows
            if _get_collapsed_title(report_row.title)
            == _get_collapsed_title(corrected_title)
        ]
        if len(corrected_titled) == 1:
            return _RuleMatch(
                corrected_titled[0], ReportLinkRule.HAND_KEPT_TITLE_ON_PRINTED_DATE
            )
    if len(same_title) > 1:
        return ReportLinkUnplacedReason.SEVERAL_REPORTS_WITH_TITLE
    return ReportLinkUnplacedReason.NO_REPORT_WITH_TITLE


def _get_citation_link_type(
    source: ReportLinkReportRow, target: ReportLinkReportRow
) -> Optional[ReportLinkType]:
    is_source_correction = _is_correction_report(source.report_type)
    if is_source_correction and source.sitting_date >= target.sitting_date:
        return ReportLinkType.CORRECTION
    if (
        not is_source_correction
        and _is_correction_report(target.report_type)
        and target.sitting_date >= source.sitting_date
    ):
        return ReportLinkType.CORRECTION
    if _is_answer_report(source.report_type):
        return ReportLinkType.REPLY
    return None


def _get_validated_report_title_to_corrected_title(
    title_corrections: list[ReportLinkTitleCorrection],
    printed_citations: list[PrintedCitation],
    resumption_headings: list[ResumptionHeading],
    id_to_report_row: dict[int, ReportLinkReportRow],
) -> dict[tuple[str, str], str]:
    printed_titles = {
        (id_to_report_row[printed_citation.report_id].report_id, printed_citation.printed_title)
        for printed_citation in printed_citations
        if printed_citation.printed_title is not None
    }
    printed_titles |= {
        (
            id_to_report_row[resumption_heading.report_id].report_id,
            id_to_report_row[resumption_heading.report_id].title,
        )
        for resumption_heading in resumption_headings
    }
    for title_correction in title_corrections:
        if (
            title_correction.report_id,
            title_correction.printed_title,
        ) not in printed_titles:
            raise HansardHandKeptEntryError(
                f"report_link_title_corrections.json: report {title_correction.report_id} "
                f"does not print {title_correction.printed_title!r}"
            )
    return {
        (title_correction.report_id, title_correction.printed_title): (
            title_correction.corrected_title
        )
        for title_correction in title_corrections
    }


def _build_unplaced_citation(
    source: ReportLinkReportRow,
    printed_citation: PrintedCitation,
    reason: ReportLinkUnplacedReason,
) -> UnplacedCitation:
    return UnplacedCitation(
        source.report_id,
        printed_citation.ordinal,
        printed_citation.printed_citation,
        printed_citation.printed_title,
        printed_citation.printed_date,
        reason,
        printed_citation.paragraph,
    )


def build_report_link_plan(
    printed_citations: list[PrintedCitation],
    resumption_headings: list[ResumptionHeading],
    report_rows: list[ReportLinkReportRow],
    title_corrections: list[ReportLinkTitleCorrection],
    shipped_rules: Sequence[ReportLinkRule],
) -> ReportLinkPlan:
    id_to_report_row = {report_row.id: report_row for report_row in report_rows}
    sitting_day_to_report_rows: dict[date, list[ReportLinkReportRow]] = {}
    for report_row in report_rows:
        sitting_day_to_report_rows.setdefault(
            report_row.sitting_date.date(), []
        ).append(report_row)
    report_title_to_corrected_title = _get_validated_report_title_to_corrected_title(
        title_corrections, printed_citations, resumption_headings, id_to_report_row
    )
    key_to_planned_link: dict[
        tuple[str, str, ReportLinkType], PlannedReportLink
    ] = {}
    unplaced_citations: list[UnplacedCitation] = []
    for printed_citation in printed_citations:
        source = id_to_report_row[printed_citation.report_id]
        citation_match = _get_citation_match(
            printed_citation,
            source,
            sitting_day_to_report_rows,
            report_title_to_corrected_title,
            shipped_rules,
        )
        if isinstance(citation_match, ReportLinkUnplacedReason):
            unplaced_citations.append(
                _build_unplaced_citation(source, printed_citation, citation_match)
            )
            continue
        link_type = _get_citation_link_type(source, citation_match.target)
        if link_type is None:
            unplaced_citations.append(
                _build_unplaced_citation(
                    source,
                    printed_citation,
                    ReportLinkUnplacedReason.SOURCE_NOT_AN_ANSWER,
                )
            )
            continue
        key_to_planned_link.setdefault(
            (source.report_id, citation_match.target.report_id, link_type),
            PlannedReportLink(
                link_type,
                citation_match.rule,
                printed_citation.printed_citation,
                source.report_id,
                citation_match.target.report_id,
                printed_citation.ordinal,
                printed_citation.paragraph,
            ),
        )
    for resumption_heading in resumption_headings:
        source = id_to_report_row[resumption_heading.report_id]
        heading_match = _get_continuation_match(
            resumption_heading,
            source,
            sitting_day_to_report_rows,
            report_title_to_corrected_title,
            shipped_rules,
        )
        if isinstance(heading_match, ReportLinkUnplacedReason):
            unplaced_citations.append(
                UnplacedCitation(
                    source.report_id,
                    resumption_heading.ordinal,
                    resumption_heading.printed_citation,
                    source.title,
                    resumption_heading.printed_date,
                    heading_match,
                    resumption_heading.paragraph,
                )
            )
            continue
        key_to_planned_link.setdefault(
            (source.report_id, heading_match.target.report_id, ReportLinkType.CONTINUATION),
            PlannedReportLink(
                ReportLinkType.CONTINUATION,
                heading_match.rule,
                resumption_heading.printed_citation,
                source.report_id,
                heading_match.target.report_id,
                resumption_heading.ordinal,
                resumption_heading.paragraph,
            ),
        )
    return ReportLinkPlan(
        sorted(
            key_to_planned_link.values(),
            key=lambda planned_link: (
                planned_link.source_report_id,
                planned_link.target_report_id,
                planned_link.link_type,
            ),
        ),
        unplaced_citations,
    )

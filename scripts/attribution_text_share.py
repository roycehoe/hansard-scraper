import argparse
from collections import Counter
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from database.init import engine
from logs import logger
from populate.attribution_figures import get_attribution_figures
from services.attribution import (
    ADR_EXCLUDED_CATEGORY,
    LINKED_CATEGORY,
    NAMED_UNLINKED_CATEGORY,
    NO_SPEAKER_CATEGORY,
    ReportTypeFigures,
)

_PERCENT = 100
_NO_DENOMINATOR = "n/a"


def _get_share(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return f"{numerator} / {denominator} = {_NO_DENOMINATOR}"
    return f"{numerator} / {denominator} = {_PERCENT * numerator / denominator:.2f}%"


def _log_report_type_figures(report_type: str, figures: ReportTypeFigures) -> None:
    linked_row_count = figures.category_to_row_count[LINKED_CATEGORY]
    adr_denominator = linked_row_count + figures.category_to_row_count[NAMED_UNLINKED_CATEGORY]
    reports_with_rows = figures.report_count - figures.zero_row_report_count
    logger.info(f"  {report_type}: {figures.report_count} reports")
    logger.info(f"    1. ADR 0001 rate:  {_get_share(linked_row_count, adr_denominator)}")
    logger.info(f"    2. All-rows rate:  {_get_share(linked_row_count, sum(figures.category_to_row_count.values()))}")
    logger.info(f"    3. Text share:     {_get_share(figures.category_to_character_count[LINKED_CATEGORY], figures.body_total)} chars")
    logger.info(f"    Zero-row reports:  {_get_share(figures.zero_row_report_count, figures.report_count)}")
    logger.info(f"    Single-speaker collapses, reports: {_get_share(figures.collapse_report_count, reports_with_rows)}")
    logger.info(f"    Single-speaker collapses, body chars: {_get_share(figures.collapse_character_count, figures.body_total)}")


def _log_rates(category_to_row_count: Counter[str], category_to_character_count: Counter[str], body_total: int) -> None:
    rows_total = sum(category_to_row_count.values())
    adr_denominator = category_to_row_count[LINKED_CATEGORY] + category_to_row_count[NAMED_UNLINKED_CATEGORY]
    logger.info(f"1. ADR 0001 rate:  {category_to_row_count[LINKED_CATEGORY]} / {adr_denominator} = "
          f"{_PERCENT * category_to_row_count[LINKED_CATEGORY] / adr_denominator:.2f}%")
    logger.info(f"2. All-rows rate:  {category_to_row_count[LINKED_CATEGORY]} / {rows_total} = {_PERCENT * category_to_row_count[LINKED_CATEGORY] / rows_total:.2f}%")
    logger.info(f"3. Text share:     {category_to_character_count[LINKED_CATEGORY]} / {body_total} chars = {_PERCENT * category_to_character_count[LINKED_CATEGORY] / body_total:.2f}%")


def main(output_path: Optional[Path]) -> None:
    if output_path is not None:
        logger.add(output_path, format="{message}", mode="w")
    with Session(engine) as session:
        attribution_figures = get_attribution_figures(session)

    headline_figures, *reported_figures = attribution_figures.groups
    category_to_row_count = headline_figures.category_to_row_count
    category_to_character_count = headline_figures.category_to_character_count
    body_total = headline_figures.body_total
    body_in_zero_row_reports = headline_figures.body_in_zero_row_reports
    stored_character_count = sum(category_to_character_count.values())

    logger.info(f"{headline_figures.group}: {headline_figures.report_count} reports with markdown, "
          f"{headline_figures.reports_with_rows_count} with speech rows, {sum(category_to_row_count.values())} speech rows")
    _log_rates(category_to_row_count, category_to_character_count, body_total)
    logger.info("Where the body text goes (chars, share of body):")
    for label, character_count in (
        ("linked rows", category_to_character_count[LINKED_CATEGORY]),
        ("named but unlinked rows", category_to_character_count[NAMED_UNLINKED_CATEGORY]),
        ("ADR-excluded rows (hon. Members, stage directions)", category_to_character_count[ADR_EXCLUDED_CATEGORY]),
        ("rows with no speaker", category_to_character_count[NO_SPEAKER_CATEGORY]),
        ("reports with no rows", body_in_zero_row_reports),
        ("dropped inside reports with rows (preamble, headings, labels)",
         body_total - stored_character_count - body_in_zero_row_reports),
    ):
        logger.info(f"  {label:<64} {character_count:>12} {_PERCENT * character_count / body_total:6.2f}%")
    logger.info(f"Rows by category: {dict(category_to_row_count)}")
    for group_figures in reported_figures:
        logger.info(f"{group_figures.group}, beside the headline:")
        _log_rates(group_figures.category_to_row_count, group_figures.category_to_character_count, group_figures.body_total)

    for group_figures in attribution_figures.groups:
        logger.info(f"{group_figures.group}, by report type:")
        for report_type in sorted(group_figures.report_type_to_figures):
            _log_report_type_figures(report_type, group_figures.report_type_to_figures[report_type])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The three attribution numbers, by Parliament group and by report type")
    parser.add_argument("--output", type=Path, help="also write the log lines to this file, such as docs/figures/2026-10-17-round8.txt")
    main(parser.parse_args().output)

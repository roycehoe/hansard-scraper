import re
from collections import Counter

from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.init import engine
from database.report import Report
from logs import logger
from services.speech import _is_artifact_line, get_start_of_speech_line

_MAX_PARLIAMENT = 11
_REPORT_BATCH = 2_000
_HEADER_SCAN_LINE_COUNT = 15
_NO_HEADER_ROW_INDEX = -1
_PERCENT = 100
_RULE_LINE_PREFIX = "---"

_ADR_EXCLUDED_SPEAKER_RE = re.compile(r"hon\.? members?", re.IGNORECASE)
_MARKUP_AND_SPACE_RE = re.compile(r"[\s*_\\#|]+")
_LEADING_BOLD_LABEL_RE = re.compile(r"^.*?(\*\*[^*]+?\*\*\s*)+:?")
_HEADER_ROW_MARKERS = ("Title:|", "MPs Speaking:|")


def _get_countable_character_count(text: str) -> int:
    return len(_MARKUP_AND_SPACE_RE.sub("", text))


def _is_adr_excluded(speaker: str) -> bool:
    return bool(_ADR_EXCLUDED_SPEAKER_RE.search(speaker)) or speaker.startswith(("(", "_"))


def _get_body_character_count(report: Report) -> int:
    lines = report.markdown_content.splitlines()
    start = get_start_of_speech_line(
        report.markdown_content, report.title, report.subtitle, report.original_title, report.report_type,
        report.report_version,
    )
    if start is None:
        start = max((line_index for line_index, line in enumerate(lines[:_HEADER_SCAN_LINE_COUNT]) if any(marker in line for marker in _HEADER_ROW_MARKERS)), default=_NO_HEADER_ROW_INDEX)
    total = 0
    for line in lines[start + 1:]:
        stripped = line.strip()
        if _is_artifact_line(stripped) or stripped.startswith(_RULE_LINE_PREFIX):
            continue
        total += _get_countable_character_count(_LEADING_BOLD_LABEL_RE.sub("", stripped, count=1) if "**" in stripped else stripped)
    return total


def main() -> None:
    with Session(engine) as session:
        reports = [report for report in CRUDReport(session).get_by_markdown_content_not_null() if report.parliament_number <= _MAX_PARLIAMENT]
        rows = []
        report_ids = [report.id for report in reports]
        for start in range(0, len(report_ids), _REPORT_BATCH):
            rows.extend(CRUDSpeech(session).get_rows_by_report_ids(report_ids[start:start + _REPORT_BATCH]))

    category_to_row_count: Counter[str] = Counter()
    category_to_character_count: Counter[str] = Counter()
    reports_with_rows = set()
    for row in rows:
        reports_with_rows.add(row.report_id)
        if row.speaker is None:
            category = "no_speaker"
        elif _is_adr_excluded(row.speaker):
            category = "adr_excluded"
        elif row.speaker_id is None:
            category = "named_unlinked"
        else:
            category = "linked"
        category_to_row_count[category] += 1
        category_to_character_count[category] += _get_countable_character_count(row.transcript)

    report_id_to_body_character_count = {report.id: _get_body_character_count(report) for report in reports}
    body_total = sum(report_id_to_body_character_count.values())
    body_in_zero_row_reports = sum(character_count for report_id, character_count in report_id_to_body_character_count.items() if report_id not in reports_with_rows)
    rows_total = sum(category_to_row_count.values())
    adr_denominator = category_to_row_count["linked"] + category_to_row_count["named_unlinked"]
    stored_character_count = sum(category_to_character_count.values())

    logger.info(f"Parliaments 0 to {_MAX_PARLIAMENT}: {len(reports)} reports with markdown, "
          f"{len(reports_with_rows)} with speech rows, {rows_total} speech rows")
    logger.info(f"1. ADR 0001 rate:  {category_to_row_count['linked']} / {adr_denominator} = "
          f"{_PERCENT * category_to_row_count['linked'] / adr_denominator:.2f}%")
    logger.info(f"2. All-rows rate:  {category_to_row_count['linked']} / {rows_total} = {_PERCENT * category_to_row_count['linked'] / rows_total:.2f}%")
    logger.info(f"3. Text share:     {category_to_character_count['linked']} / {body_total} chars = {_PERCENT * category_to_character_count['linked'] / body_total:.2f}%")
    logger.info("Where the body text goes (chars, share of body):")
    for label, character_count in (
        ("linked rows", category_to_character_count["linked"]),
        ("named but unlinked rows", category_to_character_count["named_unlinked"]),
        ("ADR-excluded rows (hon. Members, stage directions)", category_to_character_count["adr_excluded"]),
        ("rows with no speaker", category_to_character_count["no_speaker"]),
        ("reports with no rows", body_in_zero_row_reports),
        ("dropped inside reports with rows (preamble, headings, labels)",
         body_total - stored_character_count - body_in_zero_row_reports),
    ):
        logger.info(f"  {label:<64} {character_count:>12} {_PERCENT * character_count / body_total:6.2f}%")
    logger.info(f"Rows by category: {dict(category_to_row_count)}")


if __name__ == "__main__":
    main()

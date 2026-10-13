"""
Speech attribution measured three ways for Parliaments 0 to 11, so no single denominator can flatter the result.

Usage:
    poetry run python3 scripts/attribution_text_share.py

1. ADR 0001 rate: linked rows / rows with a speaker string, minus collective "hon. Member(s)" references and
   strings starting with "(" or "_" (docs/adr/0001-attribution-denominator.md).
2. All-rows rate: linked rows / every speech row, NULL-speaker rows included. Setting a row's speaker to NULL
   raises rate 1 but not this one.
3. Text share: characters of body text that sit in a linked row / characters of body text in every report with
   markdown, including reports that produced no rows. This is the figure that answers "how much of the record
   can a researcher retrieve by speaker". Text the parser drops never reaches rates 1 or 2.

Characters are counted after removing whitespace and markdown markup, and body text excludes the metadata header,
the title line, page and column markers, and the bold speaker label at the start of a line.
"""

import re
from collections import Counter

from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.init import engine
from services.speech import _is_artifact_line, get_start_of_speech_line

_MAX_PARLIAMENT = 11
_REPORT_BATCH = 2_000

# ADR 0001: collective references and stage directions name no one person.
_ADR_EXCLUDED_SPEAKER_RE = re.compile(r"hon\.? members?", re.IGNORECASE)
_MARKUP_AND_SPACE_RE = re.compile(r"[\s*_\\#|]+")
_LEADING_BOLD_LABEL_RE = re.compile(r"^.*?(\*\*[^*]+?\*\*\s*)+:?")
_HEADER_ROW_MARKERS = ("Title:|", "MPs Speaking:|")


def _countable_chars(text: str) -> int:
    return len(_MARKUP_AND_SPACE_RE.sub("", text))


def _is_adr_excluded(speaker: str) -> bool:
    return bool(_ADR_EXCLUDED_SPEAKER_RE.search(speaker)) or speaker.startswith(("(", "_"))


def _body_chars(report) -> int:
    """Countable characters after the start line, or after the metadata header when no start line is found."""
    lines = report.markdown_content.splitlines()
    start = get_start_of_speech_line(
        report.markdown_content, report.title, report.subtitle, report.original_title, report.report_type
    )
    if start is None:
        start = max((i for i, line in enumerate(lines[:15]) if any(m in line for m in _HEADER_ROW_MARKERS)), default=-1)
    total = 0
    for line in lines[start + 1:]:
        stripped = line.strip()
        if _is_artifact_line(stripped) or stripped.startswith("---"):
            continue
        total += _countable_chars(_LEADING_BOLD_LABEL_RE.sub("", stripped, count=1) if "**" in stripped else stripped)
    return total


def main():
    with Session(engine) as session:
        reports = [r for r in CRUDReport(session).get_by_markdown_content_not_null() if r.parliament_number <= _MAX_PARLIAMENT]
        speech_crud = CRUDSpeech(session)
        rows = []
        report_ids = [r.id for r in reports]
        for i in range(0, len(report_ids), _REPORT_BATCH):
            rows.extend(speech_crud.get_rows_by_report_ids(report_ids[i:i + _REPORT_BATCH]))

    row_counts: Counter[str] = Counter()
    row_chars: Counter[str] = Counter()
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
        row_counts[category] += 1
        row_chars[category] += _countable_chars(row.transcript)

    body_by_report = {r.id: _body_chars(r) for r in reports}
    body_total = sum(body_by_report.values())
    body_in_zero_row_reports = sum(chars for rid, chars in body_by_report.items() if rid not in reports_with_rows)
    rows_total = sum(row_counts.values())
    adr_denominator = row_counts["linked"] + row_counts["named_unlinked"]
    stored_chars = sum(row_chars.values())

    print(f"Parliaments 0 to {_MAX_PARLIAMENT}: {len(reports)} reports with markdown, "
          f"{len(reports_with_rows)} with speech rows, {rows_total} speech rows")
    print()
    print(f"1. ADR 0001 rate:  {row_counts['linked']} / {adr_denominator} = "
          f"{100 * row_counts['linked'] / adr_denominator:.2f}%")
    print(f"2. All-rows rate:  {row_counts['linked']} / {rows_total} = {100 * row_counts['linked'] / rows_total:.2f}%")
    print(f"3. Text share:     {row_chars['linked']} / {body_total} chars = {100 * row_chars['linked'] / body_total:.2f}%")
    print()
    print("Where the body text goes (chars, share of body):")
    for label, chars in (
        ("linked rows", row_chars["linked"]),
        ("named but unlinked rows", row_chars["named_unlinked"]),
        ("ADR-excluded rows (hon. Members, stage directions)", row_chars["adr_excluded"]),
        ("rows with no speaker", row_chars["no_speaker"]),
        ("reports with no rows", body_in_zero_row_reports),
        ("dropped inside reports with rows (preamble, headings, labels)",
         body_total - stored_chars - body_in_zero_row_reports),
    ):
        print(f"  {label:<64} {chars:>12} {100 * chars / body_total:6.2f}%")
    print()
    print("Rows by category:", dict(row_counts))


if __name__ == "__main__":
    main()

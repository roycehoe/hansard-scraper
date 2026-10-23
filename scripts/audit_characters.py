import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy.engine import make_url
from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.attendance import CRUDAttendance
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from crud.speech import CRUDSpeech
from database.init import engine
from logs import logger
from services.character_audit import (
    CHARACTER_SIGNATURES,
    get_character_fault_counts,
    get_derived_text_counts,
    get_signature_context,
)
from settings import settings


@dataclass
class SignatureTally:
    rows: int = 0
    occurrences: int = 0
    rows_not_in_raw: Optional[int] = None
    example: Optional[str] = None


Tallies = dict[tuple[str, str], SignatureTally]


def _add_counts(tallies: Tallies, column: str, row_label: str, text: str, counts: dict[str, int], raw_signatures: Optional[frozenset[str]]) -> None:
    for name, count in counts.items():
        tally = tallies[(column, name)]
        tally.rows += 1
        tally.occurrences += count
        # NOTE: only a character fault can be in the raw HTML; markup and pair counts have no raw side.
        if raw_signatures is not None and name in CHARACTER_SIGNATURES:
            rows_not_in_raw = 0 if tally.rows_not_in_raw is None else tally.rows_not_in_raw
            tally.rows_not_in_raw = rows_not_in_raw + (name not in raw_signatures)
        if tally.example is None:
            tally.example = f"{row_label}: {get_signature_context(text, name)!r}"


def _tally(tallies: Tallies, column: str, row_label: str, text: Optional[str], raw_signatures: Optional[frozenset[str]]) -> None:
    if text:
        _add_counts(tallies, column, row_label, text, get_derived_text_counts(text), raw_signatures)


def _tally_raw(tallies: Tallies, column: str, row_label: str, raw_text: str) -> None:
    _add_counts(tallies, column, row_label, raw_text, get_character_fault_counts(raw_text), None)


def _get_raw_signatures(raw_text: Optional[str]) -> frozenset[str]:
    return frozenset(get_character_fault_counts(raw_text)) if raw_text else frozenset()


def _get_tallies(session: Session) -> Tallies:
    tallies: Tallies = defaultdict(SignatureTally)
    report_raw_signatures: dict[int, frozenset[str]] = {}
    for report in CRUDReport(session).get_text_rows():
        raw_signatures = _get_raw_signatures(report.content)
        if raw_signatures:
            report_raw_signatures[report.id] = raw_signatures
            _tally_raw(tallies, "report.content (raw)", f"report {report.id}", report.content)
        _tally(tallies, "report.title", f"report {report.id}", report.title, None)
        _tally(tallies, "report.subtitle", f"report {report.id}", report.subtitle, None)
        _tally(tallies, "report.markdown_content", f"report {report.id}", report.markdown_content, raw_signatures)
    logger.info("Reports read")
    for speech in CRUDSpeech(session).get_text_rows():
        raw_signatures = report_raw_signatures.get(speech.report_id, frozenset())
        _tally(tallies, "speech.speaker", f"speech {speech.id}", speech.speaker, raw_signatures)
        _tally(tallies, "speech.transcript", f"speech {speech.id}", speech.transcript, raw_signatures)
    logger.info("Speech rows read")
    for sitting in CRUDSitting(session).get_text_rows():
        raw_signatures = _get_raw_signatures(sitting.html_full_content)
        if raw_signatures:
            _tally_raw(tallies, "sitting.html_full_content (raw)", f"sitting {sitting.id}", sitting.html_full_content)
        _tally(tallies, "sitting.markdown_content", f"sitting {sitting.id}", sitting.markdown_content, raw_signatures)
    logger.info("Sittings read")
    for attendance in CRUDAttendance(session).get_text_rows():
        _tally(tallies, "attendance.speaker_name", f"attendance {attendance.id}", attendance.speaker_name, None)
        _tally(tallies, "attendance.location_name", f"attendance {attendance.id}", attendance.location_name, None)
    return tallies


def _get_lines(tallies: Tallies) -> list[str]:
    lines = [f"Character audit of {make_url(settings.database_url).database}"]
    for (column, name), tally in sorted(tallies.items()):
        not_in_raw = "" if tally.rows_not_in_raw is None else f", {tally.rows_not_in_raw} rows not in the raw text"
        lines.append(f"{column} | {name} | {tally.rows} rows, {tally.occurrences} occurrences{not_in_raw} | e.g. {tally.example}")
    return lines


def audit_characters(output_path: Optional[Path]) -> None:
    with Session(engine) as session:
        lines = _get_lines(_get_tallies(session))
    for line in lines:
        logger.info(line)
    if output_path is not None:
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count character faults in every stored text column, and say which the raw text already held")
    parser.add_argument("--output", type=Path, help="write the lines to this path, such as docs/figures/YYYY-MM-DD-character-audit.txt")
    arguments = parser.parse_args()
    audit_characters(arguments.output)

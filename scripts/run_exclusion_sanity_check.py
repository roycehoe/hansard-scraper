import random
import re
from collections import defaultdict

from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech for Report.speeches
from crud.report import CRUDReport
from database.init import engine
from database.report import Report
from logs import logger
from services.speech import (
    extract_mps_speaking,
    get_speeches,
    get_start_of_speech_line,
)

_SAMPLE_SIZE_PER_REPORT_TYPE = 5
_SEED = 42
_MIN_MULTI_SPEAKER_COUNT = 2
_SEPARATOR_WIDTH = 80
_SEPARATOR = "=" * _SEPARATOR_WIDTH
_TITLE_DISPLAY_LENGTH = 70
_SPEAKERS_SHOWN = 5
_SUSPICIOUS_FLAGS_SHOWN = 10
_HTML_BOLD_SHOWN = 5
_MARKDOWN_BOLD_SHOWN = 5
_MARKDOWN_BOLD_DISPLAY_LENGTH = 100
_SNIPPET_LEADING_CONTEXT = 100
_SNIPPET_TRAILING_CONTEXT = 400
_SNIPPET_DISPLAY_LENGTH = 300
_MARKDOWN_LINES_SHOWN = 20
_MARKDOWN_LINE_DISPLAY_LENGTH = 100
_WHITESPACE_RE = re.compile(r"\s+")
_PERSONAL_TITLE_RE = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc|Col|Brig|Gen|Maj|Capt|Lt)\b")
_FIRST_BOLD_TAG_RE = re.compile(r"<(?:strong|b)\b", re.IGNORECASE)
_BEFORE_FIRST_LINE = -1

_HTML_BOLD_RE = re.compile(r"<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>", re.IGNORECASE | re.DOTALL)
_MARKDOWN_BOLD_RE = re.compile(r"\*\*[^* ][^*]*\*\*")


def _html_bold_texts(html: str) -> list[str]:
    return [_WHITESPACE_RE.sub(" ", text).strip() for text in _HTML_BOLD_RE.findall(html) if text.strip()]


def _looks_like_speaker(text: str) -> bool:
    stripped_text = text.strip()
    if stripped_text.endswith(":"):
        return True
    if _PERSONAL_TITLE_RE.search(stripped_text):
        return True
    return False


def _show_doc(report: Report, start_line: int, speakers: list[str]) -> list[str]:
    title_display = (report.title or "")[:_TITLE_DISPLAY_LENGTH]
    logger.info(f"\n  id={report.id}  parl={report.parliament_number}  type={report.report_type}")
    logger.info(f"  title: {title_display!r}")
    logger.info(f"  MPs Speaking ({len(speakers)}): {'; '.join(speakers[:_SPEAKERS_SHOWN])}")

    html_bold_texts = _html_bold_texts(report.content or "")
    speaker_like = [text for text in html_bold_texts if _looks_like_speaker(text)]
    logger.info(f"  HTML <strong>/<b> tags: {len(html_bold_texts)} total, {len(speaker_like)} speaker-like")
    if speaker_like:
        for text in speaker_like[:_HTML_BOLD_SHOWN]:
            logger.info(f"    HTML bold: {text!r}")

    lines_after = report.markdown_content.splitlines()[start_line + 1:]
    markdown_bold_lines = [line for line in lines_after if _MARKDOWN_BOLD_RE.search(line.strip())]
    logger.info(f"  Markdown **bold** lines after start: {len(markdown_bold_lines)}")
    for line in markdown_bold_lines[:_MARKDOWN_BOLD_SHOWN]:
        logger.info(f"    MD bold: {line.strip()[:_MARKDOWN_BOLD_DISPLAY_LENGTH]}")

    html = report.content or ""
    first_bold = _FIRST_BOLD_TAG_RE.search(html)
    if first_bold is not None:
        snippet_start = max(0, first_bold.start() - _SNIPPET_LEADING_CONTEXT)
        snippet_end = min(len(html), first_bold.start() + _SNIPPET_TRAILING_CONTEXT)
        snippet = html[snippet_start:snippet_end]
        snippet_clean = _WHITESPACE_RE.sub(" ", snippet)
        logger.info("  HTML snippet around first bold tag:")
        logger.info(f"    {snippet_clean[:_SNIPPET_DISPLAY_LENGTH]!r}")

    logger.info(f"  Markdown (lines {start_line}–{start_line + _MARKDOWN_LINES_SHOWN}):")
    for offset, line in enumerate(lines_after[:_MARKDOWN_LINES_SHOWN]):
        logger.info(f"    {start_line + 1 + offset:4d}: {line[:_MARKDOWN_LINE_DISPLAY_LENGTH]}")

    if speaker_like and not markdown_bold_lines:
        return speaker_like
    return []


def run() -> None:
    random.seed(_SEED)

    with Session(engine) as session:
        reports = CRUDReport(session).get_by_markdown_content_not_null()

    logger.info(f"Reports with markdown: {len(reports)}")

    zero_speaker: list[tuple[Report, int]] = []
    multi_speaker: dict[str, list[tuple[Report, int, list[str]]]] = defaultdict(list)
    no_start_line: list[Report] = []

    for report in reports:
        start_line = get_start_of_speech_line(
            report.markdown_content,
            report.title,
            report.subtitle,
            report.original_title,
            report.report_type,
            report.report_version,
        )
        if start_line is None:
            no_start_line.append(report)
            continue
        speeches = get_speeches(report.markdown_content, start_line, report.report_type, report.report_version)
        if speeches:
            continue

        speakers = extract_mps_speaking(report.markdown_content)
        if len(speakers) == 0:
            zero_speaker.append((report, start_line))
        elif len(speakers) >= _MIN_MULTI_SPEAKER_COUNT:
            multi_speaker[report.report_type].append((report, start_line, speakers))

    total_multi = sum(len(reports_of_type) for reports_of_type in multi_speaker.values())
    logger.info(f"Excluded — zero-speaker:  {len(zero_speaker)}")
    logger.info(f"Excluded — multi-speaker: {total_multi}")
    logger.info(f"Excluded — no start line: {len(no_start_line)}")
    logger.info("")

    logger.info(_SEPARATOR)
    logger.info("ZERO-SPEAKER DOCS (MPs Speaking absent or empty)")
    logger.info(_SEPARATOR)
    for report, start_line in zero_speaker:
        _show_doc(report, start_line, speakers=[])

    logger.info("")
    logger.info(_SEPARATOR)
    logger.info("NO-START-LINE DOCS (never parsed)")
    logger.info(_SEPARATOR)
    suspicious = []
    for report in no_start_line:
        speakers = extract_mps_speaking(report.markdown_content)
        flags = _show_doc(report, _BEFORE_FIRST_LINE, speakers)
        if flags:
            suspicious.append((report, _BEFORE_FIRST_LINE, speakers, flags))

    logger.info("")
    logger.info(_SEPARATOR)
    logger.info("MULTI-SPEAKER DOCS — stratified sample")
    logger.info(_SEPARATOR)

    for report_type, reports_of_type in sorted(multi_speaker.items(), key=lambda item: -len(item[1])):
        sample = random.sample(reports_of_type, min(_SAMPLE_SIZE_PER_REPORT_TYPE, len(reports_of_type)))
        logger.info(f"\n--- {report_type} ({len(reports_of_type)} total, checking {len(sample)}) ---")

        for report, start_line, speakers in sample:
            flags = _show_doc(report, start_line, speakers)
            if flags:
                suspicious.append((report, start_line, speakers, flags))

    logger.info("")
    logger.info(_SEPARATOR)
    logger.info(f"SUSPICIOUS (HTML bold present, no markdown speaker): {len(suspicious)}")
    if suspicious:
        for report, start_line, speakers, flags in suspicious:
            logger.info(f"\n  id={report.id}  type={report.report_type}  parl={report.parliament_number}")
            logger.info(f"  title: {report.title!r}")
            logger.info(f"  MPs Speaking: {speakers}")
            logger.info("  HTML bold texts that look like speakers:")
            for flag in flags[:_SUSPICIOUS_FLAGS_SHOWN]:
                logger.info(f"    {flag!r}")


if __name__ == "__main__":
    run()

"""
Sanity check on the ~256 excluded docs (where get_speeches returns []).

Excluded set:
  - 0 names in MPs Speaking  (~3 docs)
  - 2+ names in MPs Speaking (~253 docs) — assumed to be annex/index docs
  - no start line: never parsed; every one is shown, not sampled

For each group, draw a stratified random sample (K per report_type) and compare:
  - Raw HTML: does it contain <strong> or <b> tags with speaker-like content?
  - Markdown: does it contain **Name:** patterns after the start line?

A mismatch (bold in HTML, absent in markdown) signals a potential parser bug.
"""

import random
import re
from collections import defaultdict

from sqlmodel import Session

import database.speech  # noqa: F401  (registers Speech for Report.speeches)
from crud.report import CRUDReport
from database.init import engine
from services.speech import (
    _extract_mps_speaking,
    get_speeches,
    get_start_of_speech_line,
)

_SAMPLE_SIZE_PER_REPORT_TYPE = 5
_RANDOM_SEED = 42
# Passed as start_line for a doc with no start line, so _show_doc reads it from line 0.
_BEFORE_FIRST_LINE = -1

# HTML bold tags that might carry speaker names
_HTML_BOLD_RE = re.compile(r"<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>", re.IGNORECASE | re.DOTALL)
# Markdown closed-bold pattern (what speaker names look like after conversion)
_MARKDOWN_BOLD_RE = re.compile(r"\*\*[^* ][^*]*\*\*")


def _html_bold_texts(html: str) -> list[str]:
    return [re.sub(r"\s+", " ", text).strip() for text in _HTML_BOLD_RE.findall(html) if text.strip()]


def _looks_like_speaker(text: str) -> bool:
    """Heuristic: bold text that ends with a colon or contains a personal title."""
    stripped_text = text.strip()
    if stripped_text.endswith(":"):
        return True
    if re.search(r"\b(Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc|Col|Brig|Gen|Maj|Capt|Lt)\b", stripped_text):
        return True
    return False


def run():
    random.seed(_RANDOM_SEED)

    with Session(engine) as session:
        reports = CRUDReport(session).get_by_markdown_content_not_null()

    print(f"Reports with markdown: {len(reports)}")

    # Identify the excluded set: get_speeches returns [] after fallback
    zero_speaker: list = []
    multi_speaker: dict[str, list] = defaultdict(list)
    no_start_line: list = []

    for report in reports:
        start_line = get_start_of_speech_line(
            report.markdown_content,
            report.title,
            report.subtitle,
            report.original_title,
            report.report_type,
        )
        if start_line is None:
            no_start_line.append(report)
            continue
        speeches = get_speeches(report.markdown_content, start_line, report.report_type)
        if speeches:
            continue

        speakers = _extract_mps_speaking(report.markdown_content)
        if len(speakers) == 0:
            zero_speaker.append((report, start_line))
        elif len(speakers) >= 2:
            multi_speaker[report.report_type].append((report, start_line, speakers))

    total_multi = sum(len(reports_of_type) for reports_of_type in multi_speaker.values())
    print(f"Excluded — zero-speaker:  {len(zero_speaker)}")
    print(f"Excluded — multi-speaker: {total_multi}")
    print(f"Excluded — no start line: {len(no_start_line)}")
    print()

    # ── Zero-speaker group ────────────────────────────────────────────────────
    print("=" * 80)
    print("ZERO-SPEAKER DOCS (MPs Speaking absent or empty)")
    print("=" * 80)
    for report, start_line in zero_speaker:
        _show_doc(report, start_line, speakers=[])

    # ── No-start-line group: never parsed, so every doc is shown ──────────────
    print()
    print("=" * 80)
    print("NO-START-LINE DOCS (never parsed)")
    print("=" * 80)
    suspicious = []
    for report in no_start_line:
        speakers = _extract_mps_speaking(report.markdown_content)
        flags = _show_doc(report, _BEFORE_FIRST_LINE, speakers)
        if flags:
            suspicious.append((report, _BEFORE_FIRST_LINE, speakers, flags))

    # ── Multi-speaker group ───────────────────────────────────────────────────
    print()
    print("=" * 80)
    print("MULTI-SPEAKER DOCS — stratified sample")
    print("=" * 80)

    for report_type, items in sorted(multi_speaker.items(), key=lambda item: -len(item[1])):
        sample = random.sample(items, min(_SAMPLE_SIZE_PER_REPORT_TYPE, len(items)))
        print(f"\n--- {report_type} ({len(items)} total, checking {len(sample)}) ---")

        for report, start_line, speakers in sample:
            flags = _show_doc(report, start_line, speakers)
            if flags:
                suspicious.append((report, start_line, speakers, flags))

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 80)
    print(f"SUSPICIOUS (HTML bold present, no markdown speaker): {len(suspicious)}")
    if suspicious:
        for report, start_line, speakers, flags in suspicious:
            print(f"\n  id={report.id}  type={report.report_type}  parl={report.parliament_number}")
            print(f"  title: {report.title!r}")
            print(f"  MPs Speaking: {speakers}")
            print("  HTML bold texts that look like speakers:")
            for flag in flags[:10]:
                print(f"    {flag!r}")


def _show_doc(report, start_line: int, speakers: list[str]) -> list[str]:
    """Print doc summary. Returns list of suspicious HTML bold texts (empty = clean)."""
    title_display = (report.title or "")[:70]
    print(f"\n  id={report.id}  parl={report.parliament_number}  type={report.report_type}")
    print(f"  title: {title_display!r}")
    print(f"  MPs Speaking ({len(speakers)}): {'; '.join(speakers[:5])}")

    # ── HTML bold analysis ────────────────────────────────────────────────────
    html_bold_texts = _html_bold_texts(report.content or "")
    speaker_like = [text for text in html_bold_texts if _looks_like_speaker(text)]
    print(f"  HTML <strong>/<b> tags: {len(html_bold_texts)} total, {len(speaker_like)} speaker-like")
    if speaker_like:
        for text in speaker_like[:5]:
            print(f"    HTML bold: {text!r}")

    # ── Markdown after start line ─────────────────────────────────────────────
    lines_after = report.markdown_content.splitlines()[start_line + 1:]
    markdown_bold_lines = [line for line in lines_after if _MARKDOWN_BOLD_RE.search(line.strip())]
    print(f"  Markdown **bold** lines after start: {len(markdown_bold_lines)}")
    for line in markdown_bold_lines[:5]:
        print(f"    MD bold: {line.strip()[:100]}")

    # ── Raw HTML snippet (around first bold tag) ──────────────────────────────
    html = report.content or ""
    first_bold = re.search(r"<(?:strong|b)\b", html, re.IGNORECASE)
    if first_bold:
        snippet_start = max(0, first_bold.start() - 100)
        snippet_end = min(len(html), first_bold.start() + 400)
        snippet = html[snippet_start:snippet_end]
        snippet_clean = re.sub(r"\s+", " ", snippet)
        print("  HTML snippet around first bold tag:")
        print(f"    {snippet_clean[:300]!r}")

    # ── Markdown snippet ──────────────────────────────────────────────────────
    print(f"  Markdown (lines {start_line}–{start_line + 20}):")
    for offset, line in enumerate(lines_after[:20]):
        print(f"    {start_line + 1 + offset:4d}: {line[:100]}")

    # Flag if HTML has speaker-like bold but markdown has none
    flags = []
    if speaker_like and not markdown_bold_lines:
        flags = speaker_like
    return flags


if __name__ == "__main__":
    run()

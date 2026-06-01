"""
Sanity check on the ~256 excluded docs (where get_speeches returns []).

Excluded set:
  - 0 names in MPs Speaking  (~3 docs)
  - 2+ names in MPs Speaking (~253 docs) — assumed to be annex/index docs

For each group, draw a stratified random sample (K per report_type) and compare:
  - Raw HTML: does it contain <strong> or <b> tags with speaker-like content?
  - Markdown: does it contain **Name:** patterns after the start line?

A mismatch (bold in HTML, absent in markdown) signals a potential parser bug.
"""

import random
import re
from collections import defaultdict

from sqlmodel import Session

from crud.report import CRUDReport
from database.init import engine
from services.speech import (
    _extract_mps_speaking,
    get_speeches,
    get_start_of_speech_line,
)

K = 5
SEED = 42

# HTML bold tags that might carry speaker names
_HTML_BOLD_RE = re.compile(r"<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>", re.IGNORECASE | re.DOTALL)
# Markdown closed-bold pattern (what speaker names look like after conversion)
_MD_BOLD_RE = re.compile(r"\*\*[^* ][^*]*\*\*")


def _html_bold_texts(html: str) -> list[str]:
    return [re.sub(r"\s+", " ", t).strip() for t in _HTML_BOLD_RE.findall(html) if t.strip()]


def _looks_like_speaker(text: str) -> bool:
    """Heuristic: bold text that ends with a colon or contains a personal title."""
    t = text.strip()
    if t.endswith(":"):
        return True
    if re.search(r"\b(Mr|Mrs|Ms|Dr|Prof|Mdm|Assoc|Col|Brig|Gen|Maj|Capt|Lt)\b", t):
        return True
    return False


def run():
    random.seed(SEED)

    with Session(engine) as session:
        reports = CRUDReport(session).get_all_with_markdown()

    print(f"Reports with markdown: {len(reports)}")

    # Identify the excluded set: get_speeches returns [] after fallback
    zero_speaker: list = []
    multi_speaker: dict[str, list] = defaultdict(list)

    for report in reports:
        start_line = get_start_of_speech_line(
            report.markdown_content,
            report.title,
            report.subtitle,
            report.original_title,
            report.report_type,
        )
        if start_line is None:
            continue
        speeches = get_speeches(report.markdown_content, start_line, report.report_type)
        if speeches:
            continue

        speakers = _extract_mps_speaking(report.markdown_content)
        if len(speakers) == 0:
            zero_speaker.append((report, start_line))
        elif len(speakers) >= 2:
            multi_speaker[report.report_type].append((report, start_line, speakers))

    total_multi = sum(len(v) for v in multi_speaker.values())
    print(f"Excluded — zero-speaker:  {len(zero_speaker)}")
    print(f"Excluded — multi-speaker: {total_multi}")
    print()

    # ── Zero-speaker group ────────────────────────────────────────────────────
    print("=" * 80)
    print("ZERO-SPEAKER DOCS (MPs Speaking absent or empty)")
    print("=" * 80)
    for report, start_line in zero_speaker:
        _show_doc(report, start_line, speakers=[])

    # ── Multi-speaker group ───────────────────────────────────────────────────
    print()
    print("=" * 80)
    print("MULTI-SPEAKER DOCS — stratified sample")
    print("=" * 80)

    suspicious = []

    for rt, items in sorted(multi_speaker.items(), key=lambda x: -len(x[1])):
        sample = random.sample(items, min(K, len(items)))
        print(f"\n--- {rt} ({len(items)} total, checking {len(sample)}) ---")

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
            for f in flags[:10]:
                print(f"    {f!r}")


def _show_doc(report, start_line: int, speakers: list[str]) -> list[str]:
    """Print doc summary. Returns list of suspicious HTML bold texts (empty = clean)."""
    title_display = (report.title or "")[:70]
    print(f"\n  id={report.id}  parl={report.parliament_number}  type={report.report_type}")
    print(f"  title: {title_display!r}")
    print(f"  MPs Speaking ({len(speakers)}): {'; '.join(speakers[:5])}")

    # ── HTML bold analysis ────────────────────────────────────────────────────
    html_bolds = _html_bold_texts(report.content or "")
    speaker_like = [t for t in html_bolds if _looks_like_speaker(t)]
    print(f"  HTML <strong>/<b> tags: {len(html_bolds)} total, {len(speaker_like)} speaker-like")
    if speaker_like:
        for t in speaker_like[:5]:
            print(f"    HTML bold: {t!r}")

    # ── Markdown after start line ─────────────────────────────────────────────
    lines_after = report.markdown_content.splitlines()[start_line + 1:]
    md_bolds = [line for line in lines_after if _MD_BOLD_RE.search(line.strip())]
    print(f"  Markdown **bold** lines after start: {len(md_bolds)}")
    for line in md_bolds[:5]:
        print(f"    MD bold: {line.strip()[:100]}")

    # ── Raw HTML snippet (around first bold tag) ──────────────────────────────
    html = report.content or ""
    first_bold = re.search(r"<(?:strong|b)\b", html, re.IGNORECASE)
    if first_bold:
        snip_start = max(0, first_bold.start() - 100)
        snip_end = min(len(html), first_bold.start() + 400)
        snippet = html[snip_start:snip_end]
        snippet_clean = re.sub(r"\s+", " ", snippet)
        print("  HTML snippet around first bold tag:")
        print(f"    {snippet_clean[:300]!r}")

    # ── Markdown snippet ──────────────────────────────────────────────────────
    print(f"  Markdown (lines {start_line}–{start_line + 20}):")
    for i, line in enumerate(lines_after[:20]):
        print(f"    {start_line + 1 + i:4d}: {line[:100]}")

    # Flag if HTML has speaker-like bold but markdown has none
    flags = []
    if speaker_like and not md_bolds:
        flags = speaker_like
    return flags


if __name__ == "__main__":
    run()

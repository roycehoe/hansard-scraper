# Sanity Check — HandsardWebsiteResponse → Report → Speech

A manual end-to-end check of the parsing pipeline. Distinct from `refine-loop.md`,
which targets a quantitative pass rate. This check asks a qualitative question: for a
small, representative set of records, does the pipeline produce output that is faithful
to the source HTML?

**Control:** `handsardwebsiteresponse.content` (raw HTML as fetched from the API).  
**Output under test:** `Report` fields and `Speech` records generated from that HTML.

---

## Step 1 — Draw the sample

Use the strata from `sample.json` if it already exists (drawn during `refine-loop.md`
Setup Step 5). Do not re-sample if `sample.json` is present — the population changes as
patches are applied, so re-running would draw from a different set.

```python
import json
with open("sample.json") as f:
    sample_sets = json.load(f)
# keys: "pilot", "held_out", "regression"
all_ids = (
    sample_sets.get("pilot", [])
    + sample_sets.get("held_out", [])
    + sample_sets.get("regression", [])
)
```

If `sample.json` is absent, draw a fresh stratified sample from `HandsardWebsiteResponse`
using the same grouping convention as `refine-loop.md`: K=3 per
`(failure_stage, report_type)` for failing documents, plus ~30 passing documents as a
regression set. Write the result to `sanity-sample.json` (separate from `sample.json`
to avoid polluting the refine-loop sample).

```python
# Only run if sample.json does not exist.
from sqlmodel import select
from database.init import get_session
from database.report import HandsardWebsiteResponse, ParsingStatistics
from enums import ReportType

session = next(get_session())
K = 3

# Failing documents — stratified by (failure_stage, report_type)
failing_ids = []
for rt in ReportType:
    for failure_stage, has_start, can_speak in [
        ("has_start_line", False, False),
        ("can_get_speeches", True, False),
    ]:
        rows = session.exec(
            select(ParsingStatistics.report_id)
            .where(ParsingStatistics.report_type == rt.value)
            .where(ParsingStatistics.has_markdown == True)
            .where(ParsingStatistics.has_start_line == has_start)
            .where(ParsingStatistics.can_get_speeches == can_speak)
            .limit(K)
        ).all()
        failing_ids.extend(rows)

# Passing documents — ~30 across report types
passing_ids = []
for rt in ReportType:
    rows = session.exec(
        select(ParsingStatistics.report_id)
        .where(ParsingStatistics.report_type == rt.value)
        .where(ParsingStatistics.can_get_speeches == True)
        .limit(2)
    ).all()
    passing_ids.extend(rows)
passing_ids = passing_ids[:30]

with open("sanity-sample.json", "w") as f:
    json.dump({"failing": failing_ids, "passing": passing_ids}, f)
all_ids = failing_ids + passing_ids
```

---

## Step 2 — Generate Report and Speech objects

For each sampled record, run the pipeline in-memory (no DB writes):

```python
from sqlmodel import select
from database.report import HandsardWebsiteResponse
from services.report import get_db_report_in
from services.speech import get_start_of_speech_line, get_speeches

rows = session.exec(
    select(HandsardWebsiteResponse)
    .where(HandsardWebsiteResponse.id.in_(all_ids))
).all()

results = []
for row in rows:
    report = get_db_report_in(row)
    start_line = (
        get_start_of_speech_line(
            report.markdown_content,
            report.title,
            report.subtitle,
            report.original_title,
            report.report_type,
        )
        if report.markdown_content
        else None
    )
    speeches = (
        get_speeches(report.markdown_content, start_line)
        if start_line is not None
        else []
    )
    results.append({
        "raw": row,
        "report": report,
        "start_line": start_line,
        "speeches": speeches,
    })
```

---

## Step 3 — Compare each record

Work through `results` one at a time. Open three views side-by-side:

| View | How to get it |
|------|---------------|
| Raw HTML | `print(row.content[:3000])` or paste into a browser |
| Generated markdown | `print(report.markdown_content)` |
| Generated speeches | `for s in speeches: print(s.speaker, "│", s.transcript[:80])` |

Check each item against the list below. Mark pass (✓) or fail (✗) with a note.

### 3a — Title / subtitle extraction

| Check | Pass condition |
|-------|----------------|
| `report.title` matches visible title in HTML | Identical text, minus parenthetical subtitles |
| `report.subtitle` is None when HTML title has no parenthetical | |
| `report.subtitle` is None when parenthetical is an acronym (all-caps) | e.g. `(MAS)` → subtitle None, acronym stays in title |
| `report.subtitle` set when parenthetical is a descriptor | e.g. `(Resumption of Debate)` → `subtitle = "(Resumption of Debate)"` |
| No mojibake | No `â€™`, `âˆ'`, or similar sequences |

### 3b — HTML → markdown conversion

| Check | Pass condition |
|-------|----------------|
| `markdown_content` is not None when `content` is not None | |
| Table structure preserved as markdown table | Column headers and rows match HTML |
| Speaker names render as `**Name:**` bold pattern | Not dropped, not doubled |
| Page/column break markers stripped | No `<!-- page -->` or similar artefacts |
| No `&nbsp;` literals | Converted to spaces or removed |
| Bold lines not split across lines | Merged bold appears on one line |
| No garbled Unicode | Encoding is clean |

### 3c — Speech segmentation

| Check | Pass condition |
|-------|----------------|
| `start_line` is not None | Pipeline found the title heading |
| First speech begins after the title line | No pre-title content included |
| `Speech.speaker` values match bold names in markdown | Exact or close match |
| All `Speech.transcript` values are non-empty | |
| No speech has `speaker=None` when a named speaker is visible | |
| Speech boundaries align with bold name lines | Each new bold name starts a new `Speech` |
| Speech count is plausible for document length | 0 speeches on a multi-page document is suspicious |

### 3d — Report-type-specific checks

Consult `parsing-patterns.md` for per-type structural notes. Quick reference:

| report_type | Expected behaviour |
|-------------|-------------------|
| `oral-answer` | Q&A pairs; both questioner and answerer appear as distinct speakers |
| `written-answer` | No speeches expected; answer is tabular — `speeches` empty is correct |
| `written-answer-na` | Minimal content; `start_line` may be None — expected |
| `bill` | Long debate; many speakers (`Speech` count > 1) |
| `ministerial-statement` | First speaker matches the minister named in HTML |
| `budget` | Very long; high speech count; no truncation |

---

## Step 4 — Record findings

For each record with at least one failing check, record:

```
### <report_type> — parliament <N> — HandsardWebsiteResponse.id <ID>

**Failing checks:**
- [ ] <check name>: <what was seen vs. what was expected>

**Markdown snippet (around the failure):**
<10–20 lines>

**HTML snippet (corresponding section):**
<relevant HTML>

**Severity:** cosmetic | data-loss | pipeline-break
```

Severity definitions:
- **cosmetic** — output readable but formatting slightly off (whitespace, minor encoding)
- **data-loss** — content in HTML is absent or truncated in `Report`/`Speech`
- **pipeline-break** — `start_line` is None or `speeches` is empty when the document has speeches

Group findings by root cause before deciding whether to open a fix iteration.

---

## Step 5 — Decide next action

| Outcome | Action |
|---------|--------|
| All checks pass | Record date and sample size in `## Results` below |
| Only cosmetic failures | Document in `parsing-patterns.md`; no code change unless recurring |
| Data-loss or pipeline-break failures | Open a `refine-loop.md` iteration targeting those root causes |

---

## Results

_Record each run here. Do not delete old entries._

```
Date        | Sample size | Pipeline-break | Data-loss | Cosmetic | Notes
------------|-------------|----------------|-----------|----------|------
(no runs yet)
```

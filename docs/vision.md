# Vision

Turn the full record of Singapore's parliamentary proceedings, from colonial assembly to the present, into a clean, queryable dataset — every speech, every speaker, every sitting.

---

## Objectives

### 1. Complete corpus coverage
Fetch and store every Hansard entry published by SPRS, across all parliaments and all report types. No gaps from rate limits, format changes, or API quirks. The raw API response for every record is preserved exactly as received.

### 2. Faithful speaker attribution
Extract individual speeches from parliamentary transcripts and attribute each one to the correct MP. The target is near-complete attribution across the corpus: less than ~490 unattributable documents (and those that remain unattributed must be structurally unattributable — appendix link indexes, colonial-era procedural orders with no named author).

### 3. Rich sitting metadata
For every sitting date, capture full session metadata: attendance, permissions to be absent, debate sections, vernacular speeches, and annexures. Both pre- and post-August 2015 API formats are handled faithfully.

### 4. MP identity linking
Connect every speech and attendance record to a canonical MP identity (name, party, parliament number) sourced from parliament.gov.sg.

### 5. High-fidelity markdown
Convert raw HTML records into clean, readable markdown that downstream consumers can trust — stripping artifacts introduced by html2text across three distinct document eras (colonial, mid-era, modern) without losing any substantive content.

### 6. Automated quality monitoring
Track parsing success rates across the full corpus so regressions are caught immediately and improvement work is measurable.

---

## Strategies

### Pipeline architecture: raw first, derive second
Every external API response is stored in a raw response table before any transformation occurs. Entity tables (Report, Speech, Sitting) are pure extensions of their raw counterparts — no fields dropped, no values changed. This means the source of truth is always recoverable, and re-parsing is cheap: drop the derived rows, rerun the populate step.

### Staged, incremental population
The pipeline runs in discrete stages: fetch → parse → enrich. Each stage can be re-run independently. Skip logic at each stage (checking whether a record already exists before fetching or parsing) makes the pipeline idempotent and resumable after failures or interruptions.

### Async HTTP with rate-limit resilience
Fetching thousands of records requires concurrent HTTP. The gateway layer uses async requests with exponential backoff and jitter on 429 responses, so the pipeline self-throttles under load rather than failing hard or hammering the server.

### Stratified, human-supervised parsing refinement
Parsing improvements follow a structured loop: sample the corpus stratified by report type, identify failure groups (`has_start_line=False` or `can_get_speeches=False`), apply a fix, validate it against a regression holdout, and accept or roll back. Each cycle requires human review before committing. This keeps the improvement loop tight and prevents silent regressions across the ~22,000-document corpus.

### Format-aware HTML-to-markdown conversion
The raw HTML spans three document eras with different artifacts. Fixes are applied in `utils/markdown_parser.py` as targeted transformations: stripping known artifact patterns (`---|---` separators, empty bold pairs, orphan italic markers), merging consecutive bold-only lines split across page breaks, and normalising whitespace. Each fix is scoped to the artifact it addresses rather than applied globally, which limits blast radius when the source HTML varies.

### Title detection with multi-format fallback
`get_start_of_speech_line` locates where speeches begin by matching the document title in the markdown. It handles three old-format variants (italic title, open bold, plain text with context prefix) and the new heading format (`# Title`) introduced in Parliament 12+. Each check is additive: old-format documents never have a bare `# Title` line, so new checks cannot regress old documents.

### Principled attribution hierarchy
For documents that contain no bold speaker markup, attribution follows a deliberate fallback chain:
1. If the `MPs Speaking` header lists exactly one name, attribute the entire body to that MP (adjournment motions, bill first readings, procedural resolutions).
2. If the body follows a known ministerial attribution pattern (ministry heading + name + title), extract the minister from the body.
3. If neither applies, leave unattributed — do not fabricate attribution for multi-speaker appendix documents or structurally authorless procedural orders.

### Two-format sitting date handling
The sitting date API changed format at Parliament 13 (August 2015). The service layer branches explicitly on the cutoff date and routes each response to the correct builder (`build_old_handsard_sitting_date_response` / `build_new_handsard_sitting_date_response`). Both paths write to the same set of tables, with all fields `Optional` so either format can populate a subset without constraint violations.

### Fuzzy MP name matching for attendance
Attendance lines use title prefixes, honorific suffixes, and occasionally inverted name order that differ from how `Mp.name` is stored. Matching is performed by stripping known prefix titles and suffix honorifics before comparison, and by trying both natural and inverted name order. Match rate is tracked per corpus run (currently ~98.8%) so regressions in name-matching logic are visible.

### Diagnostic tooling as a first-class concern
The `scripts/` directory holds targeted validation and inspection tools: failure diagnosis by report type, single-speaker validation, sanity checks against the full corpus, and per-document inspection. Parsing statistics are exported to `statistics.csv` after every run. These tools make it possible to audit specific failure categories without re-running the full pipeline.

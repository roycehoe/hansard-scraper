# Vision

Turn the full record of Singapore's parliamentary proceedings, from colonial assembly to the present, into a clean, queryable dataset — every speech, every speaker, every sitting — giving researchers a reliable foundation for studying Singapore's political history at scale.

---

## Objectives

### 1. Complete corpus coverage
Fetch and store every Hansard entry published by SPRS, across all parliaments and all report types. No gaps from rate limits, format changes, or API quirks. The raw API response for every record is preserved exactly as received.

### 2. Faithful speaker attribution
Extract individual speeches from parliamentary transcripts and attribute each one to the correct MP. Attribution should be as complete as the source material allows — documents that remain unattributed must be structurally unattributable, such as appendix link indexes or colonial-era procedural orders with no named author.

### 3. Rich sitting metadata
For every sitting date, capture full session metadata: attendance, permissions to be absent, debate sections, vernacular speeches, and annexures. Both pre- and post-August 2015 API formats are handled faithfully.

### 4. MP identity linking
Connect every speech and attendance record to a canonical MP identity (name, party, parliament number) sourced from parliament.gov.sg.

### 5. High-fidelity markdown
Convert raw HTML records into clean, readable markdown that downstream consumers can trust — stripping artifacts introduced by html2text across three distinct document eras (colonial, mid-era, modern) without losing any substantive content.

### 6. Measurable parsing quality
Ensure parsing quality is measurable and regressions surface before they accumulate. Success rates are tracked per report type across the full corpus, making improvement work verifiable and backslides visible.

---

## Strategies

### Raw first, derive second
Every external API response is stored in a raw response table before any transformation occurs. Entity tables (Report, Speech, Sitting) are pure extensions of their raw counterparts — no fields dropped, no values changed. The source of truth is always recoverable, and re-parsing is cheap: drop the derived rows, rerun the populate step.

### Staged, incremental population
The pipeline runs in discrete stages: fetch → parse → enrich. Each stage can be re-run independently. Skip logic at each stage makes the pipeline idempotent and resumable after failures or interruptions.

### Async HTTP with rate-limit resilience
Fetching thousands of records requires concurrent HTTP. The gateway layer uses async requests with exponential backoff and jitter on 429 responses, so the pipeline self-throttles under load rather than failing hard or hammering the server.

### Stratified, human-supervised parsing refinement
Parsing improvements follow a structured loop: sample the corpus stratified by report type, identify failure groups, apply a fix, validate it against a regression holdout, and accept or roll back. Each cycle requires human review before committing. This keeps the improvement loop tight and prevents silent regressions across the ~22,000-document corpus.

### Format-aware artifact removal
The raw HTML spans three document eras with different artifacts. Fixes are applied as targeted transformations scoped to the artifact each addresses — stripping known separator patterns, merging bold lines split across page breaks, normalising whitespace — rather than globally, which limits blast radius when the source HTML varies.

### Principled attribution hierarchy
For documents that contain no bold speaker markup, attribution follows a deliberate fallback chain:
1. If the `MPs Speaking` header lists exactly one name, attribute the entire body to that MP (adjournment motions, bill first readings, procedural resolutions).
2. If the body follows a known ministerial attribution pattern (ministry heading + name + title), extract the minister from the body.
3. If neither applies, leave unattributed — do not fabricate attribution for multi-speaker appendix documents or structurally authorless procedural orders.

### Diagnostic tooling as a first-class concern
Targeted validation and inspection tools live alongside the main pipeline. Parsing statistics are exported after every run. These tools make it possible to audit specific failure categories by report type without re-running the full pipeline, keeping the feedback loop short.

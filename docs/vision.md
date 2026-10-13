# Vision

A complete, queryable record of Singapore's parliamentary proceedings — from the colonial Legislative Assembly through the present — for researchers studying political history at scale.

---

## Objectives

### 1. Complete corpus coverage
Fetch and store every Hansard entry published by SPRS, across all parliaments and all report types. No gaps from rate limits, format changes, or API quirks. The raw API response for every record is preserved exactly as received.

### 2. Per-utterance speaker index
Extract individual speeches from parliamentary transcripts and attribute each one to the correct speaker. Each `Speech` row represents one utterance — a single content line in the debate — with an `ordinal` that preserves delivery order within the report. The speech table is a queryable, speaker-filtered index over the report content: a researcher can retrieve all speeches by a given speaker across the corpus, sorted by ordinal to read them in context. The `markdown_content` on `Report` is the source of truth; speeches are a derived index over it, not a line-for-line mirror.

Attribution should be as complete as the source material allows. Documents that remain unattributed must be structurally unattributable (appendix link indexes, colonial-era procedural orders with no named author). Structural limits that apply by design:
- `Speech.speaker` may be `None` for utterances where no speaker attribution is possible — speakers are not guaranteed.
- Single-speaker documents are stored as one `Speech` row spanning the full body rather than per-line rows.
- Documents with multiple speakers but no bold speaker markup produce zero `Speech` rows.
- Preamble content (table headers, sitting metadata lines before the first speaker) and blank lines are excluded from `Speech` rows entirely.

### 3. Rich sitting metadata
For every sitting date, capture full session metadata: attendance, permissions to be absent, debate sections, vernacular speeches, and annexures. Both pre- and post-August 2015 API formats are handled faithfully.

### 4. Speaker identity linking
Connect every speech and attendance record to a canonical speaker identity (name, party, parliament number) sourced from parliament.gov.sg.

### 5. High-fidelity markdown
Convert raw HTML records into clean, readable markdown that downstream consumers can trust — stripping artifacts introduced by html2text across three distinct document eras (colonial, mid-era, modern) without losing any substantive content.

### 6. Parsing quality
Track parsing success rates per report type across the full corpus so regressions surface before they accumulate and improvement work is measurable.

---

## Strategies

### Raw first, derive second
Every external API response is stored in a raw response table before any transformation occurs. Entity tables (Report, Speech, Sitting) are pure extensions of their raw counterparts — no fields dropped, no values changed. The source of truth is always recoverable, and re-parsing is cheap: drop the derived rows, rerun the populate step.

### Staged, incremental population
The pipeline runs in discrete stages: fetch → parse → enrich. Each stage can be re-run independently. Skip logic at each stage makes the pipeline idempotent and resumable after failures or interruptions.

### Async HTTP with rate-limit resilience
Fetching thousands of records requires concurrent HTTP. The gateway layer uses async requests with exponential backoff and jitter on 429 responses, so the pipeline self-throttles under load rather than failing hard or hammering the server.

### Iterative parsing refinement
Parsing improvements follow a structured loop: inspect failure categories, apply a targeted fix, check per-report-type statistics, and commit. Each cycle is reviewed before merging to keep regressions visible across the ~22,000-document corpus.

### Format-aware artifact removal
The raw HTML spans three document eras with different artifacts. Fixes are applied as targeted transformations scoped to the artifact each addresses — stripping known separator patterns, merging bold lines split across page breaks, normalising whitespace — rather than globally, which limits blast radius when the source HTML varies.

### Principled attribution hierarchy
For documents that contain no bold speaker markup, attribution follows a deliberate fallback chain:
1. If the `MPs Speaking` header lists exactly one name, attribute the entire body to that speaker (adjournment motions, bill first readings, procedural resolutions).
2. If the body follows a known ministerial attribution pattern (ministry heading + name + title), extract the minister from the body.
3. If neither applies, leave unattributed — do not fabricate attribution for multi-speaker appendix documents or structurally authorless procedural orders.

### Diagnostic tooling as a first-class concern
Targeted validation and inspection tools live alongside the main pipeline. Parsing statistics are exported after every run. These tools make it possible to audit specific failure categories by report type without re-running the full pipeline, keeping the feedback loop short.

---

## Measuring progress

Last recalibrated 13 October 2026, after the refetch of skipped records and the guarded re-parse. Rerun the checks below before claiming any objective is met, and update this section when the figures move.

### The three numbers

`scripts/attribution_text_share.py` prints all three for Parliaments 0 to 11. Quote all three together. Never quote the first on its own.

| Metric | What it counts | 13 Oct 2026 |
|---|---|---|
| ADR 0001 rate | Linked rows / rows with a speaker string, minus "hon. Member(s)" and strings starting with "(" or "_" ([ADR 0001](adr/0001-attribution-denominator.md)) | 564,509 / 578,359 = 97.61% |
| All-rows rate | Linked rows / every speech row, NULL-speaker rows included | 564,509 / 624,332 = 90.42% |
| Text share | Characters of body text in a linked row / characters of body text in every report with markdown, including reports with no rows | 96.81% of 188.1M |

Text share is the number that answers objective 2 and 4 together: how much of the record a researcher can retrieve by speaker. The ADR 0001 rate has a known weakness. Setting a row's speaker to NULL removes it from the denominator, so the rate rises when the parser gives up on a line. The 13 October procedural repairs moved about 29,000 rows to NULL and raised the rate from 97.02% to 97.42%. Some of those rows really have no speaker. The other two numbers keep that honest.

Text share overstates too. The second audit ([north-star-audit-2026-10-13.md](report/north-star-audit-2026-10-13.md)) found it about 1.7 points high: its denominator is the markdown after the parser's own start line, so text html2text lost is invisible, and a report collapsed to one speaker counts its whole body as attributed. Its strict text share is 95.12%, and about 94.6% after hand-checked precision. None of the three numbers says whether a link is right.

Where the body text goes, 13 October 2026: 96.81% in linked rows, 0.76% in rows with an unlinked speaker string, 0.11% in ADR-excluded rows, 0.95% in rows with no speaker, 0.15% in reports with no rows, and 1.22% dropped inside reports that have rows (preamble, headings, labels, and text before the first speaker).

### What "parsed" means in each check

None of the automated checks tests that text sits under the right speaker. Read each pass as the narrow claim it is.

| Check | Passes when | Misses |
|---|---|---|
| `scripts/diagnose.py` | A title line is found | Zero or wrong speeches; it discards the `get_speeches` output |
| `scripts/run_sanity_check.py` | Title found, at least one speech, no NULL speaker, on a fixed sample | Wrong speaker or lost text; it rewards crediting procedural lines to the last speaker |
| `scripts/run_no_speech_validation.py`, `scripts/run_exclusion_sanity_check.py` | A zero-row report has no bold speaker markup | Speeches without bold labels |
| `scripts/trace_speaker_links.py` | Stored links equal what the resolver returns today | Whether the resolver is right; role-context rows are not re-evaluated |

The only correctness evidence is by hand. `plans/link-precision-audit.md` read 613 linked rows: 613 name strings mapped to the right person, and 98.4% of rows carried text that person said (Wilson 97.0% to 99.1%). `plans/parser-strata-audit.md` read 438 reports: 13.3% had a major defect. Both predate the 13 October rebuilds and neither covers reports with no rows. The second audit read 100 fresh rows after the rebuilds: 75 of 80 linked rows right (93.8%, Wilson 86.2% to 97.3%), 0 linked to the wrong person, and 20 of 20 unlinked rows correctly unlinked. All five errors were procedural, list or stage-direction text credited to a speaker. Quote 93.8% as the current precision.

### Verdict against the objectives, records before 10 September 2012

From two independent audits on 13 October 2026. The second ran after that day's fixes (22 zero-row debates parsed, 1,691 skipped records refetched, 6,615 stale reports re-parsed); its findings are in [north-star-audit-2026-10-13.md](report/north-star-audit-2026-10-13.md).

| Objective | Verdict |
|---|---|
| 1. Complete corpus coverage | Mostly. 21,708 records are stored and 21,693 have text, after refetching 1,691 records the search had skipped. 15 came back from SPRS with empty or no content. About 147 Parliament 12 search hits before 10 September 2012 were never refetched. Completeness against SPRS itself is not independently checked. |
| 2. Per-utterance speaker index | Partly. 20,353 of 20,918 reports with markdown have rows. 1.22% of body text is dropped inside reports that have rows. 2,078 reports keep rows from an older parser because the re-parse guard refused them. |
| 3. Sitting metadata | Partly. Attendance is present for all 1,333 sittings with HTML. The PTBA list, sections, annexures and vernaculars are empty for all of them. |
| 4. Speaker identity linking | Mostly. 0 of 80 sampled links point to the wrong person, but 93.8% of linked rows carry text that person said: procedural, list and stage-direction lines inherit a speaker. Stored rows match the current parser except in the 2,078 refused reports. |
| 5. High-fidelity markdown | Partly. The conversion loses 0.41% of HTML word tokens; 120 reports lose more than 5% and report 22103 loses 97.7%. Deleting `&nbsp;` glues words together in 18,044 reports. |
| 6. Parsing-quality tracking | No. The checks above measure structure, not correctness. |

Overall: partly met. Text from 10 September 2012 on is out of this verdict; it was never fetched ([post-2012-text.md](report/post-2012-text.md)).

### Gaps, by who owns them

- The source imposes: unnamed chairs ("The Chairman" where the report gives no chair, about 12,000 rows), collective "hon. Members", bare "Mr Deputy Speaker" on two-holder days, annex pages that are lists of links, procedural lines with no speaker.
- The project chose: the ADR 0001 denominator, dropping text before the first speaker, collapsing single-speaker reports into one row, and a pass that means only that a title line was found.
- The project missed, and these are the next work:
  1. 2,078 reports keep rows from an older parser. The guarded re-parse of 13 October rebuilt 6,615 stale reports and refused the rest: 1,954 by the F18 guard (the new parse drops a body line the stored rows hold, or yields nothing), 87 that step 6b refused, 34 where a re-parse would undo a direct edit, and 3 where it would bring back deleted rows. Each needs a parser fix before it can be rebuilt. The plan, the stored rows of every rebuilt report and two full `pg_dump` backups from before the write were kept outside the repo on 13 October; they are temporary unless moved.
  2. Text from 10 September 2012 on. Commit 2979c57 sends the topic id as a JSON body; the fetcher still sends the trailing `#` and reads `htmlContent`, which sprs3 records leave empty ([post-2012-text.md](report/post-2012-text.md)).
  3. The parser drops 1.22% of body text inside reports with rows: text before the first speaker, headings and other lines it skips. The split between them is not measured.
  4. Unbolded speaker labels and lists that inherit the last speaker (P2 and P3 in `plans/link-precision-audit.md`). Annex tables, division lists and clause text still go to the last speaker, often "Mr Speaker", and "X rose -" stage directions are stored as linked speech (781 to 1,001 rows).
  5. `utils/markdown_parser.py` deletes `&nbsp;` instead of replacing it with a space, gluing words at about 414,000 places.
  6. The ADR 0001 rule that drops speaker strings starting with "_" also drops real names written with a leading underscore, such as "__Dr Teo Ho Pin".
  7. About 147 Parliament 12 search hits before 10 September 2012 were never refetched.
  8. In report 24248 the fallback start line drops Gan Kim Yong's opening speech, because his label merged into the heading.

### Where more work stops paying

Published peers report less than this project. The Knesset corpus reports 94.5% matched with a hand-checked audit; the Glasgow UK Hansard work reports 89.3% for the Commons; ParlaMint, the Australian Hansard datasets and TheyWorkForYou publish no linking rate. None found resolves an unnamed presiding officer to a person: ParlaMint tags the role, the Knesset corpus flags the chair, and Spain's ParlaMint corpus leaves them blank. So work on unnamed chairs, or resolver tuning that moves the rate by tenths of a point, is past the point of value. Work that moves text share, coverage or measured precision is not.

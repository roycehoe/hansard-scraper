# Vision

A complete, queryable record of Singapore's parliamentary proceedings — from the colonial Legislative Assembly through the present — for researchers studying political history at scale.

---

## Objectives

### 1. Complete corpus coverage
Fetch and store every Hansard entry published by SPRS, across all parliaments and all report types. No gaps from rate limits, format changes, or API quirks. The raw API response for every record is preserved exactly as received.

### 2. Per-utterance speaker index
Extract individual speeches from parliamentary transcripts and attribute each one to the correct speaker. Each `Speech` row represents one utterance — a single content line in the debate — with an `ordinal` that preserves delivery order within the report. The speech table is a queryable, speaker-filtered index over the report content: a researcher can retrieve all speeches by a given speaker across the corpus, sorted by ordinal to read them in context. The `markdown_content` on `Report` is the source of truth; speeches are a derived index over it, not a line-for-line mirror.

Attribution should be as complete as the source material allows. Documents that remain unattributed must be structurally unattributable (appendix link indexes, colonial-era procedural orders with no named author). Structural limits that apply by design:
- `Speech.speaker` may be `None` for utterances where no speaker attribution is possible. Speakers are not guaranteed. A row's `kind` says what a row with no speaker is ([ADR 0009](adr/0009-speech-kind-column.md)). The parser sets it on every row since `2eef141`; stored rows get it when write #3 ships.
- Single-speaker documents are stored as one `Speech` row spanning the full body rather than per-line rows.
- Documents with multiple speakers but no bold speaker markup produce zero `Speech` rows.
- The report's own title line, the report header fields and blank lines get no `Speech` row. The parser has kept text before the first speaker as rows with no speaker since `e37853a` ([ADR 0008](adr/0008-text-before-the-first-speaker-kept.md)); the stored rows keep dropping it until write #3 ships.

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

Last recalibrated 16 October 2026, after the overnight rehearsal of write #3 of the speech fidelity loop ([speech-fidelity-loop.md](report/speech-fidelity-loop.md)). The stored rows are the rows after write #2 of 15 October. Write #2 shipped F4 (paragraphs cut by a column or page marker), F5, D1, D2, F2b and WS1 to WS6 (the speaker-label and heading fixes): 3,416 reports, 28,858 updates, 24,402 deletes and 109 inserts. Write #3 is the stack of parser fixes committed from 15 October on, the `kind` column ([ADR 0009](adr/0009-speech-kind-column.md)) and changes A to E of the decision review. It is rehearsed on a replica and not shipped, so its figures sit beside the stored ones and replace them once it ships. Round 1 before write #2 took the report header table out of single-speaker rows, undid html2text escapes, closed bare ampersands and kept link text without its URL, and updated 9,979 stored rows in 11,779 reports. Round 0 before it turned `&nbsp;` into a space in 3,315 older-system reports. The 14 October non-speech repair before it gave no speaker to 12,245 stored rows that were procedural text, editorial notes or "rose" chamber events (`be4d7dd`, and a targeted UPDATE of the stored rows; the plan is `plans/peer-learnings-brief.md`). Rerun the checks below before claiming any objective is met, and update this section when the figures move.

### The three numbers

`scripts/attribution_text_share.py` prints all three for Parliaments 0 to 11. Quote all three together. Never quote the first on its own.

| Metric | What it counts | Stored, 15 Oct 2026, after write #2 | Write #3 rehearsal, 16 Oct 2026, not shipped |
|---|---|---|---|
| ADR 0001 rate | Linked rows / rows with a speaker string, minus "hon. Member(s)" and strings starting with "(" or "_" ([ADR 0001](adr/0001-attribution-denominator.md)) | 537,701 / 550,163 = 97.73% | 526,807 / 538,255 = 97.87% |
| All-rows rate | Linked rows / every speech row, NULL-speaker rows included | 537,701 / 607,295 = 88.54% | 526,807 / 607,756 = 86.68% |
| Text share | Characters of body text in a linked row / characters of body text in every report with markdown, including reports with no rows. The denominator leaves out the report header fields (`Title:`, `MPs Speaking:`) since 15 October, and, since commit `0e4a110`, the script leaves the `(proc text)` tag out of the count | 181,551,794 / 186,295,828 = 97.45% | 181,359,552 / 186,290,919 = 97.35% |

On the old definition, which counted header fields as body text, the same stored rows after round 0 gave 96.59%. The header fields were 1.72M of 188.1M characters. Text share is the number that answers objective 2 and 4 together: how much of the record a researcher can retrieve by speaker. The ADR 0001 rate has a known weakness. Setting a row's speaker to NULL removes it from the denominator, so the rate rises when the parser gives up on a line. The 13 October procedural repairs moved about 29,000 rows to NULL and raised the rate from 97.02% to 97.42%. Some of those rows really have no speaker. The other two numbers keep that honest. The 14 October non-speech repair did the same on purpose: the ADR 0001 rate rose from 97.61% to 97.74% while the all-rows rate fell from 90.42% to 88.88% and text share from 96.81% to 96.58%, because about 9,600 linked rows in Parliaments 0 to 11 held text no member spoke.

Write #3 lowers the all-rows rate and text share on purpose, and raises the ADR 0001 rate for the reason above. Before the A to E changes a rehearsal of plan v2 gave 97.85%, 86.70% and 97.35%. The all-rows rate falls because its denominator gains no-speaker rows: text before the first speaker ([ADR 0008](adr/0008-text-before-the-first-speaker-kept.md)), chamber events cut out of paragraphs and procedural lines cut out of collapsed rows ([ADR 0007](adr/0007-non-speech-lines-get-no-speaker.md)). Text share falls because oath rolls, footnotes, procedural lines and chamber events leave the rows of the member they were credited to. No speech is lost, and the user accepted the drop by design on 16 October 2026. The breakdown by cause is in the [round log](report/speech-fidelity-loop.md).

Text share overstates too. The second audit ([north-star-audit-2026-10-13.md](report/north-star-audit-2026-10-13.md)) found it about 1.7 points high: its denominator is the markdown after the parser's own start line, so text html2text lost is invisible, and a report collapsed to one speaker counts its whole body as attributed. Its strict text share is 95.12%, and about 94.6% after hand-checked precision. None of the three numbers says whether a link is right.

Where the body text goes, Parliaments 0 to 11, stored rows after write #2 (15 October 2026): 97.45% in linked rows, 0.72% in rows with an unlinked speaker string, 0.10% in ADR-excluded rows, 1.21% in rows with no speaker, 0.11% in reports with no rows, and 0.40% dropped inside reports that have rows (headings, labels and other lines the parser skips). After write #3, in the rehearsal: 97.35% in linked rows, 0.67% in rows with an unlinked speaker string, 0.05% in ADR-excluded rows, 1.63% in rows with no speaker, 0.11% in reports with no rows, and 0.19% dropped inside reports that have rows. Every step that changes or drops source text, with its cost, whether it can be undone and who decided it, is in [data-loss-register.md](data-loss-register.md).

Rows by kind ([ADR 0009](adr/0009-speech-kind-column.md)), whole speech table, after write #3 in the rehearsal. A NULL speaker no longer means one thing, so the count of speech rows with no speaker stands apart from the rows that are not speech. A row with a speaker is always SPEECH.

| Kind | Rows |
|---|---|
| SPEECH, speaker known | 963,399 |
| SPEECH, speaker NULL | 488 |
| PROCEDURAL | 46,833 |
| CHAMBER_EVENT | 5,794 |
| EDITORIAL_NOTE | 2,286 |
| DOCUMENT_TEXT | 2,584 |
| HEADING | 2,570 |
| UNCLASSIFIED | 20,579 |
| kind NULL (reports write #3 did not rebuild) | 4,176 |

### What "parsed" means in each check

None of the automated checks tests that text sits under the right speaker. Read each pass as the narrow claim it is.

| Check | Passes when | Misses |
|---|---|---|
| `scripts/diagnose.py` | A title line is found | Zero or wrong speeches; it discards the `get_speeches` output |
| `scripts/run_sanity_check.py` | Title found, at least one speech, no NULL speaker, on a fixed sample | Wrong speaker or lost text; it rewards crediting procedural lines to the last speaker |
| `scripts/run_no_speech_validation.py`, `scripts/run_exclusion_sanity_check.py` | A zero-row report has no bold speaker markup | Speeches without bold labels |
| `scripts/trace_speaker_links.py` | Stored links equal what the resolver returns today | Whether the resolver is right; role-context rows are not re-evaluated |
| `scripts/check_link_plausibility.py` | It always passes; it lists linked rows whose person was absent or unlisted that sitting, unlinked speaker strings outside the known-unlinkable classes, and sittings with a short attendance list | Wrong links to someone who was present; it cannot tell a wrong link from a wrong attendance row. On 14 October it flagged 378 (report, person) pairs, and a 30-pair sample was 24 attendance errors, 0 link errors |

The only correctness evidence is by hand. `plans/link-precision-audit.md` read 613 linked rows: 613 name strings mapped to the right person, and 98.4% of rows carried text that person said (Wilson 97.0% to 99.1%). `plans/parser-strata-audit.md` read 438 reports: 13.3% had a major defect. Both predate the 13 October rebuilds and neither covers reports with no rows. The second audit read 100 fresh rows after the rebuilds: 75 of 80 linked rows right (93.8%, Wilson 86.2% to 97.3%), 0 linked to the wrong person, and 20 of 20 unlinked rows correctly unlinked. All five errors were procedural, list or stage-direction text credited to a speaker. Quote 93.8% as the last measured precision of linked rows; the 14 October non-speech repair targets that error class. Round 2 of the speech fidelity loop read 5,934 rows against the source and put Tier A errors (wrong speaker, lost or duplicated text, a chamber event or a first reading credited to a speaker) at 1.97% of rows weighted, with an upper bound of 2.58%. That is an error rate over all rows, so it does not replace the linked-row precision.

### Parliaments 12 to 14, beside the headline

The 14 October load added text from 10 September 2012 on. Same filter as the ADR 0001 rate, then the all-rows rate, then text share, from `scripts/attribution_text_share.py`:

| Scope | ADR 0001 rate | All-rows rate | Text share |
|---|---|---|---|
| Parliament 12 (whole), stored after write #2 | 82,817 / 83,749 = 98.89% | 82,817 / 85,640 = 96.70% | 98.95% |
| Parliament 12 from 10 Sep 2012, before the non-speech repair | 72,013 / 72,778 = 98.95% | | |
| Parliament 13, stored after write #2 | 133,188 / 135,645 = 98.19% | 133,188 / 138,337 = 96.28% | 99.06% |
| Parliament 14, stored after write #2 | 208,195 / 210,228 = 99.03% | 208,195 / 213,322 = 97.60% | 99.21% |
| Parliament 12, write #3 rehearsal | 82,170 / 83,077 = 98.91% | 82,170 / 86,479 = 95.02% | 29,041,974 / 29,443,992 = 98.63% |
| Parliament 13, write #3 rehearsal | 132,208 / 134,550 = 98.26% | 132,208 / 139,512 = 94.76% | 41,810,359 / 42,329,130 = 98.77% |
| Parliament 14, write #3 rehearsal | 206,961 / 208,894 = 99.07% | 206,961 / 214,962 = 96.28% | 59,402,698 / 60,051,708 = 98.92% |

The plan projected 99.1 to 99.3 for Parliament 12 from the cutoff, 98.1 to 99.1 for Parliament 13 and 98.6 for Parliament 14. Parliament 12 from the cutoff is about 110 rows short: "The Chairman" leaves 566 rows unlinked there, and 61 "[Deputy Speaker" parse-noise rows stay in the denominator (77 across Parliaments 12 and 13, where the plan expected 16). Across the new rows the largest unlinked groups are "The Chairman" with 4,018 (no chair named in the report), bare "Mr Deputy Speaker" with 1,119 on days with two holders ([ADR 0002](adr/0002-role-holder-attribution.md) leaves them), "[Deputy Speaker" with 77, "Mr Chairman" with 44, and 5 "Mdm Speaker" rows that are Hansard misprints for "Mdm Deputy Speaker" and stay unlinked. No hand audit covers these rows yet.

Across the whole table on 14 October, before the writes of 15 October: 1,068,887 speech rows, 1,007,992 with a speaker string, 986,424 of them linked (97.9%). After write #2 the table holds 1,044,594 speech rows. Attendance: 134,916 of 135,072 linked (99.88%); write #3 deletes 45 junk attendance rows.

The decisions, run order, judgement calls and evidence for this load are in [post-2012-load.md](report/post-2012-load.md).

### Verdict against the objectives, records before 10 September 2012

From two independent audits on 13 October 2026. The second ran after that day's fixes (22 zero-row debates parsed, 1,691 skipped records refetched, 6,615 stale reports re-parsed); its findings are in [north-star-audit-2026-10-13.md](report/north-star-audit-2026-10-13.md).

| Objective | Verdict |
|---|---|
| 1. Complete corpus coverage | Mostly. Corpus-wide, 41,811 distinct records are stored from 47,402 search hits, and 41,683 have text. 128 have none: 106 `atbp` records (the newer system gives them no topic text) and 22 others, 8 of them newer-system ids that return no text: 6 the API answers with HTTP 400 on every attempt, and 2 old rows (`bill-intro-1318#`, `ministerial-statement-1902#`) whose items are stored with text under the new ids `budget-1318#` and `clarification-1902#`. The 111 older-system Parliament 12 hits before 10 September 2012 are now added. Completeness against SPRS itself is not independently checked. |
| 2. Per-utterance speaker index | Partly. 20,353 of 20,918 reports with markdown have rows. 0.40% of body text is dropped inside reports that have rows in the stored rows. The parser has kept text before the first speaker as rows since `e37853a` ([ADR 0008](adr/0008-text-before-the-first-speaker-kept.md)); the stored rows change when write #3 ships, and the figure falls to 0.19% in the rehearsal. 2,078 reports keep rows from an older parser because the re-parse guard refused them; write #3 rebuilds many of them and holds 174. |
| 3. Sitting metadata | Partly. Attendance is present for all 1,333 sittings with HTML. The PTBA list, sections, annexures and vernaculars are empty for all of them. The 386 sittings from 10 September 2012 are now filled with metadata and section lists, and attendance for them comes from the structured list. 19,874 of 19,880 sitting sections pair with a stored report ([post-2012-sections-gap.md](report/post-2012-sections-gap.md)). |
| 4. Speaker identity linking | Mostly. 0 of 80 sampled links point to the wrong person, and 93.8% of linked rows carried text that person said before the 14 October non-speech repair, which removed the speaker from 12,245 procedural, editorial-note and chamber-event rows; lists inside a speech still inherit it. Write #3 will unlink the 465 stored rows of ten reports where the speaker is known to be wrong. Stored rows match the current parser except in the 2,078 refused reports. |
| 5. High-fidelity markdown | Partly. The conversion loses 0.41% of HTML word tokens; 120 reports lose more than 5% and report 22103 loses 97.7%. Round 0 of the speech fidelity loop stopped `&nbsp;` gluing words in 3,315 older-system reports; 149 more are held back. After round 1 the glued-word detector found 31.8 pipeline hits per million tokens and the punctuation detector 12.66, against a source rate of 6.24; the write #3 rehearsal gives 9.84 and 3.66. Round 2 read 316 reports (5,934 rows) after write #2. Weighted by rows, with a first reading credited to its presenter counted as Tier A, Tier A is 1.97% (upper bound 2.58%) and Tier B 1.72% (2.60%); weighted by characters, which now gates, Tier A is 0.77% (1.04%) and Tier B 0.88% (1.48%). Both gates fail. Round 3, provisional and read on the rehearsal copy of write #3, pools 548 reports and 9,824 rows: Tier A is 0.79% by characters (bound 1.88%) and fails on one report, 22149; Tier B is 0.90% (1.42%) and passes, with both detectors under their source rates. |
| 6. Parsing-quality tracking | No. The checks above measure structure, not correctness. |

Overall: partly met. This verdict covers records before 10 September 2012. Text from that date on is now loaded and is measured beside the headline above, with no hand audit yet ([post-2012-text.md](report/post-2012-text.md)).

### Gaps, by who owns them

- The source imposes: unnamed chairs ("The Chairman" where the report gives no chair, about 12,000 rows), collective "hon. Members", bare "Mr Deputy Speaker" on two-holder days, annex pages that are lists of links, procedural lines with no speaker.
- The project chose: the ADR 0001 denominator, collapsing single-speaker reports into one row, and a pass that means only that a title line was found. Dropping text before the first speaker was a choice until 15 October 2026, when [ADR 0008](adr/0008-text-before-the-first-speaker-kept.md) reversed it.
- The project missed, and these are the next work:
  1. 2,078 reports keep rows from an older parser. The guarded re-parse of 13 October rebuilt 6,615 stale reports and refused the rest: 1,954 by the F18 guard (the new parse drops a body line the stored rows hold, or yields nothing), 87 that step 6b refused, 34 where a re-parse would undo a direct edit, and 3 where it would bring back deleted rows. Each needs a parser fix before it can be rebuilt. The plan, the stored rows of every rebuilt report and two full `pg_dump` backups from before the write were kept outside the repo on 13 October; they are temporary unless moved.
  2. The stored rows drop 0.40% of body text inside reports with rows (after write #2). The parser has kept text before the first speaker as rows since `e37853a`, and write #3 brings the stored rows to 0.19% when it ships. Headings, time stamps, chair annotations and question numbers still get no row (decision review, finding 7, open). The split between the remaining classes is not measured.
  3. Unbolded speaker labels and lists that inherit the last speaker (P2 and P3 in `plans/link-precision-audit.md`). The 14 October repair gave no speaker to the lines after a procedural line, to whole-line editorial notes and to "rose" stage directions; what remains is unbolded labels, lists inside a member's speech, 83 "Certificate of Urgency handed in." rows, 4 rows in two stale reports (26467, 27699) the repair could not match, and 6 rows of a Budget statement in report 22691 resumed after a suspension, now unattributed instead of credited to Mr Speaker. Annex tables after a heading are ministers' own tables in written answers and stay with them.
  4. Glued and split words, markup residue, lost text and wrong speakers that the speech fidelity loop ([speech-fidelity-loop.md](report/speech-fidelity-loop.md)) is working through. Round 0 fixed `&nbsp;` in 3,315 older-system reports and cut the detectors' pipeline hits from 35,993 to 2,041 (dictionary test) and from 14,569 to 824 (punctuation test). Round 1 fixed the header table in single-speaker rows, html2text escapes, bare ampersands and link URLs, in 11,779 reports. Write #2 fixed F4 (a paragraph cut across rows at a column or page marker, the largest class), F5 and the speaker-label classes WS1 to WS6. Round 2 read 316 reports and found Tier A and Tier B above their gates. Write #3 fixes the round 2 classes (PA1 to PA7, TB1, TB2, TC1) and adds the `kind` column. Still open after it: Tier A (round 3, provisional: 0.79% by characters, bound 1.88%; the classes are headings and footnote lines read as speaker labels, older-system first readings credited to their presenter and procedural lines that miss an anchor) and review findings 6 to 13 (the heading exemption in Tier C, text dropped with no row, column numbers, vernacular marking, row identity, the 1,568-report rebuild sample, `footNote` and `mpNames`, small points). The loop stops when Tier A's weighted upper bound, by characters, is 1% or less, Tier B's is 2% or less with both detectors below their source typo rates, and every remaining class is listed with its corpus count here; round 6 is a cap.
  5. The ADR 0001 rule that drops speaker strings starting with "_" also drops real names written with a leading underscore. Round 0 removed the stray `__` from 33 such labels, "__Dr Teo Ho Pin" among them. One name is left, `_S_ hawn Huang Wei Zhong (Jurong)` on 2 rows; the other 10 strings starting with "_" are italic headings.
  6. In report 24248 the fallback start line dropped Gan Kim Yong's opening speech, because his label merged into the heading. The parser now keeps the speech as 30 rows with no speaker and kind SPEECH (`72d4d64`), and write #3 stores them. The report is on the per-report Tier A list in [data-loss-register.md](data-loss-register.md). The speech stays unattributed.
  7. For 465 stored rows in ten reports the speaker is known to be wrong. The right speaker is known for all of them except the 7 rows of 42017, a notice of motion that no member spoke, and it is not stored. Write #3 unlinks the rows, and an override file with the right speakers is not built.

### Where more work stops paying

Published peers report less than this project. The Knesset corpus reports 94.5% of speaker strings matched to its member database, and 98.3% speaker-name correctness on a hand-checked test set; a 2026 paper linking the UK Hansard corpus to MPs reports 89.3% for the Commons; ParlaMint, the Australian Hansard datasets and TheyWorkForYou publish no linking rate. None found resolves an unnamed presiding officer to a person: ParlaMint tags the role, the Knesset corpus flags the chair, and Spain's ParlaMint corpus leaves them blank. So work on unnamed chairs, or resolver tuning that moves the rate by tenths of a point, is past the point of value. Work that moves text share, coverage or measured precision is not. What peer projects do that this one does not is in [peer-projects.md](peer-projects.md).

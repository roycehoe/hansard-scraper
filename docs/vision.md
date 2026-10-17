# Vision

A complete, queryable record of Singapore's parliamentary proceedings — from the colonial Legislative Assembly through the present — for researchers studying political history at scale.

---

## Objectives

### 1. Complete corpus coverage
Fetch and store every Hansard entry published by SPRS, across all parliaments and all report types. No gaps from rate limits, format changes, or API quirks. The raw API response for every record is preserved exactly as received.

### 2. Per-utterance speaker index
Extract individual speeches from parliamentary transcripts and attribute each one to the correct speaker. Each `Speech` row represents one utterance — a single content line in the debate — with an `ordinal` that preserves delivery order within the report. The speech table is a queryable, speaker-filtered index over the report content: a researcher can retrieve all speeches by a given speaker across the corpus, sorted by ordinal to read them in context. The `markdown_content` on `Report` is the source of truth; speeches are a derived index over it, not a line-for-line mirror.

Attribution should be as complete as the source material allows. Documents that remain unattributed must be structurally unattributable (appendix link indexes, colonial-era procedural orders with no named author). Structural limits that apply by design:
- `Speech.speaker` may be `None` for utterances where no speaker attribution is possible. Speakers are not guaranteed. A row's `kind` says what a row with no speaker is ([ADR 0009](adr/0009-speech-kind-column.md)). The parser sets it on every row since `2eef141`, and write #3 stored it on 16 October 2026 for every report it rebuilt.
- Single-speaker documents are stored as one `Speech` row for the speaker's text rather than per-line rows. The report title is dropped from it, and procedural lines and a first reading become rows of their own with no speaker.
- Documents with multiple speakers but no bold speaker markup produce zero `Speech` rows.
- The report's own title line, the report header fields and blank lines get no `Speech` row. The parser has kept text before the first speaker as rows with no speaker since `e37853a` ([ADR 0008](adr/0008-text-before-the-first-speaker-kept.md)); write #3 stored it on 16 October 2026 for every report it rebuilt.

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

Last recalibrated 17 October 2026, after write #7 of the speech fidelity loop ([speech-fidelity-loop.md](report/speech-fidelity-loop.md)), write #6, write #5, write #4 and the ten writes of the data sanity fix run. Write #4 and the fix run were committed on the remote from 07:48 to 08:10 on 17 October, write #5 at 09:29, write #6 at 11:19 and write #7 at 16:03. Each stored figure below equals its rehearsal's. Write #2 shipped F4 (paragraphs cut by a column or page marker), F5, D1, D2, F2b and WS1 to WS6 (the speaker-label and heading fixes): 3,416 reports, 28,858 updates, 24,402 deletes and 109 inserts. Write #3 is the stack of parser fixes committed from 15 October on, the `kind` column ([ADR 0009](adr/0009-speech-kind-column.md)) and changes A to E of the decision review. Its stored figures equal its rehearsal's. Write #4 is the three parser fixes of cycle 4 (`2ec5fe8`, `73ed1d6` and `1220161`) and the rebuild of 42 reports that write #3 held. It shipped at 07:48 on 17 October. The plan applies 2,923 reports and writes 8,729 speech updates (3,234 of them ordinal only), 361 kind-only updates, 443 deletes, 66 inserts and 25 report markdowns. Write #5 is the w5 parser patches (`167e2e8` to `1c71189`) and the 188 stage 8 links of patch 05. It shipped at 09:29 on 17 October (lock 124 s, 56 checks ok), its stored figures equal its rehearsal's, and the replica equals the remote by table hashes. It applies 2,910 reports and writes 11,523 row updates (11,335 planned content updates plus the 188 links), 30,769 ordinal-only updates, 145 kind-only rows, 12 ordinal_kind rows, 325 deletes, 3,511 inserts, 1,014 report markdowns and 7 sitting markdowns. It holds 181 reports. Write #6 is the p06 and p04 fixes (`d20cb43` and `5515de4`) and a rebuild of the reports write #5 held on them. It shipped at 11:19 on 17 October (lock 10.0 s, 52 checks ok in the rehearsal and again in the commit), and its stored figures equal its rehearsal's. It applies 55 reports and writes 131 row updates, 55 report markdowns and 5 sitting markdowns, with no delete, insert, kind change or link, so the speech table stays at 1,050,712 rows. It holds 123 reports: 2 new (38147, 38222) and the 121 older ones. Its attendance part (`7d6f305`) set 496 stored speaker names to the stage 7 names, and the replica equals the remote by table hashes. Write #7 is DS2-01 (`7ce66a3`, unbolded labels with a language note) and DS2-02 (`27d6c5e`, older-system entity characters kept). It shipped at 16:03 on 17 October (lock 108.1 s, total 135.3 s, 52 checks ok in the rehearsal and again in the commit), and its stored figures equal its rehearsal's. It applies 1,132 reports and writes 8,001 row updates: 7,868 change characters only, 36 label rows change speaker and lose the label from their text, and 97 rows after a label change speaker. It writes no insert, delete, kind or ordinal change, 1,118 report markdowns and 131 sitting markdowns, and the speech table stays at 1,050,712 rows. It holds 126 reports: 3 new (37959, 20889, 43635) and the 123 older ones, none released. Attendance is re-derived to the same 135,083 rows, so it writes none. The replica equals the remote by table hashes. The figures before it stay beside them. Round 1 before write #2 took the report header table out of single-speaker rows, undid html2text escapes, closed bare ampersands and kept link text without its URL, and updated 9,979 stored rows in 11,779 reports. Round 0 before it turned `&nbsp;` into a space in 3,315 older-system reports. The 14 October non-speech repair before it gave no speaker to 12,245 stored rows that were procedural text, editorial notes or "rose" chamber events (`be4d7dd`, and a targeted UPDATE of the stored rows; the plan is `plans/peer-learnings-brief.md`). Rerun the checks below before claiming any objective is met, and update this section when the figures move.

### The three numbers

`scripts/attribution_text_share.py` prints all three for Parliaments 0 to 11. Quote all three together. Never quote the first on its own.

| Metric | What it counts | Before write #3, 15 Oct 2026, after write #2 | Stored, 16 Oct 2026, after write #3 | Stored, 17 Oct 2026, after write #4 | Stored, 17 Oct 2026, after write #4 and DS-04 | Stored, 17 Oct 2026, after write #5 | Stored, 17 Oct 2026, after write #6 | Stored, 17 Oct 2026, after write #7 |
|---|---|---|---|---|---|---|---|---|
| ADR 0001 rate | Linked rows / rows with a speaker string, minus "hon. Member(s)" and strings starting with "(" or "_" ([ADR 0001](adr/0001-attribution-denominator.md)) | 537,701 / 550,163 = 97.73% | 526,807 / 538,255 = 97.87% | 523,056 / 533,817 = 97.98% | 522,435 / 533,183 = 97.98% | 513,404 / 523,420 = 98.09% | 513,398 / 523,414 = 98.09% | 513,405 / 523,415 = 98.09% |
| All-rows rate | Linked rows / every speech row, NULL-speaker rows included | 537,701 / 607,295 = 88.54% | 526,807 / 607,756 = 86.68% | 523,056 / 607,408 = 86.11% | 522,435 / 606,746 = 86.10% | 513,404 / 609,701 = 84.21% | 513,398 / 609,701 = 84.20% | 513,405 / 609,701 = 84.21% |
| Text share | Characters of body text in a linked row / characters of body text in every report with markdown, including reports with no rows. The denominator leaves out the report header fields (`Title:`, `MPs Speaking:`) since 15 October, and, since commit `0e4a110`, the script leaves the `(proc text)` tag out of the count | 181,551,794 / 186,295,828 = 97.45% | 181,359,552 / 186,290,919 = 97.35% | 180,926,723 / 186,290,255 = 97.12% | 180,696,591 / 186,092,895 = 97.10% | 180,788,738 / 186,092,945 = 97.15% | 180,788,469 / 186,092,971 = 97.15% | 180,790,066 / 186,092,963 = 97.15% |

On the old definition, which counted header fields as body text, the same stored rows after round 0 gave 96.59%. The header fields were 1.72M of 188.1M characters. Text share is the number that answers objective 2 and 4 together: how much of the record a researcher can retrieve by speaker. The ADR 0001 rate has a known weakness. Setting a row's speaker to NULL removes it from the denominator, so the rate rises when the parser gives up on a line. The 13 October procedural repairs moved about 29,000 rows to NULL and raised the rate from 97.02% to 97.42%. Some of those rows really have no speaker. The other two numbers keep that honest. The 14 October non-speech repair did the same on purpose: the ADR 0001 rate rose from 97.61% to 97.74% while the all-rows rate fell from 90.42% to 88.88% and text share from 96.81% to 96.58%, because about 9,600 linked rows in Parliaments 0 to 11 held text no member spoke.

Write #3 lowers the all-rows rate and text share on purpose, and raises the ADR 0001 rate for the reason above. Before the A to E changes a rehearsal of plan v2 gave 97.85%, 86.70% and 97.35%. The all-rows rate falls because its denominator gains no-speaker rows: text before the first speaker ([ADR 0008](adr/0008-text-before-the-first-speaker-kept.md)), chamber events cut out of paragraphs and procedural lines cut out of collapsed rows ([ADR 0007](adr/0007-non-speech-lines-get-no-speaker.md)). Text share falls because oath rolls, footnotes, procedural lines and chamber events leave the rows of the member they were credited to. No speech is lost, and the user accepted the drop by design on 16 October 2026. The breakdown by cause is in the [round log](report/speech-fidelity-loop.md).

Write #4 moves the three numbers the same way: the ADR 0001 rate rises from 97.87% to 97.98%, the all-rows rate falls from 86.68% to 86.11% and text share from 97.35% to 97.12%. In Parliaments 0 to 11 the three fixes take 568,484 countable characters out of linked rows (513,428 of them from the first-reading fix) and the release of 42 held reports puts 135,655 back with the members who were speaking. By cause the text-share points are fix 1 -0.014, fix 2 -0.014, fix 3 -0.276 and the release +0.073. No word is lost: each whole-cache check lost none, and 355 words come back in 29 reports. The breakdown by cause is in the [round log](report/speech-fidelity-loop.md).

The DS-04 removal of ten duplicate reports and their 825 speech rows (662 of them in Parliaments 0 to 11) is a data fix, not a parser fix, and moves the three numbers a little further: the ADR 0001 rate stays at 97.98%, the all-rows rate falls from 86.11% to 86.10% and text share from 97.12% to 97.10%. The 662 rows include 621 linked rows and 634 rows that count in the ADR 0001 denominator.

DS-16 then links the 82 "The Chief Minister" rows of 7 June 1956 to David Marshall. Stored on 17 October, after DS-04, DS-08, DS-11, DS-12, G6 and the rest of G5, Parliaments 0 to 11 are at ADR 0001 rate 522,517 / 533,183 = 98.00%, all-rows rate 522,517 / 606,746 = 86.12% and text share 180,732,303 / 186,092,895 = 97.12%. Parliaments 12 to 14 do not move.

Write #5 stored the figures in the fifth column. From the DS-16 state the ADR 0001 rate rises from 98.00% to 98.09%, the all-rows rate falls from 86.12% to 84.21% and text share rises from 97.12% to 97.15%. The ADR 0001 rate rises because italic titles lose their speaker (p07). The all-rows rate falls 1.91 points for two reasons: p07 takes 9,461 title rows off speakers (-1.505 points), and p08 adds 3,418 rows with no speaker to reports that had none (-0.447 points, 3,172 of them in Parliaments 0 to 11). p09 takes 252 linked rows out (-0.006). Text share rises 0.03 points: p05's links (+0.088), p04 (+0.043 and +0.003 with p07) and the title rebase of 22789, 23760 and 43147 (+0.019) outweigh p07 (-0.131). By cause, in Parliaments 0 to 11, linked characters change by p07 -244,459, p05 +163,847, p04 +80,901 (+5,928 with p07), the title rebase +34,803 and p08 +16,225. Patch 02 changes no row, and ordinal shifts change no figure. The detectors read 4.282 and 1.977 per million tokens (275 and 127 hits), against source rates of 106.45 and 6.23. The breakdown by cause is in the [round log](report/speech-fidelity-loop.md).

Write #6 stored the figures in the last column. Against write #5 the ADR 0001 rate stays at 98.09% (513,404 / 523,420 to 513,398 / 523,414), the all-rows rate moves from 84.21% to 84.20% (the numerator loses 6 linked rows, the denominator stays at 609,701) and text share stays at 97.15% (180,788,738 / 186,092,945 to 180,788,469 / 186,092,971, so linked characters fall 269 and the denominator rises 26). The 131 row updates change speech text next to footnote markers and pipe labels, and no row's link. The detectors are unchanged: dictionary 4.282 and punctuation 1.977 per million tokens, the same as after write #5. The attendance names change no figure.

Write #7 stored the figures in the last column. Against write #6 the ADR 0001 rate stays at 98.09% (513,398 / 523,414 to 513,405 / 523,415), the all-rows rate moves from 84.20% to 84.21% (7 more linked rows, the denominator stays at 609,701) and text share stays at 97.15% (180,788,469 / 186,092,971 to 180,790,066 / 186,092,963, so linked characters rise 1,597 and the denominator falls 8). The 36 label rows and the 97 rows after them change speaker; stage 8 links 132 of those 133 rows to the member the label names, and "Inche Rahamat" in 38006 stays unlinked. 59 of the 133 were credited to Mr Speaker before. The 7,868 character-only rows move no link. Parliaments 12 to 14 do not move. The dictionary detector reads 4.266 per million tokens (274 hits), down from 4.282 (275 hits), and the punctuation detector stays at 1.977 (127 hits).

Text share overstates too. The second audit ([north-star-audit-2026-10-13.md](report/north-star-audit-2026-10-13.md)) found it about 1.7 points high: its denominator is the markdown after the parser's own start line, so text html2text lost is invisible, and a report collapsed to one speaker counts its whole body as attributed. Its strict text share is 95.12%, and about 94.6% after hand-checked precision. None of the three numbers says whether a link is right.

Where the body text goes, Parliaments 0 to 11, before write #3 (15 October 2026): 97.45% in linked rows, 0.72% in rows with an unlinked speaker string, 0.10% in ADR-excluded rows, 1.21% in rows with no speaker, 0.11% in reports with no rows, and 0.40% dropped inside reports that have rows (headings, labels and other lines the parser skips). Stored after write #3 (16 October 2026): 97.35% in linked rows, 0.67% in rows with an unlinked speaker string, 0.05% in ADR-excluded rows, 1.63% in rows with no speaker, 0.11% in reports with no rows, and 0.19% dropped inside reports that have rows. In the write #4 rehearsal: 97.12% in linked rows, 0.58% in rows with an unlinked speaker string, 0.05% in ADR-excluded rows, 1.96% in rows with no speaker, 0.11% in reports with no rows, and 0.19% dropped inside reports that have rows. With DS-04 on the same copy: 97.10% in linked rows, 0.58% in rows with an unlinked speaker string, 0.05% in ADR-excluded rows, 1.96% in rows with no speaker, 0.11% in reports with no rows, and 0.20% dropped inside reports that have rows. Every step that changes or drops source text, with its cost, whether it can be undone and who decided it, is in [data-loss-register.md](data-loss-register.md).

Rows by kind ([ADR 0009](adr/0009-speech-kind-column.md)), whole speech table, stored after write #3 (16 October 2026), in the write #4 rehearsal and stored after write #5 (17 October 2026). A NULL speaker no longer means one thing, so the count of speech rows with no speaker stands apart from the rows that are not speech. A row with a speaker is always SPEECH.

| Kind | Rows, after write #3 | Rows, write #4 rehearsal | Rows, stored after write #5 |
|---|---|---|---|
| SPEECH, speaker known | 963,407 | 960,592 | 950,014 |
| SPEECH, speaker NULL | 488 | 488 | 488 |
| PROCEDURAL | 46,868 | 49,841 | 50,381 |
| CHAMBER_EVENT | 5,800 | 5,838 | 5,838 |
| EDITORIAL_NOTE | 2,286 | 3,187 | 3,186 |
| DOCUMENT_TEXT | 2,584 | 2,616 | 5,388 |
| HEADING | 2,570 | 2,570 | 12,358 |
| UNCLASSIFIED | 20,579 | 20,944 | 20,784 |
| kind NULL (reports write #3 did not rebuild) | 4,146 | 2,275 | 2,275 |

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
| Parliament 12 (whole), before write #3 | 82,817 / 83,749 = 98.89% | 82,817 / 85,640 = 96.70% | 98.95% |
| Parliament 12 from 10 Sep 2012, before the non-speech repair | 72,013 / 72,778 = 98.95% | | |
| Parliament 13, before write #3 | 133,188 / 135,645 = 98.19% | 133,188 / 138,337 = 96.28% | 99.06% |
| Parliament 14, before write #3 | 208,195 / 210,228 = 99.03% | 208,195 / 213,322 = 97.60% | 99.21% |
| Parliament 12, stored after write #3 | 82,170 / 83,077 = 98.91% | 82,170 / 86,480 = 95.02% | 29,041,974 / 29,443,992 = 98.63% |
| Parliament 13, stored after write #3 | 132,205 / 134,547 = 98.26% | 132,205 / 139,516 = 94.76% | 41,810,025 / 42,329,130 = 98.77% |
| Parliament 14, stored after write #3 | 206,946 / 208,878 = 99.08% | 206,946 / 214,976 = 96.26% | 59,399,644 / 60,051,708 = 98.91% |
| Parliament 12, write #4 rehearsal | 82,102 / 83,004 = 98.91% | 82,102 / 86,458 = 94.96% | 29,027,236 / 29,443,992 = 98.58% |
| Parliament 13, write #4 rehearsal | 132,194 / 134,536 = 98.26% | 132,194 / 139,509 = 94.76% | 41,808,220 / 42,329,130 = 98.77% |
| Parliament 14, write #4 rehearsal | unchanged | unchanged | unchanged |
| Parliament 12, rehearsal plus DS-04 | 81,947 / 82,849 = 98.91% | 81,947 / 86,295 = 94.96% | 28,965,177 / 29,381,430 = 98.58% |
| Parliaments 13 and 14, rehearsal plus DS-04 | unchanged | unchanged | unchanged |
| Parliament 12, stored after write #5 | 81,997 / 82,823 = 99.00% | 81,997 / 86,393 = 94.91% | 28,981,638 / 29,382,042 = 98.64% |
| Parliament 13, stored after write #5 | 132,221 / 134,533 = 98.28% | 132,221 / 139,566 = 94.74% | 41,817,912 / 42,329,696 = 98.79% |
| Parliament 14, stored after write #5 | 206,970 / 208,883 = 99.08% | 206,970 / 215,052 = 96.24% | 59,407,425 / 60,053,116 = 98.92% |
| Parliament 12, stored after write #6 | 81,997 / 82,823 = 99.00% | 81,997 / 86,393 = 94.91% | 28,981,672 / 29,382,076 = 98.64% |
| Parliament 13, stored after write #6 | 132,221 / 134,533 = 98.28% | 132,221 / 139,566 = 94.74% | 41,818,104 / 42,329,888 = 98.79% |
| Parliament 14, stored after write #6 | 206,969 / 208,882 = 99.08% | 206,969 / 215,052 = 96.24% | 59,407,479 / 60,053,202 = 98.92% |
| Parliament 12, stored after write #7 | 81,997 / 82,823 = 99.00% | 81,997 / 86,393 = 94.91% | 28,981,672 / 29,382,076 = 98.64% |
| Parliament 13, stored after write #7 | 132,221 / 134,533 = 98.28% | 132,221 / 139,566 = 94.74% | 41,818,104 / 42,329,888 = 98.79% |
| Parliament 14, stored after write #7 | 206,969 / 208,882 = 99.08% | 206,969 / 215,052 = 96.24% | 59,407,479 / 60,053,202 = 98.92% |

The plan projected 99.1 to 99.3 for Parliament 12 from the cutoff, 98.1 to 99.1 for Parliament 13 and 98.6 for Parliament 14. Parliament 12 from the cutoff is about 110 rows short: "The Chairman" leaves 566 rows unlinked there, and 61 "[Deputy Speaker" parse-noise rows stay in the denominator (77 across Parliaments 12 and 13, where the plan expected 16). Across the new rows the largest unlinked groups are "The Chairman" with 4,018 (no chair named in the report), bare "Mr Deputy Speaker" with 1,119 on days with two holders ([ADR 0002](adr/0002-role-holder-attribution.md) leaves them), "[Deputy Speaker" with 77, "Mr Chairman" with 44, and 5 "Mdm Speaker" rows that are Hansard misprints for "Mdm Deputy Speaker" and stay unlinked. No hand audit covers these rows yet.

Across the whole table on 14 October, before the writes of 15 October: 1,068,887 speech rows, 1,007,992 with a speaker string, 986,424 of them linked (97.9%). After write #2 the table held 1,044,594 speech rows. After write #3 it holds 1,048,728, of which 967,147 have a speaker string and 948,128 are linked. In the write #4 rehearsal it holds 1,048,351, of which 962,541 have a speaker string and 944,298 are linked; DS-04 takes 825 of those rows out, leaving 1,047,526. Write #5 takes it to 1,050,712, and write #6 and write #7 leave it there. Attendance: 134,916 of 135,027 linked (99.92%), after write #3 deleted 45 junk attendance rows. Stored on 17 October after write #6 and write #7: 135,080 of 135,083 linked (99.998%). The 3 unlinked rows are A.V. Winslow (2) and Andrew Fong (1), who have no Speaker row.

The decisions, run order, judgement calls and evidence for this load are in [post-2012-load.md](report/post-2012-load.md).

### Verdict against the objectives, records before 10 September 2012

From two independent audits on 13 October 2026. The second ran after that day's fixes (22 zero-row debates parsed, 1,691 skipped records refetched, 6,615 stale reports re-parsed); its findings are in [north-star-audit-2026-10-13.md](report/north-star-audit-2026-10-13.md).

| Objective | Verdict |
|---|---|
| 1. Complete corpus coverage | Mostly. Corpus-wide, 41,811 distinct records are stored from 47,402 search hits, and 41,683 have text. 128 have none: 106 `atbp` records (the newer system gives them no topic text) and 22 others, 8 of them newer-system ids that return no text: 6 the API answers with HTTP 400 on every attempt, and 2 old rows (`bill-intro-1318#`, `ministerial-statement-1902#`) whose items are stored with text under the new ids `budget-1318#` and `clarification-1902#`. The 111 older-system Parliament 12 hits before 10 September 2012 are now added. Completeness against SPRS itself is not independently checked. |
| 2. Per-utterance speaker index | Partly. 20,353 of 20,918 reports with markdown have rows. 0.19% of body text is dropped inside reports that have rows in the stored rows, down from 0.40% before write #3. The parser has kept text before the first speaker as rows since `e37853a` ([ADR 0008](adr/0008-text-before-the-first-speaker-kept.md)). 2,078 reports keep rows from an older parser because the re-parse guard refused them; write #3 rebuilt many of them and held 162, and write #4 rebuilds 42 of those. |
| 3. Sitting metadata | Partly. Attendance is present for all 1,333 sittings with HTML. The PTBA list, sections, annexures and vernaculars are empty for all of them. The 386 sittings from 10 September 2012 are now filled with metadata and section lists, and attendance for them comes from the structured list. 19,874 of 19,880 sitting sections pair with a stored report ([post-2012-sections-gap.md](report/post-2012-sections-gap.md)). |
| 4. Speaker identity linking | Mostly. 0 of 80 sampled links point to the wrong person, and 93.8% of linked rows carried text that person said before the 14 October non-speech repair, which removed the speaker from 12,245 procedural, editorial-note and chamber-event rows; lists inside a speech still inherit it. Write #3 unlinked the 465 stored rows of ten reports where the speaker is known to be wrong. Stored rows match the current parser except in the reports write #3 held: 162, and 121 after write #4. |
| 5. High-fidelity markdown | Partly. The conversion loses 0.41% of HTML word tokens; 120 reports lose more than 5% and report 22103 loses 97.7%. Round 0 of the speech fidelity loop stopped `&nbsp;` gluing words in 3,315 older-system reports; 149 more are held back. After round 1 the glued-word detector found 31.8 pipeline hits per million tokens and the punctuation detector 12.66, against a source rate of 6.24; the write #3 rehearsal gave 9.84 and 3.66, and the write #4 rehearsal gives 4.27 and 1.98 against source rates of 106.54 and 6.23. Round 2 read 316 reports (5,934 rows) after write #2. Weighted by rows, with a first reading credited to its presenter counted as Tier A, Tier A is 1.97% (upper bound 2.58%) and Tier B 1.72% (2.60%); weighted by characters, which now gates, Tier A is 0.77% (1.04%) and Tier B 0.88% (1.48%). Both gates fail. Round 3, provisional and read on the rehearsal copy of write #3, pools 548 reports and 9,824 rows: Tier A is 0.79% by characters (bound 1.88%) and fails on one report, 22149; Tier B is 0.90% (1.42%) and passes, with both detectors under their source rates. Write #4 fixes the three Tier A classes behind that failure. Round 4 is provisional: it was read on the write #4 rehearsal copy and, for 114 tranche 2 reports, early on the replica. It re-read the 34 pooled reports that write #4 touched and pools 672 reports and 12,122 rows. Tier A is 0.05% by characters (bound 0.08%) and Tier B is 0.75% (bound 1.03%). Both gates pass, and both detectors are under their source rates (4.27 and 1.98 per million tokens against 106.54 and 6.23). Every remaining class is listed with its count under "Where more work stops paying". The loop is done, provisionally: the verdict stands once write #4 ships unchanged and `build_r4.py verify` on the replica finds the windows unchanged. |
| 6. Parsing-quality tracking | No. The checks above measure structure, not correctness. |

Overall: partly met. This verdict covers records before 10 September 2012. Text from that date on is now loaded and is measured beside the headline above, with no hand audit yet ([post-2012-text.md](report/post-2012-text.md)).

### Gaps, by who owns them

- The source imposes: unnamed chairs ("The Chairman" where the report gives no chair, about 12,000 rows), collective "hon. Members", bare "Mr Deputy Speaker" on two-holder days, annex pages that are lists of links, procedural lines with no speaker.
- The project chose: the ADR 0001 denominator, collapsing single-speaker reports into one row, and a pass that means only that a title line was found. Dropping text before the first speaker was a choice until 15 October 2026, when [ADR 0008](adr/0008-text-before-the-first-speaker-kept.md) reversed it.
- The project missed, and these are the next work:
  1. 2,078 reports keep rows from an older parser. The guarded re-parse of 13 October rebuilt 6,615 stale reports and refused the rest: 1,954 by the F18 guard (the new parse drops a body line the stored rows hold, or yields nothing), 87 that step 6b refused, 34 where a re-parse would undo a direct edit, and 3 where it would bring back deleted rows. Each needs a parser fix before it can be rebuilt. The plan, the stored rows of every rebuilt report and two full `pg_dump` backups from before the write were kept outside the repo on 13 October; they are temporary unless moved. Write #3 rebuilt most of these and held 162. Write #4 rebuilds 42 of the 162 (the 22149 class and 38719), and 120 stay held.
  2. The stored rows drop 0.19% of body text inside reports with rows (after write #3; 0.40% before it). The parser has kept text before the first speaker as rows since `e37853a`. Headings, time stamps, chair annotations and question numbers still get no row (decision review, finding 7, open). The split between the remaining classes is not measured.
  3. Unbolded speaker labels and lists that inherit the last speaker (P2 and P3 in `plans/link-precision-audit.md`). The 14 October repair gave no speaker to the lines after a procedural line, to whole-line editorial notes and to "rose" stage directions; what remains is unbolded labels, lists inside a member's speech, 83 "Certificate of Urgency handed in." rows, 4 rows in two stale reports (26467, 27699) the repair could not match, and 6 rows of a Budget statement in report 22691 resumed after a suspension, now unattributed instead of credited to Mr Speaker. Annex tables after a heading are ministers' own tables in written answers and stay with them.
  4. Glued and split words, markup residue, lost text and wrong speakers that the speech fidelity loop ([speech-fidelity-loop.md](report/speech-fidelity-loop.md)) is working through. Round 0 fixed `&nbsp;` in 3,315 older-system reports and cut the detectors' pipeline hits from 35,993 to 2,041 (dictionary test) and from 14,569 to 824 (punctuation test). Round 1 fixed the header table in single-speaker rows, html2text escapes, bare ampersands and link URLs, in 11,779 reports. Write #2 fixed F4 (a paragraph cut across rows at a column or page marker, the largest class), F5 and the speaker-label classes WS1 to WS6. Round 2 read 316 reports and found Tier A and Tier B above their gates. Write #3 fixes the round 2 classes (PA1 to PA7, TB1, TB2, TC1) and adds the `kind` column. Round 3 put Tier A at 0.79% by characters (bound 1.88%) and named three classes. Write #4 fixes them: page-reference footnotes and division records read as speech (`2ec5fe8`), procedural lines that miss an anchor (`73ed1d6`) and older-system first readings credited to their presenter (`1220161`). It also rebuilds 42 held reports: 41 whose stored rows credit headings and captions to a speaker (report 22149 was one of them) and 38719, whose stored rows hold 71 paragraphs cut at column markers. Round 4 (provisional, read on the write #4 rehearsal copy) puts Tier A at 0.05% by characters (bound 0.08%) and Tier B at 0.75% (bound 1.03%): both gates pass. Still open after it: the classes the fixes found and left, each with its corpus count under "Where more work stops paying", Tier B (paragraphs cut inside `<pre>` blocks, footnote digits glued to a word) and review findings 6 to 13 (the heading exemption in Tier C, text dropped with no row, column numbers, vernacular marking, row identity, the 1,568-report rebuild sample, `footNote` and `mpNames`, small points). The loop stops when Tier A's weighted upper bound, by characters, is 1% or less, Tier B's is 2% or less with both detectors below their source typo rates, and every remaining class is listed with its corpus count here; round 6 is a cap. Round 4 meets all three, provisionally.
  5. The ADR 0001 rule that drops speaker strings starting with "_" also drops real names written with a leading underscore. Round 0 removed the stray `__` from 33 such labels, "__Dr Teo Ho Pin" among them. One name is left, `_S_ hawn Huang Wei Zhong (Jurong)` on 2 rows; the other 10 strings starting with "_" are italic headings.
  6. In report 24248 the fallback start line dropped Gan Kim Yong's opening speech, because his label merged into the heading. The parser now keeps the speech as 30 rows with no speaker and kind SPEECH (`72d4d64`), and write #3 stores them. The report is on the per-report Tier A list in [data-loss-register.md](data-loss-register.md). The speech stays unattributed.
  7. For 465 stored rows in ten reports the speaker is known to be wrong. The right speaker is known for all of them except the 7 rows of 42017, a notice of motion that no member spoke, and it is not stored. Write #3 unlinks the rows, and an override file with the right speakers is not built.

### Where more work stops paying

Published peers report less than this project. The Knesset corpus reports 94.5% of speaker strings matched to its member database, and 98.3% speaker-name correctness on a hand-checked test set; a 2026 paper linking the UK Hansard corpus to MPs reports 89.3% for the Commons; ParlaMint, the Australian Hansard datasets and TheyWorkForYou publish no linking rate. None found resolves an unnamed presiding officer to a person: ParlaMint tags the role, the Knesset corpus flags the chair, and Spain's ParlaMint corpus leaves them blank. So work on unnamed chairs, or resolver tuning that moves the rate by tenths of a point, is past the point of value. Work that moves text share, coverage or measured precision is not. What peer projects do that this one does not is in [peer-projects.md](peer-projects.md).

The stopping rule needs every remaining class listed with its corpus count. These are the classes the speech fidelity loop found and left. The second census (`plans/speech-fidelity-loop/cycle4/census/CENSUS2.md`) counted on master `1220161`, the three fixes included; the fix surveys counted before or after their own fix, as the row says. The detail is in the [round log](report/speech-fidelity-loop.md).

| Class | Rows | Reports | Countable characters | Harm |
|---|---|---|---|---|
| Italic title stored as a SPEECH row (60 of 60 read were headings) | 9,782 | 1,094 | 293,008 | Tier C |
| Of those, an italic title that closes a member's run and is credited to the previous member (1,978 before write #3) | 2,281 | 157 | 49,933 | Tier C |
| Bare time stamp credited to a speaker (1,262 before write #3) | 51 | 51 | 427 | Tier C |
| "#### [... in the Chair]" credited to a speaker (524 before write #3) | 0 | 0 | 0 | None left |
| `<pre>` table stored one row per line (about 15,500 of the rows are real tables) | 18,591 | 863 | 388,269 | Tier C |
| Prose cut across rows inside `<pre>`, a lower bound (542 cuts) | 1,021 | 162 | 37,103 | Tier B |
| Footnote digit glued to a word or number (1,462 hits; 185 hits in 147 reports change a number) | 1,157 | 869 | 401,308 | Tier B |
| Labels that are not people: headings 52 rows in 7 reports, a table caption and cell in 22806 (8), a report title in 32642 (5), junk such as a bold "Question" or "To ask" (48) | 113 | 15 | 9,081 | Tier A where the text is a member's or the chair's (about 7,000 characters), otherwise Tier C |
| Member speech swallowed by a footnote run (23268, held) | 6 | 1 | 1,297 | Tier A |
| Caption text dropped after a bold "Table N:" (23627, 43250) | 2 lines | 2 | 23 words | Tier A, lost text |
| Caption-only bold lines, no row by design since WS3 | 42 lines | 28 | 475 words | Tier C |
| A column marker that leaves a `****` line, so a paragraph stays cut across it: 405 cuts, about 300 to 355 of them real (15 of 20 sampled); 684 rows, 259 reports and 678,438 characters without the 50 cuts after a link-title line; older system only; a lower bound | 770 | 293 | 694,905 | Tier B |
| Reports with markdown and no rows: 22 hold prose a person said or wrote (94,547 characters; 14 ministers' addenda to the President's Address with no label, 8 other addenda, 33574 alone 27,467), 16 hold procedural records or first readings (2,500), 664 are appendix stubs, assent lists, adjournment records and order-read stubs | 0 | 702 | 220,800 (208,633 in Parliaments 0 to 11) | Lost text for the 22; the rest are stubs and records |
| Near-miss procedural lines left by fix 2: "The amendment(s) read(s) as follows:" with no marker (9), "Original Question put, and agreed to." (6), "Resolved." (5), "Bill accordingly read the Third time." (2), "+The following amendments stood ..." (2), five single rows | 29 | up to 27 | 1,051 | Tier A, procedural line credited |
| First-reading leftovers: OCR-typo formulas (33648, 35994, 38770, 39997), 25885, 22343's split tail, trailing headings and time stamps in 6 reports, "theSenior" or "theSecond" glue in 13945, 13946 and 13953 | at least 12 | 15 | not counted | Tier A for 6 reports, Tier C for 6, Tier B for 3 |
| "The voting was as follows:-" (5 rows) and "Division Bells rung." (4 rows) credited to the chair | 9 | not counted | not counted | Tier A |
| Footnote continuation lines (21601) | not counted | 1 | not counted | Tier A |
| Double-marker notes (22949, 43048) and "(1)IATA" notes with no space (21163) | 4 | 3 | not counted | Tier A |
| Resumed Budget speech with no speaker in 22691, after the rebuild | not counted | 1 | 18,706 | Listed, not scored |
| Reports still held after write #4 (22806, 23038, 23268, 23627, 24839, 41804, the hand-edited 22647 and 22650, and the rest of write #3's 162; 24248 gets no write). Write #5 holds 60 more, so 181 are held: 56 refused by patch 06 (a space next to the footnote marker), 3 by patch 04 and 1 by patch 09. Write #6 rebuilds 58 of the 60 and holds 2 new ones (38147, 38222), so 123 are held. Write #7 holds 3 new ones (37959, 20889, 43635) and releases none, so 126 are held | kind NULL on 2,275 | 121; 181 after write #5; 123 after write #6; 126 after write #7 | not counted | Stored rows from an older parser |
| Latent: `_SPEAKER_HONORIFIC_RE` does not know Miss, Madam, Che, LG or COL; "Miss Penny Low (Pasir Ris-Punggol" cut at a bracket (24708) | 0 today; 14 | 0; 1 | 0; 4,436 | None until a bold-only line with no colon appears. 6,828 "Miss" and "Madam" rows (2,461,263 characters) depend on the colon |
| Group labels ("An hon. Member" and 16 spellings) and real people whose label lacks an honorific the regexes know | 2,241 and 7,533 | 922 and 1,391 | 70,238 and 2,815,754 | Not errors; the ADR 0001 rate already excludes the "hon. Member(s)" forms |
| Markup residue: `**` in 50 rows and `__` in 247 rows (write #4 replica, 16 October recount; the strip rule `27f6d46` has been written) | 50 and 247 | 22 and 164 | not counted | Tier C |
| Rows of kind UNCLASSIFIED, many of them PROCEDURAL, DOCUMENT_TEXT or HEADING in fact; readers flagged 199 of 9,043 round 3 and round 4 rows | 20,944 | not counted | not counted | None; kind gates nothing |
| Text dropped inside reports that have rows: headings, time stamps, chair annotations, question numbers | not counted | not counted | 0.19% of body text | Tier C (decision review, finding 7, open) |

The classes the source imposes, such as unnamed chairs, are in "Gaps, by who owns them" above.

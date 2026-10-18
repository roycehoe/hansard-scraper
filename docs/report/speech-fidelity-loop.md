# Speech fidelity loop

Started 14 October 2026. The loop checks stored speech rows against their source HTML, fixes the defects it finds, and repeats with a fresh sample until the stopping rule below holds. It began with report `00004736-WA.00002403-WA_1`, which stored "they are notlousier than Singapore", "Sir,I" and "reports.I". The source has `not&nbsp;lousier`.

## Method

Each round does two things.

1. **A sampled reading.** A stratified sample of speech rows, each read by hand against `HansardWebsiteResponse.content`.
   - The unit is a speech row.
   - Strata are report_version by report_type by era (P0, P1-4, P5-8, P9-11, P12, P13, P14), 137 non-empty strata.
   - Each stratum gets min(N_h, 2 + round(126 × N_h / N)) rows, about 400 a round, weighted N_h / n_h.
   - The seed is 20261014 plus the round number. Nothing else changes between rounds.
   - A regression panel adds every row fixed or flagged in an earlier round.
2. **Two corpus-wide detectors**, run on every speech row. Each hit is checked against the raw HTML, with tags stripped and `&nbsp;` read as a space. A token that is also in the HTML is a source typo. One that is missing from the HTML is a pipeline error.
   - The dictionary test flags a token that is absent from `/usr/share/dict/words` and rare in the corpus (at most 200 occurrences), and that splits into two pieces that each occur at least 12,000 times.
   - The punctuation test flags `[a-z][,;:?!.][A-Z][a-z]`, a capitalised word straight after punctuation with no space.

   The dictionary test cannot see glue that has a rare half: "notlousier" passes because "lousier" is rare. Zero hits do not prove the text is clean.

In scope: glued or split words, lost, duplicated or reordered text, markup residue, text under the wrong speaker, and mangled speaker labels. Out of scope: typos in the source HTML, and everything `docs/vision.md` lists as source-imposed or project-chosen.

The loop stops by a rule on error rates, not on a clean round. A round reads about 400 rows. A clean round only bounds the true rate below 0.75% at 95% confidence, and a 0.5% rate comes back clean 13% of the time. So errors go into three tiers by harm to a researcher, and each tier has its own gate.

| Tier | Errors | Gate |
|---|---|---|
| A | Wrong speaker, lost text, duplicated or reordered text | Weighted upper bound of 1% or less on the pooled rounds |
| B | Glued or split words, a paragraph cut across rows | Weighted upper bound of 2% or less, and both detectors below their source typo rates |
| C | Markup residue, a label that still names the right person | No rate gate; fix only with a mechanical rule that leaves zero unexplained rows |

Every rate is weighted by N_h / n_h. The bound is the one-sided 95% Clopper-Pearson bound on the Kish effective sample size. A row keeps its verdict across rounds unless a later write touched its report. A Tier B or C class that touches fewer than about 100 rows and needs a row-count change goes on a residue list with its corpus count in `docs/vision.md`. Round 6 is a hard cap. If it ends first, the loop reports which gate failed and by how much. The tracked copy of the full rule, with its measurement method and the current standing, is [speech-fidelity-stopping-rule.md](../speech-fidelity-stopping-rule.md).

No fix may make earlier work worse. Every write is diffed against a snapshot taken before it. Every changed row must belong to the error class the fix targets. A whitespace fix must leave each row's text identical once whitespace is removed. The three attribution numbers, the speech row count and the unmatched attendance names may hold or improve, never worsen. Both detector rates are recorded before and after every fix, and a rise counts as a regression.

## Round 0: `&nbsp;` deleted instead of spaced

Commit `50cc527`. `utils/markdown_parser.py` deleted `&nbsp;` from older-system HTML. The newer system's branch already turned it into a space. Both systems now replace it with a space before html2text runs. An emphasis tag that holds only `&nbsp;` becomes a single space, because otherwise it would render as a stray `__` or `****`.

A dry run found 3,464 older-system reports whose markdown changes. 606 sittings change too.

### The write

On 14 October at 21:08, one transaction applied the change to 3,315 reports and 606 sittings. It updated 50,971 speech rows in place, keeping their ids and `speaker_id`. Then it ran stage 8 and diffed every row against the snapshot.

| Class | Rows |
|---|---|
| Whitespace-only text change | 50,373 |
| Whitespace-only label change | 197 |
| Stray `__` or `****` also removed | 344 |
| Label loses a leading `__` | 33 |
| Read by hand against the HTML | 18 |
| Procedural line now has no speaker, under the existing non-speech rule | 6 |
| Unexplained | 0 |

No attendance rows changed. Stage 8 set no new links: 0 of 156 attendance records and 0 of 82,452 speech records. The 57 sittings whose markdown changed by more than whitespace are listed outside the repo, in `plans/speech-fidelity-loop/r0/sitting_other.txt`.

Four groups of reports were held back. The groups overlap.
- 121 stale reports, whose stored rows already differ from the current parse. They include the reports the 13 October guard refused and the hand-edited ones.
- 16 reports (ids 37916 to 39514) whose stored markdown still holds `**Column : 293**` lines.
- 10 reports where spacing the entity exposes html2text escapes such as `6\.` and `\-`.
- 6 reports whose row count would change. Reports 23398 and 23401 would lose a footnote, 22602 would gain a junk row, and 22073, 22636 and 24516 would gain rows.

### Figures

Attribution, Parliaments 0 to 11, from `scripts/attribution_text_share.py`:

| Metric | Before | After |
|---|---|---|
| ADR 0001 rate | 554,900 / 567,756 = 97.74% | 554,941 / 567,782 = 97.74% |
| All-rows rate | 554,900 / 624,332 = 88.88% | 554,941 / 624,332 = 88.89% |
| Text share | 96.58% | 181,724,051 / 188,134,408 = 96.59% |

Parliaments 12, 13 and 14 did not move. `scripts/trace_speaker_links.py` reports 0 stale keys across 554,941 linked rows. The table still holds 1,068,668 speech rows.

Detectors, pipeline hits only:

| Test | Before | After |
|---|---|---|
| Dictionary, all | 35,993 (561.5 per million tokens) | 2,041 (31.8) |
| Dictionary, sprs2 | 908.3 per million | 51.4 per million |
| Dictionary, sprs3 | 0.04 per million | 0.04 per million |
| Punctuation, all | 14,569 (227.3 per million) | 824 (12.8) |
| Punctuation, sprs2 | 367.6 per million | 20.7 per million |
| Punctuation, sprs3 | 0.16 per million | 0.16 per million |

Source-typo hits went from 6,811 to 6,842 on the dictionary test and stayed at 399 on the punctuation test. The dictionary test's thresholds depend on corpus frequencies, and spacing out glued words shifts those frequencies.

The `__Dr Teo Ho Pin` class of label (vision gap 5) is closed except for one row. After the write, 74 rows in 11 distinct speaker strings start with `_`. Ten of those strings are italic headings such as `_Annex B - Supplementary information_`, not names. The one name is `_S_ hawn Huang Wei Zhong (Jurong)`, on 2 rows.

A `pg_dump` of report, speech, attendance and sitting from before the write is kept outside the repo, in `plans/speech-fidelity-loop/backup/`.

## Round 1: header tables, escapes, ampersands and link URLs

Round 1 read a fresh sample, fixed four classes plus the header table, and changed how the loop is run.

### The sample

The seed is 20261015. The sample holds 395 rows in 137 strata, plus 58 regression-panel rows from round 0. Eight Sonnet readers checked the rows against the source HTML. One reader judged another chunk's rows because both used a shared helper that one of them overwrote. Its verdicts were dropped and an independent second reader redid the chunk. None of the 20 flawed panel rows got worse in round 0.

Weighted by N_h / n_h, from the 395 sampled rows only:

| Tier | Rows with an error | Weighted rate | Weighted upper bound |
|---|---|---|---|
| A | 5 | 1.29% | 3.69% |
| B | 12 | 3.52% | 6.23% |
| C | 15 | 1.25% | none |
| Any | 31 | 6.00% | 9.18% |

The Kish effective sample size is 208. Unweighted, 7.85% of rows had an error. Tier A is the binding gate: it needs 301 effective rows with no error, and each error found raises that number.

### Fixes

| Fix | Commit | Defect | Reports | Rows |
|---|---|---|---|---|
| F1 | `46b1988` | The report header table (its `Title:` and `MPs Speaking:` fields) became the start of a single-speaker row | | 2,745 |
| F7 | `215e3e8` | A speaker label with nested bold lost its title, so `****Mr X** :**` was not read as a label | 3 | 26 |
| F3 | `32ec0eb` | html2text escapes such as `\.` and `\-` stayed in the text | 10,253 | 4,862 |
| F6 | `49a389f` | A bare `&` came out with a `;` after the next word (`R&D.;`, `F&B;`) | 335 | 1,020 |
| F2 | `bbf52de` | A link kept its URL in the text; now only the link text stays | 1,759 | 4,068 |

The report and row counts for F7, F3, F6 and F2 are from each fix's own dry run. They overlap, so they do not sum to the combined write.

F1 went in at 10:33 on 15 October. It changed 2,745 rows, with 0 unexplained.

### A metric change

Text share counted the `Title:|` and `MPs Speaking:|` header fields as body text the parser dropped. They were 1.72M of 188.1M characters. Commit `7ba038f`, approved by the user, leaves them out of the denominator. On the same stored rows, text share moves from 96.59% to 97.48%. F1 then lowered it by 0.07 points, because 135,406 characters of metadata had counted as linked speech. The user accepted that. Text dropped inside reports with rows fell from 1.22% to 0.41%.

### The combined write

F7, F3, F6 and F2 shipped as one write at 12:21 on 15 October. The write ran on a local replica first. A delta shipper then sent the changes to the remote database. 41 of 41 ship checks passed, the table hashes were equal, and the snapshot comparison showed 0 differences.

| Item | Count |
|---|---|
| Reports applied | 11,779 |
| Speech rows updated | 9,979 |
| Speech rows inserted | 222 |
| Speech rows deleted (empty-link rows) | 3 |
| Sitting markdowns changed | 104 |
| Attendance rows changed | 0 |
| Stale links | 0 |

Two reports were read by hand and included. In report 43315, 17 rows moved from Mr Speaker to Mr Lim Hng Kiang and 1 was restored. In report 6643, one row had swallowed about 10,500 words. It is now 431 rows that match the source's speaker sequence.

Eight "X rose ---" stage-direction rows lost their speaker under the 14 October rule, because the escape had hidden them. The all-rows rate fell 0.01 points as a result. The user accepted that.

Held back: 111 reports whose stored markdown no longer matches the parser, 584 stale reports, and 17 with changes the checker could not explain. Reports 22647 and 22650 were hand-edited earlier and stay as they are.

### Figures

Attribution, Parliaments 0 to 11, from `scripts/attribution_text_share.py`. The text share uses the new denominator, so the "before" column is the 11:37 run on the stored rows after F1:

| Metric | After round 0 | Before combined write | After combined write |
|---|---|---|---|
| ADR 0001 rate | 554,941 / 567,782 = 97.74% | 554,941 / 567,782 = 97.74% | 554,933 / 567,774 = 97.74% |
| All-rows rate | 554,941 / 624,332 = 88.89% | 554,941 / 624,332 = 88.89% | 554,933 / 624,332 = 88.88% |
| Text share | 96.59% (old definition) | 181,588,645 / 186,413,873 = 97.41% | 181,508,897 / 186,296,232 = 97.43% |

| Scope | ADR 0001 rate | All-rows rate | Text share |
|---|---|---|---|
| Parliament 12 | 98.94% | 96.93% | 98.95% |
| Parliament 13 | 98.18% | 96.31% | 99.06% |
| Parliament 14 | 208,220 / 210,284 = 99.02% | 208,220 / 213,318 = 97.61% | 99.21% |

The speech table holds 1,068,887 rows.

### Changes to how the loop runs

- A local cache of report and sitting HTML. Dry runs read it instead of the database.
- A one-at-a-time dry-run queue. Concurrent dry runs ran the laptop out of RAM.
- A local Postgres replica and a delta shipper. A rehearsal takes 5 to 10 minutes locally, against about 45 over the hotspot.
- A word-multiset detector. It compares the words of a report's HTML with the words of its rows. On the round 1 reports, 19 of 19 flags were real. It finds lost text that the glue and punctuation detectors miss.
- The stopping rule above.

### Still open

- F5: a line with inline bold that holds `$` or `%` is dropped (report 46433, maybe 11470). Tier A.
- Round 1's wrong-speaker rows. Tier A.
- F4: a paragraph cut across rows at a column or page marker. Tier B, and the largest class in round 1.
- A rerun of both detectors. The punctuation detector must fall below its source typo rate of about 6.2 per million, from 12.8 after round 0.

## Round 2 and write 3 (15 to 16 October)

### Write 2

Write 2 shipped at 15:46 on 15 October through the local replica and the delta shipper. It carried WS1 to WS6, F5, D1, D2, F2b and F4, committed as `19bd47d` to `d383048`, each with a golden fixture. 19 tests pass.

| Item | Count |
|---|---|
| Reports applied | 3,416 |
| Speech rows updated | 28,858 |
| Speech rows deleted (F4 joins and 52 addenda rows) | 24,402 |
| Speech rows inserted | 109 |
| Sittings changed | 160 |

40 of 40 ship checks passed, the table hashes were equal and the snapshot comparison showed 0 differences. The speech table holds 1,044,594 rows. Held back: reports 23921, 38225 and 41944 (the register says why), 8 unexplained, 112 that drifted and 41 stale.

Attribution after the write, Parliaments 0 to 11: 537,701 / 550,163 = 97.73% (ADR 0001 rate), 537,701 / 607,295 = 88.54% (all rows), 181,551,794 / 186,295,828 = 97.45% (text share). The all-rows rate fell from 88.88% because F4 merged rows. Parliament 12 stands at 98.89 / 96.70 / 98.95, Parliament 13 at 98.19 / 96.28 / 99.06 and Parliament 14 at 99.03 / 97.60 / 99.21.

### Round 2

The seed is 20261016. The sample holds 332 reports and 6,277 rows. 316 reports and 5,934 rows were read now, by 20 Sonnet cold readers. 16 reports wait for write 3. The aggregate (`plans/speech-fidelity-loop/r2/AGGREGATE.md`, under the row rule of the time) put Tier A at 1.71% with an upper bound of 2.31%, Tier B at 1.72% (2.60%) and Tier C at 5.62% (7.20%). Both gates fail. The bound is the report bootstrap of the [stopping rule](../speech-fidelity-stopping-rule.md). The Method section above describes the Clopper-Pearson bound the loop started with.

| Tier A class | Share of Tier A |
|---|---|
| Footnote and amendment text credited to the speaker | 33.5% |
| Procedural one-liners, member actions and "Adjourned accordingly" in a collapsed row | 27.8% |
| Inline directions in a speaker's paragraph | 16.7% |
| Oath rolls under the Speaker | 10.4% |
| "X rose -" with the name lost | 8.3% |

Fixing the first four leaves about 0.20% (bound 0.30%) on this sample. In Tier B, wrapped prose inside `<pre>` is 57.5% and a sentence split across source blocks is 14.6%. Errors cluster: 229 of the 316 reports have no Tier A row, and five reports carry 47% of Tier A. Second reads of two batches found as many or more Tier A rows than the first reads, and the aggregator's own census added 54 Tier A rows that no reader flagged. From round 3 every reader does a full source pass.

### Write 3 preparation

Write 3 is the stack of parser fixes committed on master from `89bf053` on, 23 commits, then the kind column and changes A to E, five more commits (see "The overnight run"). The planner built the write from them in steps: each commit has a checker, and a chain checker explains every changed row in order. The stale reports (stored rows that differ from the current parse) are rebuilt when their stored rows equal some parser version's output, the rule the user set on 15 October. The 1,568 near-match reports follow the 30-report check below.

| Commit | What it does |
|---|---|
| `850a070` | PA1: oath rolls and procedural one-liners get no speaker |
| `bc582ff`, `33280c2` | PA2 and PA3: a labelled "rose" line keeps the name; labelled assent, dissent and resumed-seat lines end the turn |
| `db369d7` | PA4: bold "Hon. Members" mid-sentence stays in the speaker's row |
| `d5958d8` | PA5: footnotes and amendment text get no speaker |
| `6824b56` | PA6: procedural lines split out of single-speaker collapsed rows |
| `4c2aa72` | PA7: inline directions split out of speaker rows |
| `21264ae` | TB1: wrapped prose lines inside preformatted blocks are joined |
| `8537c44` | TB2: adjourned and suspended directions split across blocks are joined |
| `1fc23a3` | TC1: bold markers are stripped from transcripts |
| `b76ee3c`, `f7ab3cf` | BG, Encik and other titles are accepted on long speaker labels, at the start of a label only |
| `5963408`, `1d056c2` | A footnote that opens with a hash marker stays out of the headings; a long underscore line is read as a footnote rule |
| `3810dd5`, `9d87d81` | A bracketed note cut by a column marker is joined, with its space kept |
| `2dc520f` | The first copy of a paragraph printed twice around a stray tag is dropped |
| `e184d36`, `b7dcff4` | Gestures and more inline directions are split out; the split stops mutating its arguments |
| `f63200e`, `0a7297c` | The leading title line leaves single-speaker collapsed rows; a "Resolved" heading stays as the body of a collapsed report |
| `e890946` | Text before the first speaker is kept as rows with no speaker |
| `9e882ff` | Speech after a closed footnote keeps its speaker |

The user decided on 15 October (late) to keep the preamble as rows with no speaker, to rebuild the 1,568 near-match stale reports after a reader sampled 30 and found no hand edit, to accept the 21 "repair tranche" reports, and to fix four defects the stale checker found in HEAD: the BG, Encik and RAdm titles that long labels dropped, the `#Text` footnotes in 23398 and 23401 dropped as headings, the split of 20991's vernacular note, and 24516's duplicated sentence. On 16 October the user kept the 24516 fix, approved renumbering ordinals, approved shipping with `ship_delta4.py`, accepted the fall in the all-rows rate and text share as designed, ruled that "Head NNNN -" preamble fragments are Tier C, put 24248 on the per-report Tier A list, and set round 3 as re-reads plus tranche 1.

Plan v2 (on `c94e3ee`, before changes A to E) applies 11,271 reports (9,502 clean and 1,769 stale rebuilt) and holds 162. It carries 628,210 speech updates (601,802 of them change the ordinal only), 8,253 deletes and 13,051 inserts, 3,210 report markdown updates, 44 sitting markdown updates and 45 junk attendance deletes. A replay of every applied report equals the final parse. The ship test ran on clones of the replica. The apply committed with 0 unexplained rows. Five drift tests all aborted before any write. The rehearsal and commit passed 49 checks, and the local and target tables had equal hashes. `ship_delta4.py` sends an ordinal-only update as `id` and `ordinal`, which cut the speech upload from 321.4 MB to 69.9 MB.

Plan v2 changes the figures like this (Parliaments 0 to 11, the stored rows are the rows after write 2):

| Metric | Stored | Plan v2 rehearsal |
|---|---|---|
| ADR 0001 rate | 537,701 / 550,163 = 97.73% | 527,739 / 539,357 = 97.85% |
| All-rows rate | 537,701 / 607,295 = 88.54% | 527,739 / 608,695 = 86.70% |
| Text share | 181,551,794 / 186,295,828 = 97.45% | 181,359,343 / 186,290,919 = 97.35% |

| Where the body text goes | Stored | Plan v2 rehearsal |
|---|---|---|
| Linked rows | 97.45% | 97.35% |
| Rows with an unlinked speaker string | 0.72% | 0.69% |
| ADR-excluded rows | 0.10% | 0.05% |
| Rows with no speaker | 1.21% | 1.61% |
| Reports with no rows | 0.11% | 0.11% |
| Dropped inside reports with rows | 0.40% | 0.19% |

Rows by category went from 537,701 linked, 54,026 no speaker, 12,462 named but unlinked and 3,106 ADR-excluded, to 527,739, 67,003, 11,618 and 2,335. The breakdown by cause:

| Cause | Linked rows | All rows | ADR denominator | Linked characters |
|---|---|---|---|---|
| Directions split out (PA7 and the gesture fix) | +760 | +2,323 | +762 | -23,414 |
| Footnotes and amendment text (PA5 and its fixes) | -2,546 | -2,456 | -3,145 | -180,226 |
| Other (TB1, TB2, TC1, joins, ordinal shifts) | -287 | -330 | -309 | -934 |
| Preamble rows kept | +0 | +5,433 | +0 | -22 |
| Procedural, oath, rose and label lines (PA1 to PA4, PA6, title drop, titles on long labels) | -1,914 | +527 | -1,966 | -131,376 |
| Stale rebuild | -5,975 | -4,097 | -6,148 | +143,521 |
| Total | -9,962 | +1,400 | -10,806 | -192,451 |

Parliaments 12 to 14 under plan v2: Parliament 12 at 98.90 / 95.46 / 98.84, Parliament 13 at 98.21 / 95.18 / 98.95, Parliament 14 at 99.04 / 96.60 / 99.11. The all-rows rate falls because no-speaker rows join its denominator. No speech is lost.

### The decision review

An independent review of the docs, the decisions and the parser (`plans/speech-fidelity-loop/decision-review.md`, 15 October) made 13 findings. The user approved the first five as changes A to E. Findings 6 to 13 are out of scope for write 3 and stay open.

| Finding | Change |
|---|---|
| 1. A NULL speaker means six things | A: the `kind` column ([ADR 0009](../adr/0009-speech-kind-column.md)) |
| 2. 471 known-wrong rows stay linked to the wrong person (the review's count; 465 stored rows) | C: unlink them, kind SPEECH |
| 3. The Tier A gate can pass on undercounted reads | D: weight Tier A and B by characters, full source pass for every reader ([stopping rule](../speech-fidelity-stopping-rule.md)) |
| 4. A single-speaker collapse credits non-speech to the presenter, and the source's `(proc text)` tag is thrown away | E: keep the tag; tagged paragraphs get no speaker and kind PROCEDURAL |
| 5. The PA7 split cuts a sentence the F4 join had just repaired, and the detector cannot see it | B: cut the direction out, keep the paragraph whole |
| 6. Tier C exempts a heading credited to a speaker | Open |
| 7. Text dropped with no row, even after ADR 0008 | Open |
| 8. Column numbers are discarded | Open |
| 9. Vernacular speech cannot be told from English | Open |
| 10. Row identity is unstable, and the docs trail the writes | Open; the docs part is fixed in this change |
| 11. Rebuilding 1,568 reports on a 0-of-30 sample | Open |
| 12. `footNote` and `mpNames` are not stored | Open |
| 13. Smaller points | Open |

The user also ruled that a first reading credited to its presenter is Tier A. Under the row rule that moves round 2 Tier A from 1.71% to 1.97%, with an upper bound of 2.58%.

### The overnight run

The user was asleep for seven hours. One Opus orchestrator ran the night from `plans/speech-fidelity-overnight-brief.md`, with Sonnet workers for reading and implementation and Opus for checkers, plans, writes and verdicts. The brief set the limits: no speech-row ship to the remote, no push, and no waiting on the user. A call outside the brief took the conservative path and went into the morning report.

Changes A to E went in as new commits on top of master, with no history rewrite.

| Change | What it does | Commit |
|---|---|---|
| A | `speech.kind`, a nullable Postgres enum, migration `7c1d4e9a2b60`; the parser sets it on every parsed row | `27fd9c7`, `0969500` |
| B | A direction is cut out of its paragraph; the paragraph stays whole and keeps its row, and the direction follows as a CHAMBER_EVENT row. A parse of the cached reports changes 702 reports and leaves 1,153 fewer rows than the three-row split, with no text lost | `15a00e4` |
| C | `data/unattributed_speech.json` lists ten entries: the eight chair-resumption reports, 31083 and 24248's opening speech (30 rows). The rows in a listed range that carry the listed label get no speaker and kind SPEECH. 42017 is left out | `052540d` |
| D | The stopping rule weights Tier A and B by characters and requires a full source pass | this change |
| E | A `(proc text)` pair that wraps a whole block stays in the markdown (10,060 of 10,107 pairs); that line becomes a no-speaker PROCEDURAL row, inside collapsed reports too. Other pairs keep the old treatment. A parse of the cached reports changes 2,762 markdowns and 941 reports' rows, and 1,132 credited rows become PROCEDURAL | `efa477d` |

The kind migration revises `e5a9c3b7d216`. Another session's uncommitted `transcript_tsv` migration (`f2b8d4a6c913`) was left alone, so the working tree shows two heads until that migration's `down_revision` is re-pointed when it is committed. The replica and the remote were both migrated at 22:51 on 15 October; the migration adds the column only, and no rows were written. Two calls differ from the brief or the register. Report 42017 gets kind UNCLASSIFIED, because its rows are a notice of motion that nobody spoke. The count of stored rows under a known-wrong label is 465. The register first said 471, which counted ordinal spans; write 2 deleted rows without renumbering, so the ranges for 17279 and 18272 hold 37 and 9 rows although their ordinals span 42 and 10.

The ADRs are [0007](../adr/0007-non-speech-lines-get-no-speaker.md) (reworked), [0008](../adr/0008-text-before-the-first-speaker-kept.md) (new, supersedes 0005) and [0009](../adr/0009-speech-kind-column.md) (new). The register, the stopping rule and `docs/vision.md` carry the figures. The stale lines the review found are fixed: "rows deleted: not measured" and "stored rows: not yet rewritten" after write 2, and the single-speaker report count, where 1,193, 3,032 and 4,209 count different things.

A report write 3 does not rebuild gets a kind only on rows that equal a parsed row, and the rest stay NULL: 4,146 rows in 162 reports.

### Figures after changes A to E

The rehearsal ran on scratch copies of the replica, never on the remote. Parliaments 0 to 11 first, then 12 to 14, with the stored rows and plan v2 beside the final plan.

| Metric | Stored | Plan v2 | Write 3 rehearsal |
|---|---|---|---|
| ADR 0001 rate | 537,701 / 550,163 = 97.73% | 527,739 / 539,357 = 97.85% | 526,807 / 538,255 = 97.87% |
| All-rows rate | 537,701 / 607,295 = 88.54% | 527,739 / 608,695 = 86.70% | 526,807 / 607,756 = 86.68% |
| Text share | 181,551,794 / 186,295,828 = 97.45% | 181,359,343 / 186,290,919 = 97.35% | 181,359,552 / 186,290,919 = 97.35% |

| Scope and metric | Stored | Plan v2 | Write 3 rehearsal |
|---|---|---|---|
| Parliament 12, ADR 0001 rate | 98.89% | 98.90% | 82,170 / 83,077 = 98.91% |
| Parliament 12, all-rows rate | 96.70% | 95.46% | 82,170 / 86,480 = 95.02% |
| Parliament 12, text share | 98.95% | 98.84% | 29,041,974 / 29,443,992 = 98.63% |
| Parliament 13, ADR 0001 rate | 98.19% | 98.21% | 132,205 / 134,547 = 98.26% |
| Parliament 13, all-rows rate | 96.28% | 95.18% | 132,205 / 139,516 = 94.76% |
| Parliament 13, text share | 99.06% | 98.95% | 41,810,025 / 42,329,130 = 98.77% |
| Parliament 14, ADR 0001 rate | 99.03% | 99.04% | 206,946 / 208,878 = 99.08% |
| Parliament 14, all-rows rate | 97.60% | 96.60% | 206,946 / 214,976 = 96.26% |
| Parliament 14, text share | 99.21% | 99.11% | 59,399,644 / 60,051,708 = 98.91% |

| Where the body text goes | Stored | Plan v2 | Write 3 rehearsal |
|---|---|---|---|
| Linked rows | 97.45% | 97.35% | 97.35% |
| Rows with an unlinked speaker string | 0.72% | 0.69% | 0.67% |
| ADR-excluded rows | 0.10% | 0.05% | 0.05% |
| Rows with no speaker | 1.21% | 1.61% | 1.63% |
| Dropped inside reports with rows | 0.40% | 0.19% | 0.19% |

The breakdown by cause, from the rehearsal:

| Cause (Parliaments 0 to 11) | Linked rows | All rows | ADR denominator | Linked characters | All-rows points | Text-share points |
|---|---|---|---|---|---|---|
| B: paragraph kept whole around chamber events (KB) | -75 | +465 | -79 | -17,612 | -0.08 | -0.009 |
| C: Tier A unlinks (465 rows) | +0 | +0 | -163 | +0 | 0.0 | 0.0 |
| directions split out (PA7, f) | -15 | +655 | -15 | -9,611 | -0.098 | -0.005 |
| footnotes and amendment text (PA5, b, b2, h) | -2,505 | -1,978 | -3,104 | -179,654 | -0.124 | -0.096 |
| other (TB1, TB2, TC1, c, d, ordinal shifts) | -263 | -306 | -285 | -934 | 0.001 | -0.001 |
| preamble rows (g) | +0 | +5,433 | +0 | -22 | -0.792 | -0.0 |
| procedural, oath, rose and label lines (PA1-4, PA6, a, e) | -1,983 | +368 | -2,035 | -127,953 | -0.38 | -0.069 |
| stale rebuild | -6,053 | -4,176 | -6,227 | +143,544 | -0.388 | 0.08 |

| Cause (Parliaments 12 to 14) | Linked rows | All rows | ADR denominator | Linked characters | All-rows points | Text-share points |
|---|---|---|---|---|---|---|
| B: paragraph kept whole around chamber events (KB) | +0 | +174 | +0 | -4,535 | -0.038 | -0.003 |
| C: Tier A unlinks (465 rows) | -194 | +0 | -302 | -53,606 | -0.044 | -0.041 |
| E: proc text rows (KE) | -1,158 | +660 | -1,237 | -208,387 | -0.408 | -0.158 |
| directions split out (PA7, f) | -11 | +1,444 | -11 | -22,077 | -0.32 | -0.017 |
| footnotes and amendment text (PA5, b, b2, h) | -654 | -336 | -674 | -47,303 | -0.074 | -0.036 |
| other (TB1, TB2, TC1, c, d, ordinal shifts) | -9 | -5 | -9 | -981 | -0.001 | -0.001 |
| preamble rows (g) | +0 | +1,637 | +0 | -11 | -0.36 | -0.0 |
| procedural, oath, rose and label lines (PA1-4, PA6, a, e) | -835 | +52 | -868 | -54,686 | -0.201 | -0.041 |
| stale rebuild | +0 | +28 | +0 | -769 | -0.006 | -0.0 |

B is commit `15a00e4`, C the 465 unlinks of brief decision 7, and E commit `efa477d`, which acts on newer-system reports only and so has no row for Parliaments 0 to 11. Points are percentage points of the all-rows rate and text share for the scope of the table.

Detectors, pipeline hits per million tokens, against the source typo rate:

| Test | Stored, after write 2 | Source typos | Write 3 rehearsal |
|---|---|---|---|
| Dictionary | 31.8 | 106.6 | 9.84 |
| Punctuation | 12.66 | 6.24 | 3.66 |

Both detectors are now under their source typo rates; the punctuation detector was over it before. Pipeline hits fall from 2,038 to 632 (dictionary) and from 812 to 235 (punctuation) on 64.2 million tokens.

The ship candidate is plan v4 on `6e1922b`: 12,337 reports applied, 162 held, 627,303 speech updates (599,528 of them ordinal and kind only), 404,891 kind-only updates, 8,254 deletes, 12,388 inserts, 5,584 report and 44 sitting markdowns, and 45 junk attendance rows. It equals plan v3 on `052540d` plus the 12 newer-system reports that `6e1922b` fixes (it trims a space left inside a proc text tag). Both plans were rehearsed in full; the figures above are v4's, the detectors and the cause tables v3's, which differ by those 12 reports at most. The plan and the morning commands are in `plans/speech-fidelity-loop/write3/`. Over the 41,697 cached reports, before change E, the parser gives SPEECH 968,296 rows, PROCEDURAL 43,089, UNCLASSIFIED about 25,000, CHAMBER_EVENT 6,133, EDITORIAL_NOTE 2,534, DOCUMENT_TEXT 1,793 and HEADING 1,429. The largest UNCLASSIFIED classes are division lists, oath-roll names and unanchored procedural lines. `0969500` changed no speaker and no transcript on any of those reports.

Rows by kind, whole table, after the rehearsal of plan v4: SPEECH with a speaker 963,407, SPEECH with no speaker 488, PROCEDURAL 46,868, CHAMBER_EVENT 5,800, EDITORIAL_NOTE 2,286, DOCUMENT_TEXT 2,584, HEADING 2,570, UNCLASSIFIED 20,579 and NULL 4,146.

Round 2 re-aggregated under both rules (details in the [stopping rule](../speech-fidelity-stopping-rule.md)): Tier A by rows 1.97% (bound 2.58%) and by characters 0.77% (1.04%); Tier B by rows 1.72% (2.60%) and by characters 0.88% (1.48%).

### Round 3 reading, provisional

Round 3 reads against a scratch copy with write 3 applied: the round 2 reports whose windows a write touched, then tranche 1 of a fresh draw. Its verdicts carry over only if the morning ship equals the rehearsal. Status: provisional, read on the rehearsal copy of write #3. Re-read: 158 reports. Tranche 1: 216 reports and 3,448 rows, Tier A 0.79% (bound 1.88%) and Tier B 0.90% (bound 1.42%), both by characters. These are pooled estimates: tranche 1 and the re-reads with the 174 round 2 reports whose windows write 3 does not touch, 548 reports and 9,824 rows in all. By rows, Tier A is 1.38% (bound 2.85%) and Tier B 1.14% (1.79%). Nine batches were read twice; single-reader recall was 100% for Tier A and 92.6% for Tier B, so no recall adjustment applies. Decision on tranche 2: Scenario S3 of the brief fired (Tier A point 0.79% by characters, above 0.7%), so tranche 2 was not read and the classes behind Tier A are the next fixes.

Tier A fails on one cluster. Report 22149, a Budget statement whose bold-italic headings were read as speaker labels, carries 0.55 of the 0.79 points. The classes to fix next, by weight: headings or footnote lines taken as speaker labels (22149; the `*Cols.` footnote rows in 21548; a division list credited to the Prime Minister in 39514); first readings credited to their presenter in older-system reports, which carry no proc text tag (17 reports); and procedural lines that miss an anchor ("Amendment by leave, withdrawn." without its comma, "Amendments, by leave, withdrawn.", a supply-head "ordered to stand part" line). Three older-system adjournment motions credited to their mover from the "- [Name]" tag were scored as accepted, as round 2 did; scored as Tier A they add little. Tier B passes on the sample (bound 1.42%, gate 2%) and on both detectors; its classes are paragraphs cut across rows inside `<pre>` blocks or at markers, and footnote digits glued to a word. Kind was not scored: readers flagged 184 of 6,672 round 3 rows, mostly UNCLASSIFIED rows that could be PROCEDURAL, DOCUMENT_TEXT or HEADING, and headings stored as SPEECH.

### The ship of write 3 (16 October)

The user approved the ship of plan v4 on the morning of 16 October. It shipped on the fifth attempt, committed on the remote at 16:03. Plan v4 went onto the replica once, at 09:36. `apply_fix4` committed it with 0 unexplained rows, and its figures equal the rehearsal's. Every attempt ran a delta shipper against the same before and after snapshots of the replica.

| Attempt | Outcome |
|---|---|
| 1, 09:37 | The rehearse's 404,891-row kind-only UPDATE hit the shipper's 600 s statement timeout and rolled back |
| 2, 10:15 | The user approved a 3,600 s timeout. The permission system refused the edit to the shipper, so nothing ran |
| 3, 10:47 | With the user's 3,600 s timeout the rehearse passed (51 checks, lock 3,004 s). The commit's connection closed 34 minutes into the lock, during the ordinal-and-kind UPDATE, and the server rolled it back. A read-only session minutes later ended with "terminating connection due to administrator command". The cause is not known |
| 4, 12:48 | The user stopped the ship during the rehearse, to shrink the lock first. The rehearse rolled back on its own (51 checks, lock 2,606 s) |
| 5, 14:07 | Shipped with `ship_delta6.py` |

The remote equaled its pre-ship hashes before every attempt and after every rollback.

`ship_delta6.py` takes kind out of the locked transaction. The 1,004,419 rows whose only changes are kind, or ordinal and kind, get their final kind first, in 201 batches of 5,000 rows, each its own short transaction. A batch writes kind only where the stored row has kind NULL and its other columns still have the before md5. It writes no row that fails that test, and any failure stops the run before the lock. The locked transaction then writes only the ordinal of the ordinal-and-kind rows. It checks that both classes carry the pre-step kind over unchanged content, and it verifies every touched row against the replica, kind included. Text, speakers, deletes, inserts, markdown and attendance all stayed inside the lock. The tool also sets TCP keepalives and times each check inside the lock. Before it touched the remote, it passed eight drift tests on a 1,028-report subset of the replica. Between the pre-step and the commit, the web app's kind filter saw about 1.0M rows with their final kind, while the 27,775 rewritten rows had none and the 12,388 new rows did not exist yet.

| Step on the remote | Result |
|---|---|
| Pre-step, 201 batches, each committed | 1,698 s, median 7.2 s a batch, longest 30.2 s; 0 rows failed the guard |
| Kind counts after the pre-step | As expected: 1,004,419 rows with a kind, 40,175 NULL |
| Rehearse | 54 checks, lock 1,717 s, rolled back |
| Gate before the commit | Every table equal to the pre-ship hashes, speech compared with kind read as NULL |
| Commit | 54 checks, lock 1,944 s, committed |

Inside the commit's lock, the drift checks took 72 s and the deletes and the 27,775 rewrites 68 s. The 599,528 ordinal writes took 1,494 s. The inserts, markdown and attendance took 62 s, and the verify 244 s, 138 s of it the final row counts. The ordinal writes are three quarters of the lock. Each one rewrites the row and its index entries, the full-text index on the transcript included. The old shipper held the lock 3,004 s in its rehearse.

After the ship:

- The replica equals the remote by `table_hashes.sql` on every table and sequence: speech 1,048,728 rows, attendance 135,027, alembic `7c1d4e9a2b60`.
- Rows by kind on the remote: SPEECH 963,895, PROCEDURAL 46,868, UNCLASSIFIED 20,579, CHAMBER_EVENT 5,800, DOCUMENT_TEXT 2,584, HEADING 2,570, EDITORIAL_NOTE 2,286 and NULL 4,146.
- The figures equal the rehearsal's in the tables above, now as stored. Parliaments 0 to 11: ADR 0001 rate 526,807 / 538,255 = 97.87%, all-rows rate 526,807 / 607,756 = 86.68%, text share 181,359,552 / 186,290,919 = 97.35%. The detectors give 632 dictionary hits (9.84 per million tokens) and 235 punctuation hits (3.66).
- The cache markdown was refreshed from the replica: 5,584 reports and 44 sittings.

### The user's rulings, 16 October

- Report 42017's seven rows keep kind UNCLASSIFIED. They are a notice of motion that no member spoke.
- The three older-system adjournment motions credited to their mover through the "- [Name]" tag (21168, 37767, 33560) count as accepted, as rounds 2 and 3 scored them.
- `hansard_w3`, the round 3 reading copy, is kept until round 4 is aggregated.
- Cycle 4 fixes these classes in this order: headings and footnote lines read as speaker labels, then procedural lines that miss an anchor, then older-system first readings credited to the presenter.
- Write 4 may rebuild the 41 held reports in the 22149 class. Their stored rows match no parser version, every row was checked against the source, and none shows a hand edit.

### Still open

- Push: the write 3 commits are on master and pushed.
- Review findings 6 to 13, including finding 11 on the 1,568-report rebuild.
- How a wrong `kind`, and a SPEECH row with no speaker, score under the stopping rule.
- A NOT NULL constraint on `kind`, an override file with the right speakers for the 465 rows, and round 3 tranche 2.
- The "Still open" list at the end of the Round 1 section above is out of date: write 2 fixed F5 and F4.

## Write 4 and round 4

Cycle 4 began on 16 October while write 3 waited to ship, and finished after it landed at 16:03. It fixed the three classes round 3 named, prepared the rebuild of 42 held reports as the user ruled, and re-read what the writes touched. The fixes are committed on master as `b33a028`, `acd8707` and `2b74a2b`. Write 4 was built, verified and rehearsed on clones of the replica. It shipped to the remote at 07:48 on 17 October (54 checks ok, lock 14 s). Round 4 passes both gates. It was read on `hansard_w4`, the clone with the plan applied, and, for 114 tranche 2 reports, early on the replica. After the ship, `build_r4.py verify` on the replica found the 672 pooled reports unchanged, so the verdict is final. It is under "Round 4" below.

### Why 22149 was a stale-row problem

Round 3 put 0.55 of its 0.79 Tier A points on report 22149, a Budget statement whose bold-italic headings were read as speaker labels. That looked like a parser defect and is not one. The write 3 parser already reads those headings as headings, and its parse gives the Budget statement to the Minister. The stored rows are the problem. Plan v3 and plan v4 both held 22149, v4 as `hold:provenance_none`, which means its stored rows equal the output of no parser version. Write 3 left them as they were. They credit the Budget statement to "Best place for families" and four other headings: 115 rows and 24,902 countable characters. The round 3 reading copy came from plan v3, so it carried the same rows and the readers scored them.

The shape is not unique to 22149. Of the 162 reports plan v4 held, 47 credit text to a string that names no person: 537 rows (156,323 characters) to headings, 96 (7,623) to table captions and cells, 69 (3,780) to agenda titles, 11 (2,884) to junk strings and 14 (4,400) to a label cut by a column marker. That is 727 rows and 175,010 characters. A read of all 47 against the source HTML explained 41 of them. Every stored transcript is source text (6,008 of the 6,030 stored rows are found in the source as they stand; the other 22 are table rules, link-markup rows, `&;` artefacts and two source oddities). Of the 201 row pairs the parse joins, 130 have a column or page marker between them and 27 are registered suspension or adjournment lines; 44 are too short to test. In the 41 explained reports no stored word is lost outside the registered drops, and no sign of a hand edit shows. The user ruled on 16 October that write 4 may rebuild those 41. The user also approved 38719, a 42nd report, which round 4 turned up (see "The release").

### The three fixes

Each fix was checked against the parser before it, first on every report that can reach the changed code and then on the whole cache of 41,811 reports. Each adds golden fixtures; 70, 89 and 97 tests pass at the three commits, and ruff is clean.

| Fix | Commit | Class | Credited before | After | Whole-cache check |
|---|---|---|---|---|---|
| 1 | `b33a028` | Page-reference and numbered footnotes; division records and lists | Footnotes 721 rows in 233 reports (22,412 characters); division records and lists 527 rows in 13 reports (about 9,500) | 9 and 5 rows, correct or listed below | 421 reports change, all older system. 0 words lost or gained. 1,057 rows lose their speaker, and 185 more in the 5 reports where a record is cut out. 145 "Ayes. Noes." headings and 79 column references change kind only |
| 2 | `acd8707` | Procedural lines that miss an anchor | 665 lines in 392 reports (23,984 characters) and 119 record rows after them in 39 reports (7,175) | 29 near-miss rows, listed below | 437 reports change. 0 words lost or gained. 784 rows lose their speaker and 88 change kind only |
| 3 | `2b74a2b` | First readings credited to their presenter | 2,090 rows, 531,677 characters: older first readings 2,018 rows and 522,792 characters, related lines 23 and 704, newer system 49 and 8,181 | None in the formula; 12 reports keep a credited row, listed below | 2,144 reports change. 355 words regained in 29 reports, none lost. 2,054 rows become no-speaker PROCEDURAL one to one, 29 pairs merge, 7 rows split, 68 change kind only |

Fix 1 gives a page-reference note ("*Cols. 3929-3930.") and a numbered note beside it kind EDITORIAL_NOTE, and cuts a division record that the source printed straight after a member's words ("Division, Sir. The House divided: ...") into its own PROCEDURAL row. Fix 2 widens the procedural anchors to their misspellings and variants, so "Amendment by leave, withdrawn." without its comma (270 rows in 107 reports) and a bare "Question put." (48 rows in 46 reports) stop being credited. Fix 3 uses the formula of a first reading as the stand-in for the `(proc text)` tag the older system never had. The formula line, the bill's title quote and any time stamp or heading before it become one no-speaker PROCEDURAL row, and text after the formula stays with the presenter. In 29 newer-system reports the presenter was bold and read as a label, which had dropped the words "presented by"; those words come back. The sources for all counts are `plans/speech-fidelity-loop/cycle4/fix1/COUNTS.md`, `fix2/COUNTS.md` and `fix3/`.

### The release

Write 4 rebuilds 42 reports, as the user approved on 16 October 2026: the 41 explained reports of the 22149 class, and 38719. The 41 are 23 motions, 7 budget statements, 4 oral answers, 4 written answers, 1 `written-answer-na`, 1 ministerial statement and 1 bill. Their stored rows credit 645 rows and 164,156 countable characters to headings, captions, agenda titles and junk strings. The rebuild gives that text to the member who was speaking, to the one `MPs Speaking` member of a motion, or to no speaker where the parse gives it none. In linked rows, 25,909 characters move to another member (18,658 in 26655 and 7,251 in 27156, where an unbolded label hid the next member) and 5,175 lose their link (3,570 in 38382, which holds division lists and resolution text).

22691 is in the set with a flag. Its rebuild leaves 18,706 characters of the Minister's resumed Budget speech with no speaker, because a suspension ends his turn and he resumes without a label. No linked row is lost there, since the stored rows credit those characters to heading labels. It is already a gap in `docs/vision.md`. 41804 is out of the set: its rebuild credits two procedural lines (89 characters) to Mr Lee Kuan Yew. Five more stay held with it: 22806 (a caption and a bold table cell are still read as labels), 23038 and 24839 (stored rows missing, with no recorded cause), 23268 (a footnote run swallows the speech after it) and 23627 (the parser drops a "Table 1:" caption).

38719 is a bill from Parliament 0 whose stored rows come from write 2. Round 4's early read found three paragraphs in it cut at column markers, and they put Tier B over its gate. Its rebuild is explained. Parser `6770752` run on the stored markdown reproduces all 438 stored transcripts exactly, so no hand edit shows, and the speakers differ only on six rows of the registered 14 October repair. The rebuild goes from 438 rows to 372 and from 157,545 to 157,613 countable characters. It joins 71 paragraphs cut at column markers (mid-sentence cuts fall from 68 to 8, the three round 4 found among them), cuts five inline "[Interruption]" directions into chamber-event rows (73 characters leave four members), removes three escapes and two glues, and keeps one pre-speaker line. No speech changes speaker. 15 stored words differ (13 escape variants and 2 glue splits) and none is lost.

One change in 38719 has no checker rule and is an approved exception. A "Column: 614" marker leaves a "****" line, and the parser splits one paragraph of Mr David Marshall into two rows, both his. The stored rows joined with one space equal the new rows joined with one space. The user accepted this one new cut for the 71 the rebuild joins. The stale-rebuild checker refuses 7 of 38719's 70 blocks: that split, the five inline-direction cuts, and "Mr Rajah resumed his seat." turned from a label into a no-speaker chamber event, which fits ADR 0007. The plan records the exception, and the exception file is `plans/speech-fidelity-loop/cycle4/write4/r2/approved_exception_38719.json`.

### The plan and the rehearsal

Write 4 is a delta on the write 3 state, built on master `2b74a2b` against the replica after the write 3 ship. The plan is `cycle4/write4/r2/plan_w4_release2.pkl`; it supersedes a 41-report plan that differed only in 38719. The planner's tools build the stack from the three commits, check every changed report against a checker written from each fix's contract, and refuse a report whose stored rows or markdown differ from the write 3 parse. The checkers explain 421 of 421, 437 of 437 and 2,144 of 2,144 changed reports with no refusal, and every planted error in the mutation tests (14, 9 and 26 cases) is refused. The 162 reports write 3 held and 24248 get no write, kind included, apart from the 41 released reports, which are built in a separate plan slot and merged.

The plan applies 2,923 reports (2,881 by the fixes and 42 released) and holds 121, none of them a new write 4 hold. The 121 are the 120 of write 3's 162 that are not released, and 24248. It writes 8,729 speech updates (3,234 of them ordinal only), 361 kind-only updates, 443 deletes, 66 inserts and 25 report markdowns. Of the 5,495 updates that change content, fix 1 accounts for 1,061, fix 2 for 767, fix 3 for 2,089, fix 1 and fix 2 together for 86, fix 2 and fix 3 together for 8, and the release for 1,484. The release also writes 3,205 ordinal-only updates, 414 deletes, 54 inserts and all 25 markdowns. In the plan fix 1 is a cause in 405 reports, fix 2 in 428 and fix 3 in 2,141. `verify_stack4.py` finds no problems, and 1,048,351 speech rows remain, 2,275 of them with kind NULL.

The rehearsal ran on clones of the replica on 16 October (17:40 to 22:37). `apply_fix4` committed with 0 unexplained rows. All eight drift tests (delete, insert, kind content, kind third kind, ordinal, report markdown, update, row count) aborted and rolled back. The shipper rehearse and commit passed 56 checks each, the two clones ended equal by `table_hashes.sql` with 0 diff lines, the replica was unchanged, and the applied clone equals `hansard_w4`. The shipper is `bin/ship_delta6_stack4.py`, a copy of `ship_delta6.py` that stages each row's before kind, because write 4 moves 361 rows from one kind to another and `ship_delta6.py` assumes NULL before kinds. The upload is 4.7 MB against 375 MB for write 3. The lock held 0.9 s on commit and 2.9 s on rehearse on a local clone. The planner expects about 40 s on the remote from write 3's measured rates, and under two minutes with the hotspot's latency. The run needs about 1 GB of disk and peaked at 1.4 GB of memory. It shipped at 07:48 on 17 October with 54 checks ok and a 14 s lock. The commands are in `plans/speech-fidelity-loop/cycle4/SHIP_w4.md`.

Parliaments 0 to 11 first, then 12 to 14, with write 3 as stored beside the write 4 rehearsal.

| Metric | Stored, after write 3 | Write 4 rehearsal |
|---|---|---|
| ADR 0001 rate | 526,807 / 538,255 = 97.87% | 523,056 / 533,817 = 97.98% |
| All-rows rate | 526,807 / 607,756 = 86.68% | 523,056 / 607,408 = 86.11% |
| Text share | 181,359,552 / 186,290,919 = 97.35% | 180,926,723 / 186,290,255 = 97.12% |

| Scope and metric | Stored, after write 3 | Write 4 rehearsal |
|---|---|---|
| Parliament 12, ADR 0001 rate | 82,170 / 83,077 = 98.91% | 82,102 / 83,004 = 98.91% |
| Parliament 12, all-rows rate | 82,170 / 86,480 = 95.02% | 82,102 / 86,458 = 94.96% |
| Parliament 12, text share | 29,041,974 / 29,443,992 = 98.63% | 29,027,236 / 29,443,992 = 98.58% |
| Parliament 13, ADR 0001 rate | 132,205 / 134,547 = 98.26% | 132,194 / 134,536 = 98.26% |
| Parliament 13, all-rows rate | 132,205 / 139,516 = 94.76% | 132,194 / 139,509 = 94.76% |
| Parliament 13, text share | 41,810,025 / 42,329,130 = 98.77% | 41,808,220 / 42,329,130 = 98.77% |
| Parliament 14, ADR 0001 rate | 206,946 / 208,878 = 99.08% | unchanged |
| Parliament 14, all-rows rate | 206,946 / 214,976 = 96.26% | unchanged |
| Parliament 14, text share | 59,399,644 / 60,051,708 = 98.91% | unchanged |

| Where the body text goes | Stored, after write 3 | Write 4 rehearsal |
|---|---|---|
| Linked rows | 97.35% | 97.12% |
| Rows with an unlinked speaker string | 0.67% | 0.58% |
| ADR-excluded rows | 0.05% | 0.05% |
| Rows with no speaker | 1.63% | 1.96% |
| Reports with no rows | 0.11% | 0.11% |
| Dropped inside reports with rows | 0.19% | 0.19% |

The ADR 0001 rate rises because rows that are not speech lose their speaker and leave its denominator. The all-rows rate and text share fall for the same reason, and fix 3 carries most of the text-share change. In Parliaments 0 to 11 the fixes take 568,484 countable characters out of linked rows (513,428 of them from fix 3), and the release puts 135,655 back with the members who were speaking. The release also lowers the body-character count by 664. The breakdown by cause, from the rehearsal (points are percentage points of the all-rows rate and text share for the scope of the table):

| Cause (Parliaments 0 to 11) | Linked rows | All rows | ADR denominator | Linked characters | All-rows points | Text-share points |
|---|---|---|---|---|---|---|
| Fix 1: page-reference notes, division records | -1,031 | +3 | -1,058 | -26,522 | -0.170 | -0.014 |
| Fix 2: variant procedural lines | -674 | 0 | -759 | -26,321 | -0.111 | -0.014 |
| Fix 3: first readings | -1,991 | +7 | -2,005 | -513,428 | -0.329 | -0.276 |
| Fix 1 and fix 2 on the same rows | -84 | +2 | -84 | -1,677 | -0.014 | -0.001 |
| Fix 2 and fix 3 on the same rows | -8 | 0 | -8 | -536 | -0.001 | 0.000 |
| Release: 42 held reports rebuilt | +37 | -360 | -524 | +135,655 | +0.057 | +0.073 |

| Cause (Parliaments 12 to 14) | Linked rows | All rows | ADR denominator | Linked characters | All-rows points | Text-share points |
|---|---|---|---|---|---|---|
| Fix 2: variant procedural lines | -5 | 0 | -7 | -277 | -0.001 | 0.000 |
| Fix 3: first readings | -74 | -29 | -77 | -16,266 | -0.010 | -0.012 |

Detectors, pipeline hits per million tokens, against the source typo rate:

| Test | Stored, after write 3 | Source typos | Write 4 rehearsal |
|---|---|---|---|
| Dictionary | 9.84 (632 hits) | 106.54 | 4.27 (274 hits) |
| Punctuation | 3.66 (235 hits) | 6.23 | 1.98 (127 hits) |

Rows by kind, whole table, in the rehearsal: SPEECH with a speaker 960,592, SPEECH with no speaker 488, PROCEDURAL 49,841, CHAMBER_EVENT 5,838, EDITORIAL_NOTE 3,187, DOCUMENT_TEXT 2,616, HEADING 2,570, UNCLASSIFIED 20,944 and NULL 2,275. The speech table holds 1,048,351 rows. Attendance does not change. After a ship, `table_hashes.sql` on the replica and the remote must be equal, the cache markdown must be refreshed from the replica, and `attribution_text_share.py` and the detectors must give the figures above.

### Round 4

Round 4 draws nothing new. It re-reads the pooled reports that write 4 touched, checks Tier A against Scenario S3 on the character rule, and reads tranche 2 only if S3 does not fire. The pool is round 3's 548 reports and 9,824 rows: 174 round 2 reports kept, 158 re-read in round 3 and 216 new in tranche 1. Tranche 2 is 124 reports and 2,298 rows that nobody had read. The user approved reading the reports write 4 does not change early on the replica (115 at first, 114 once 38719 moved to `hansard_w4`), with S3 still governing and any report that later proves touched read again. The other 10 are in the write 4 change set and were read on `hansard_w4`: the 9 touched reports and 38719.

A pooled report counts as touched, and its old verdict is dropped, when its window differs from the rows the reader saw in any of five ways: a different speaker or transcript on a row, a row gone, a new row between the first and last window row, a changed order, or, for reports read in round 3, a different kind. A uniform ordinal shift touches nothing, as in round 3. Write 3's inserted row ids differ between the round 3 copy and the shipped replica (shifts of 9 to 15 in 126 pooled reports), so the match uses id and content together. 34 of the 548 pooled reports were touched (455 window rows): 7 round 2 kept, 13 round 3 re-reads and 14 from tranche 1. One of them (22298) was touched by a kind change alone. Two (12000 and 45499) changed because write 3's plan v4 applied them while the round 3 copy, plan v3, held them. Readers got round 3's prompt with four added bullets for the row shapes write 4 creates: page-reference and numbered notes, division records and lists, procedural lines in variant spellings, and a first reading as one no-speaker PROCEDURAL row with its title quote. Cases the fixes leave credited stay errors. The three older-system adjournment motions credited to their mover (21168, 37767, 33560) and the seven rows of 42017 are scored under the 16 October rulings.

16 batches were read and 7 were read twice (round 3's 20% share per group, plus the batches that hold 22149, 21548, 39514 and 38719). Two Tier B disagreements, in `r4t2e_06`, were adjudicated by hand (a hyphen at a column end joined with a space, scored as a split). Single-reader recall was 100.00% for Tier A (50 of 50 error rows) and 91.43% for Tier B. The 34 re-read windows held 110 Tier A rows before write 4 (90 from round 3's new reports, 14 from its re-reads, 6 from round 2's kept) and hold none now, 22149, 21548 and 39514 among them. Scenario S3 did not fire: on tranche 1 alone the Tier A point is 0.05% by characters, under 0.7%, so the early tranche 2 reads count.

38719 needed a second look. The early read of its stored rows had put Tier B over the gate (1.46%, bound 2.69%), with 0.705 of those points on three of its paragraphs cut at column markers. The user approved its rebuild. Its re-read on the rebuilt copy (batch `r4t2_02`, window ordinals 303 to 343 of 372, first and second reader) found no error in any tier, and the aggregate drops the early read of its stored rows.

| Tier | Row rule point | Row rule bound | Character rule point | Character rule bound | Gate |
|---|---|---|---|---|---|
| Tier A | 0.08% | 0.12% | 0.05% | 0.08% | 1% or less, by characters: passes |
| Tier B | 0.84% | 1.10% | 0.75% | 1.03% | 2% or less, by characters, and both detectors under their source rates: passes |
| Tier C | 4.26% | 5.31% | 1.92% | 2.72% | None |

The pooled view holds 672 reports and 12,122 rows. On tranche 1 alone (548 reports, 9,824 rows) Tier A is 0.06% (bound 0.09%) by rows and 0.05% (0.09%) by characters, and Tier B is 0.83% (1.21%) and 0.68% (1.03%). The heaviest reports for Tier A by character points are 38079 (0.018), 497 (0.010), 15646 (0.004), 258 (0.004), 37684 (0.003) and 38610 (0.002). Tier B among round 4's own reads is split words (7 rows in 6 reports, 0.179 points), glued words (6 rows in 4 reports, 0.081) and paragraphs cut at column markers (14 rows in 4 reports, 0.018). Readers flagged 199 of 9,043 round 3 and round 4 rows for kind (2.20%), which gates nothing. The aggregate is `plans/speech-fidelity-loop/cycle4/r4/aggregate_r4.md`.

Done. The stopping rule's three conditions hold on round 4. Tier A's weighted upper bound by characters is 0.08%, under the 1% gate. Tier B's is 1.03%, under the 2% gate, and both detectors are under their source rates (4.27 and 1.98 per million tokens against 106.54 and 6.23). Every remaining class is listed with its corpus count under "Found and not fixed" below and in `docs/vision.md`. The readers worked on the write 4 rehearsal copy, and on the replica for 114 tranche 2 reports. Write 4 shipped unchanged, and `build_r4.py verify` on the replica then found the 672 pooled reports unchanged.

### Found and not fixed

The census, the fix surveys and the held read found these classes and left them. Counts are corpus counts on the cached reports. The second census (`cycle4/census/CENSUS2.md`) counted on master `2b74a2b`, the three fixes included; the fix surveys counted before or after their own fix as each row says. `docs/vision.md` repeats the list under "Where more work stops paying".

| Class | Rows | Reports | Countable characters | Tier and why it stays |
|---|---|---|---|---|
| Italic title stored as a SPEECH row | 9,782 | 1,094 | 293,008 | Tier C. 60 of 60 read were headings. 9,318 rows are heading-like. Not fixed |
| Of those, an italic title that closes a member's run and is credited to the previous member | 2,281 | 157 | 49,933 | Tier C. 1,978 before write 3. 15 of 15 read were credited to the wrong member |
| Bare time stamp credited to a speaker | 51 | 51 | 427 | Tier C. 1,262 before write 3. All 51 read were real: "12.00 noon", "midnight", colon and dotted forms. A "#### * * *" row credited to Mr Speaker in 33044 is not counted |
| "#### [... in the Chair]" credited to a speaker | 0 | 0 | 0 | 524 before write 3 |
| `<pre>` table stored one row per line | 18,591 | 863 | 388,269 | Tier C. 25 of 30 sampled tables were tables, so about 15,500 rows are real, mostly division lists. The table test misreads prose with a margin note |
| Prose cut across rows inside `<pre>` | 1,021 (542 cuts) | 162 | 37,103 | Tier B, a lower bound: a cut whose next line starts with a capital or a digit is not flagged. 29 of 30 sampled cuts were real. 327 of the cuts sit in blocks with inner tags, which the joiner skips |
| Footnote digit glued to a word or number | 1,157 (1,462 hits) | 869 | 401,308 | Tier B. 29 of 30 sampled hits were footnote digits. 185 hits in 147 reports change a number ("2481"). 1,336 hits are newer system |
| Labels that are not people | 113 | 15 | 9,081 | Found by the census, outside the three classes. Headings 52 rows in 7 reports (33559 alone is 45 rows, a heading taking 6,292 characters of Dr Tan Cheng Bock's speech), a table caption and cell in 22806 (8), a report title in 32642 (5), junk such as a bold "Question" or "To ask" (48). About 7,000 of the characters are a member's or the chair's text |
| Member speech swallowed by a footnote run: 23268, after footnote 2 | 6 | 1 | 1,297 | A short italic subheading after the note stops `_get_speech_start_position`. Of 640 look-alike rows, a read of every run and 44 sampled draws found no other speech. 23268 stays held |
| Caption text dropped after a bold "Table N:" (23627, 43250) | 2 lines | 2 | 23 words with the label | `_TABLE_CAPTION_RE` skips the whole line, not only the label |
| Caption-only bold lines, dropped by design since WS3 | 42 lines | 28 | 475 words | A heading line gets no row; listed in the register |
| Reports with markdown and no rows | 0 | 702 | 220,800 (208,633 in Parliaments 0 to 11) | 22 reports hold prose a person said or wrote (94,547 characters): 14 ministers' addenda to the President's Address with no label (51,563) and 8 addenda or written texts (42,984; 33574 alone is 27,467). 16 hold procedural records or first readings (2,500; 34587 among them). The other 664 are appendix stubs, assent lists, adjournment records and order-read stubs |
| A column marker that leaves a `****` line, so a paragraph stays cut across it (the F4 shape) | 770 (405 cuts) | 293 | 694,905 | Tier B, older system only, a lower bound (11.6% of the 153,919 markers could not be located). About 300 to 355 of the 405 cuts are real: 15 of 20 sampled were, and the 5 others follow a link-title line. Without the 50 cuts after a link-title line: 684 rows, 259 reports, 678,438 characters. The marker removal leaves an empty `<b></b>`, html2text strips the next text node, and a paragraph running from one marker to the next loses the trailing space the page-break pattern needs. The 9 cuts kept in 38719 are this class, and its approved split at "Column: 614" is one of them. Listed, not fixed |
| Latent honorific gap: `_SPEAKER_HONORIFIC_RE` and `_is_speaker_name` do not know Miss, Madam, Che, LG or COL | 0 today | 0 | 0 | No stored line hits it. A bold-only "Miss Penny Low" line with no colon would be skipped. 6,828 "Miss" and "Madam" rows (2,461,263 characters) depend on the colon |
| "Miss Penny Low (Pasir Ris-Punggol" cut at an unclosed bracket (24708), and an unspaced "AssocProf" (16466, not counted) | 14 | 1 | 4,436 | Probably a source typo; the counts are for 24708 |
| Near-miss procedural lines fix 2 leaves: "The amendment(s) read(s) as follows:" with no marker (9 rows, 8 reports), "Original Question put, and agreed to." (6), "Resolved." and a quoted "Resolved." motion (5), "Bill accordingly read the Third time." (2), "+The following amendments stood in the name of ..." (2), and one row each for "Questions proposed.", "Resolution, reported", an OCR comma in "stood in the, name of", "Amendment made: ..." and "Clause .2, as amended, ordered ..." | 29 | up to 27 | 1,051 | Tier A. Each needs a new rule or its own decision. "Resolved." would split the collapsed row in 7 reports. About 10 Schedule lines with italic marks inside the words lose their speaker and stay UNCLASSIFIED |
| First-reading leftovers: OCR-typo formulas in 4 reports (33648, 35994, 38770, 39997), 25885 (no "presented by"), the split tail of 22343, trailing headings and time stamps after a first reading in 6 reports (31849, 33558, 36585, 39390, 39730, 42737), and "theSenior" or "theSecond" glue in 13945, 13946 and 13953 | at least 12 | 15 | not counted | Tier A for 6 reports, Tier C for 6, Tier B for 3. The regex needs "presented ... by ... read ... First time". The glue appears when a bold run starts with no space after a word and the `**` markers go |
| "The voting was as follows:-" (5 rows) and "Division Bells rung." (4 rows) credited to the chair | 9 | not counted | not counted | Tier A. Out of fix 1's scope; each needs its own anchor |
| Footnote continuation lines (21601) | not counted | 1 | not counted | Found while checking fix 1; not sized |
| Double-marker notes ("**Col. 1005, ..." in 22949, "** Cols. 291-2" in 43048) and "(1)IATA" notes with no space (21163) | 4 | 3 | not counted | Tier A. A bold marker sends the line down the bold branch, which skips the footnote set. The numbered-note pattern needs a space after "(1)" |
| Reports still held after write 4 | kind NULL on 2,275 | 121 | not counted | The 120 left of write 3's 162 and 24248, which gets no write. Includes 22806, 23038, 23268, 23627, 24839, 41804 and the hand-edited 22647 and 22650 |
| 22691's resumed Budget speech with no speaker | not counted | 1 | 18,706 | A suspension ends the Minister's turn and he resumes without a label; a candidate for `data/unattributed_speech.json`. Listed, not scored |

Kind is not scored. Readers flagged 199 of 9,043 round 3 and round 4 rows (2.20%), mostly UNCLASSIFIED rows that could be PROCEDURAL, DOCUMENT_TEXT or HEADING, and headings stored as SPEECH. UNCLASSIFIED holds 20,944 rows in the rehearsal.

### Still open

- Write 4 shipped at 07:48 on 17 October. The replica and the remote hash equal by `table_hashes.sql`, and `build_r4.py verify` found no touched window.
- Push: the write 3 commits and the three fix commits are on master and pushed.
- Review findings 6 to 13, including finding 11 on the 1,568-report rebuild.
- How a wrong `kind`, and a SPEECH row with no speaker, score under the stopping rule.
- A NOT NULL constraint on `kind`, and an override file with the right speakers for the 465 rows.
- Tier B and C classes in the table above that write 4 did not touch.
- `hansard_w3` stays until round 4 is aggregated, by the user's ruling. `hansard_w4` was dropped after the round 4 readers finished.
- The "Still open" lists above are out of date: write 2 fixed F5 and F4, and write 3 shipped.

## Write 5 (17 October)

Write 5 is the w5 parser patches on master, from `7da899c` (01a) to `e9952f6` (09), and the 188 stage 8 links of patch 05 (`9b88a95`). The plan was built against the replica after write 4 and the ten fix-run writes, with the tree at `git archive e9952f6`. It was rehearsed on scratch clones of the replica from 08:52 to 09:10: 0 unexplained rows, every drift test aborted and rolled back, and the clones ended equal by table hashes. It shipped to the remote at 09:29 (lock 124 s, 56 checks ok), and the replica equals the remote by table hashes. The stored figures equal the rehearsal's.

It applies 2,910 reports and writes 11,523 row updates (11,335 planned content updates plus the 188 links), 30,769 ordinal-only updates, 145 kind-only rows, 12 ordinal_kind rows, 325 deletes, 3,511 inserts, 1,014 report markdowns and 7 sitting markdowns. No attendance row changes.

| Group | Measure | Before | After |
|---|---|---|---|
| P0-11 | ADR 0001 rate | 522,517 / 533,183 = 98.00% | 513,404 / 523,420 = 98.09% |
| P0-11 | All-rows rate | 522,517 / 606,746 = 86.12% | 513,404 / 609,701 = 84.21% |
| P0-11 | Text share | 180,732,303 / 186,092,895 = 97.12% | 180,788,738 / 186,092,945 = 97.15% |
| P12 | ADR / all-rows / text | 98.91%; 94.96%; 98.58% | 99.00%; 94.91%; 98.64% |
| P13 | ADR / all-rows / text | 98.26%; 94.76%; 98.77% | 98.28%; 94.74%; 98.79% |
| P14 | ADR / all-rows / text | 99.08%; 96.26%; 98.91% | 99.08%; 96.24%; 98.92% |

By cause, P0-11. Columns are linked rows, all rows, ADR denominator and linked characters, then the cause's share of the change in all-rows and text-share points.

| Cause | Linked rows | All rows | ADR denominator | Linked characters | All-rows / text-share points |
|---|---|---|---|---|---|
| p01a | -39 | -46 | -40 | -371 | 0.000 / 0.000 |
| p01a+p07 | -11 | -1 | -15 | -277 | -0.002 / 0.000 |
| p01a+p09 | -10 | -10 | -10 | -30 | 0.000 / 0.000 |
| p04 | +115 | +11 | -58 | +80,901 | +0.017 / +0.043 |
| p04+p07 | +38 | +1 | -7 | +5,928 | +0.006 / +0.003 |
| p05 (links) | +142 | 0 | 0 | +163,847 | +0.023 / +0.088 |
| p06 | 0 | 0 | 0 | +42 | 0.000 / 0.000 |
| p06+p07 | -3 | 0 | -3 | -157 | 0.000 / 0.000 |
| p07 | -9,175 | 0 | -9,461 | -244,459 | -1.505 / -0.131 |
| p07+p09 | -2 | -1 | -2 | -17 | 0.000 / 0.000 |
| p08 | +4 | +3,172 | +5 | +16,225 | -0.447 / +0.009 |
| p09 | -252 | -252 | -252 | 0 | -0.006 / 0.000 |
| title rebase (22789, 23760, 43147) | +80 | +81 | +80 | +34,803 | +0.002 / +0.019 |

Patch 02 changes no row. Ordinal shifts change no figure.

Detectors, pipeline hits per million tokens: dictionary 4.269 (274 hits) before and 4.282 (275 hits) after, against a source rate of 106.45; punctuation 1.979 (127 hits) and 1.977 (127 hits), against 6.23.

Rows by kind, whole table, before and after: SPEECH 960,290 to 950,502 (488 with no speaker, unchanged), HEADING 2,569 to 12,358, DOCUMENT_TEXT 2,615 to 5,388, PROCEDURAL 49,817 to 50,381, UNCLASSIFIED 20,937 to 20,784, CHAMBER_EVENT 5,837 to 5,838. EDITORIAL_NOTE stays at 3,186 and NULL at 2,275. The speech table goes from 1,047,526 to 1,050,712 rows.

The plan holds 181 reports. 121 are the write 3 and write 4 holds, still held with no write of any kind. 60 are new, each refused by a checker: 56 for patch 06 (the marker takes the space next to the superscript and glues words, a defect in the patch), 3 for patch 04 (the widened table-row test reads a label line with a "|" as a table row in 15632 and 46541, and 38222 folds a heading, a time stamp and a bill title into a first-reading row) and 1 for patch 09 (38147). 172 sitting markdowns that change are held and 7 are applied; attendance is the same in all 179.

## Write 6 (17 October)

Write 6 is the two parser fixes `53eac45` (keep the space next to a footnote marker) and `204dbff` (keep a member's label when the speech holds a pipe), and the stage 7 attendance names of `558b971`. The plan was built against the replica after write 5. It was rehearsed on scratch clones from 10:42 to 11:04: 0 unexplained rows, every drift test that applies aborted and rolled back, and the clones ended equal by table hashes. The speech ship ran from 11:16 to 11:19 on 17 October (lock 10.0 s, total 13.1 s). The rehearsal and the commit each logged 52 checks ok.

It rebuilt 55 reports and wrote 131 speech row updates, 55 report markdowns and 5 sitting markdowns. It wrote no delete, insert, kind change or link, so the speech table stays at 1,050,712 rows. 3 more reports parse the same as stored. The plan holds 123 reports: the 121 older holds and 2 new ones (38147, refused by the p09 checker, and 38222, where the parse folds a heading, a time stamp and a bill title into a first-reading row).

`scripts/apply_attendance_names.py` then set 496 stored names in 79 spellings in 227 sittings, on the remote at 11:25 and on the replica at 11:27. A second run planned 0 on each, every row kept its `speaker_id`, and attendance stays at 135,083 rows. After the ship the remote and the replica hash equal by `table_hashes.sql` (11:30), and the cache refresh changed 55 report and 5 sitting markdowns and nothing else.

| Group | Measure | Before | After |
|---|---|---|---|
| P0-11 | ADR 0001 rate | 513,404 / 523,420 = 98.09% | 513,398 / 523,414 = 98.09% |
| P0-11 | All-rows rate | 513,404 / 609,701 = 84.21% | 513,398 / 609,701 = 84.20% |
| P0-11 | Text share | 180,788,738 / 186,092,945 = 97.15% | 180,788,469 / 186,092,971 = 97.15% |
| P12 | ADR / all-rows / text | 99.00%; 94.91%; 98.64% | 99.00%; 94.91%; 98.64% |
| P13 | ADR / all-rows / text | 98.28%; 94.74%; 98.79% | 98.28%; 94.74%; 98.79% |
| P14 | ADR / all-rows / text | 99.08%; 96.24%; 98.92% | 99.08%; 96.24%; 98.92% |

The detectors read dictionary 4.282 and punctuation 1.977 per million tokens, unchanged.

### Still open

- The 123 held reports keep their older rows.
- Review findings 6 to 13, including finding 11 on the 1,568-report rebuild.
- How a wrong `kind`, and a SPEECH row with no speaker, score under the stopping rule.
- A NOT NULL constraint on `kind`, and an override file with the right speakers for the 465 rows.
- Tier B and C classes that no write has touched.
- Push: the write 6 commits (`53eac45`, `204dbff`, `558b971` and this record) are on master and not pushed.

## Census of speaker labels, after write 6 (17 October)

Two detectors count speaker labels in the speech table. DS-05 counts labels that are not a person, an office or a group. DS-09 counts unlinked labels that name a person who exists as a Person or Speaker row. `label_census.py` in the fix run's census folder runs both on the replica; it is not in the repository. The run was read-only, from an export of master at `6fbc89b`, and counted on 17 October 2026 after write 6. Every unlinked label was read by hand with its first transcript words: 94 strings on 17,371 rows, and so were the 6 linked strings that a DS-05 shape flags. The readings of 16 October carried over for every label that still exists. Four labels were new and were read again: "RADM LUI TUCK YEW" and three bracketed office labels whose nested bracket the parser now closes. Characters are countable characters, as in `scripts/attribution_text_share.py`.

The first census, on 16 October, counted the write 3 data. The fix run held its figures under the 5% rule, because the counts on the write 4 rehearsal had already moved: 431 DS-05 rows in 50 reports and 254 DS-09 rows in 152 reports. After write 6 they have moved again.

| Class | Rows | Strings | Reports | Characters | Rows, 16 Oct |
|---|---|---|---|---|---|
| DS-05 heading | 79 | 14 | 11 | 20,872 | 788 |
| DS-05 sentence fragment | 13 | 4 | 5 | 3,044 | 162 |
| DS-05 table caption or cell | 40 | 8 | 3 | 1,496 | 81 |
| DS-05 junk | 4 | 2 | 2 | 559 | 38 |
| DS-05 total | 136 | 28 | 20 | 25,971 | 1,069 |
| DS-09 total | 67 | 25 | 24 | 29,907 | 268 |

By group, P0-11, P12, P13 and P14, DS-05 holds 132, 3, 0 and 1 rows, and DS-09 holds 63, 1, 0 and 3. Rows with kind NULL are rows of reports that no write has rebuilt. They number 86 for DS-05 and 0 for DS-09, and every other counted row has kind SPEECH. Eight DS-05 rows are linked to the right person. Their label carries a stage direction, as in "The Leader of the House (Mr Wong Kan Seng) stood up, and addressing himself to the Clerk of Parliament said". Every other counted row is unlinked. Offices and groups, which are valid labels, hold 17,167 of the 17,371 unlinked rows. Nine more rows name two men who have no Person: Andrew Fong and A. V. Winslow.

The personas findings counted three DS-05 shapes and three DS-09 shapes on production before write 3. The same SQL gives these figures today, on the unlinked rows.

| Shape | Before write 3 | Write 3 data | After write 6 |
|---|---|---|---|
| DS-05 label with a finite verb | 174 | 174 | 31 |
| DS-05 label in capitals | 192 | 36 | 2 |
| DS-05 label starting with `[`, `(`, `_`, `*` or a quote | 395 | 229 | 39 |
| DS-09 bracketed titled name | 96 | 69 | 35 |
| DS-09 "Name (Mr Speaker)", counted inside the line above | 59 | 34 | 0 |
| DS-09 leading quote before a titled name | 35 | 35 | 0 |

The drop follows write 5, which carried the label fixes `0089cc3` and `9b88a95`, and the report rebuilds of writes 4 to 6. It is not traced row by row.

Of the 67 DS-09 rows, 66 would link to the named person. The other one is a "Resolved" line, so a link would credit a line no member spoke. The resolver links none of the 67 today. The Person of every DS-09 string except the four with no Person sat in the Parliament of each of its reports, checked against the Speaker rows. A report of the colonial era is checked against Parliaments 0 to 3, as the resolver does since write 9 moved the Assembly-only members to Parliament 0.

## Write 7 (17 October)

Write 7 is DS2-01 (`864bd22`, an unbolded label that carries a language note starts that member's turn) and DS2-02 (`cdae744`, older-system entity characters are kept), with the register rows in `f6ea861`. It was rehearsed on scratch clones, and the rehearsal and the commit each logged 52 checks ok. The speech ship started at 15:44, the speech part finished at 15:58 and the whole ship at 16:03 on 17 October (lock held 108.1 s, total 135.3 s, with 73.8 MB uploaded before the lock).

It rebuilt 1,132 reports and wrote 8,001 speech row updates. 7,868 change characters only. 36 DS2-01 label rows change speaker and lose the label from their text, and 97 rows after a label change speaker. It wrote no insert, delete, kind or ordinal change, so the speech table stays at 1,050,712 rows. It also wrote 1,118 report markdowns and 131 sitting markdowns. Stage 7 re-derived on the replica gives the same 135,083 attendance rows, so no attendance write was made. Stage 8 linked 132 of the 133 rows whose speaker changed, each to the member the label names. "Inche Rahamat" (38006) has no Speaker row under that short name and stays unlinked. The plan holds 126 reports: 37959, 20889 and 43635 are new and none of the older 123 was released. After the ship the remote and the replica hash equal, and the cache refresh changed 1,118 report and 131 sitting markdowns and nothing else.

| Group | Measure | Before | After |
|---|---|---|---|
| P0-11 | ADR 0001 rate | 513,398 / 523,414 = 98.09% | 513,405 / 523,415 = 98.09% |
| P0-11 | All-rows rate | 513,398 / 609,701 = 84.20% | 513,405 / 609,701 = 84.21% |
| P0-11 | Text share | 180,788,469 / 186,092,971 = 97.15% | 180,790,066 / 186,092,963 = 97.15% |
| P12 | ADR / all-rows / text | 99.00%; 94.91%; 98.64% | 99.00%; 94.91%; 98.64% |
| P13 | ADR / all-rows / text | 98.28%; 94.74%; 98.79% | 98.28%; 94.74%; 98.79% |
| P14 | ADR / all-rows / text | 99.08%; 96.24%; 98.92% | 99.08%; 96.24%; 98.92% |

The dictionary detector reads 4.266 per million tokens (274 hits), down from 4.282 (275 hits). The punctuation detector stays at 1.977 (127 hits).

### Still open

- The 126 held reports keep their older rows.
- 750 sitting-level Deputy Speaker speech links from another session's `b489bd6` and `b3b6c79` are not shipped. They need a separate write.
- Unbolded bare-name labels with no language note, about 89 rows. Reading them as turns would release 37959.
- The adjournment-mover shape with an en dash in 20889 and 43635. Both are held.
- "Inche Rahamat" in 38006, which has no Speaker row under that short name.
- Review findings 6 to 13, including finding 11 on the 1,568-report rebuild.
- How a wrong `kind`, and a SPEECH row with no speaker, score under the stopping rule.
- A NOT NULL constraint on `kind`, and an override file with the right speakers for the 465 rows.
- Tier B and C classes that no write has touched.
- Push: the write 7 commits (`864bd22`, `cdae744`, `f6ea861` and this record) are on master and not pushed.

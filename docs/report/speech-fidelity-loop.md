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

Commit `88f6b34`. `utils/markdown_parser.py` deleted `&nbsp;` from older-system HTML. The newer system's branch already turned it into a space. Both systems now replace it with a space before html2text runs. An emphasis tag that holds only `&nbsp;` becomes a single space, because otherwise it would render as a stray `__` or `****`.

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
| F1 | `1251a7c` | The report header table (its `Title:` and `MPs Speaking:` fields) became the start of a single-speaker row | | 2,745 |
| F7 | `91e1349` | A speaker label with nested bold lost its title, so `****Mr X** :**` was not read as a label | 3 | 26 |
| F3 | `2f1492d` | html2text escapes such as `\.` and `\-` stayed in the text | 10,253 | 4,862 |
| F6 | `0e5ad27` | A bare `&` came out with a `;` after the next word (`R&D.;`, `F&B;`) | 335 | 1,020 |
| F2 | `c628314` | A link kept its URL in the text; now only the link text stays | 1,759 | 4,068 |

The report and row counts for F7, F3, F6 and F2 are from each fix's own dry run. They overlap, so they do not sum to the combined write.

F1 went in at 10:33 on 15 October. It changed 2,745 rows, with 0 unexplained.

### A metric change

Text share counted the `Title:|` and `MPs Speaking:|` header fields as body text the parser dropped. They were 1.72M of 188.1M characters. Commit `e1bba7d`, approved by the user, leaves them out of the denominator. On the same stored rows, text share moves from 96.59% to 97.48%. F1 then lowered it by 0.07 points, because 135,406 characters of metadata had counted as linked speech. The user accepted that. Text dropped inside reports with rows fell from 1.22% to 0.41%.

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

Write 2 shipped at 15:46 on 15 October through the local replica and the delta shipper. It carried WS1 to WS6, F5, D1, D2, F2b and F4, committed as `2de9bdf` to `c33e922`, each with a golden fixture. 19 tests pass.

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

Write 3 is the stack of parser fixes committed on master from `7fb6ce1` on, 23 commits, then the kind column and changes A to E, five more commits (see "The overnight run"). The planner built the write from them in steps: each commit has a checker, and a chain checker explains every changed row in order. The stale reports (stored rows that differ from the current parse) are rebuilt when their stored rows equal some parser version's output, the rule the user set on 15 October. The 1,568 near-match reports follow the 30-report check below.

| Commit | What it does |
|---|---|
| `bcb0af2` | PA1: oath rolls and procedural one-liners get no speaker |
| `9df9966`, `1884d53` | PA2 and PA3: a labelled "rose" line keeps the name; labelled assent, dissent and resumed-seat lines end the turn |
| `8e876a2` | PA4: bold "Hon. Members" mid-sentence stays in the speaker's row |
| `55e99a6` | PA5: footnotes and amendment text get no speaker |
| `517b2c1` | PA6: procedural lines split out of single-speaker collapsed rows |
| `d411ea9` | PA7: inline directions split out of speaker rows |
| `4ee4713` | TB1: wrapped prose lines inside preformatted blocks are joined |
| `ee9ff50` | TB2: adjourned and suspended directions split across blocks are joined |
| `27f6d46` | TC1: bold markers are stripped from transcripts |
| `8dae2fc`, `eeb4d61` | BG, Encik and other titles are accepted on long speaker labels, at the start of a label only |
| `af6e516`, `493ef00` | A footnote that opens with a hash marker stays out of the headings; a long underscore line is read as a footnote rule |
| `d867d90`, `e100380` | A bracketed note cut by a column marker is joined, with its space kept |
| `a8c5ffc` | The first copy of a paragraph printed twice around a stray tag is dropped |
| `a3c1246`, `a950b25` | Gestures and more inline directions are split out; the split stops mutating its arguments |
| `9209f01`, `c104e58` | The leading title line leaves single-speaker collapsed rows; a "Resolved" heading stays as the body of a collapsed report |
| `e37853a` | Text before the first speaker is kept as rows with no speaker |
| `aca7ebe` | Speech after a closed footnote keeps its speaker |

The user decided on 15 October (late) to keep the preamble as rows with no speaker, to rebuild the 1,568 near-match stale reports after a reader sampled 30 and found no hand edit, to accept the 21 "repair tranche" reports, and to fix four defects the stale checker found in HEAD: the BG, Encik and RAdm titles that long labels dropped, the `#Text` footnotes in 23398 and 23401 dropped as headings, the split of 20991's vernacular note, and 24516's duplicated sentence. On 16 October the user kept the 24516 fix, approved renumbering ordinals, approved shipping with `ship_delta4.py`, accepted the fall in the all-rows rate and text share as designed, ruled that "Head NNNN -" preamble fragments are Tier C, put 24248 on the per-report Tier A list, and set round 3 as re-reads plus tranche 1.

Plan v2 (on `cecfc20`, before changes A to E) applies 11,271 reports (9,502 clean and 1,769 stale rebuilt) and holds 162. It carries 628,210 speech updates (601,802 of them change the ordinal only), 8,253 deletes and 13,051 inserts, 3,210 report markdown updates, 44 sitting markdown updates and 45 junk attendance deletes. A replay of every applied report equals the final parse. The ship test ran on clones of the replica. The apply committed with 0 unexplained rows. Five drift tests all aborted before any write. The rehearsal and commit passed 49 checks, and the local and target tables had equal hashes. `ship_delta4.py` sends an ordinal-only update as `id` and `ordinal`, which cut the speech upload from 321.4 MB to 69.9 MB.

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
| A | `speech.kind`, a nullable Postgres enum, migration `7c1d4e9a2b60`; the parser sets it on every parsed row | `e8b8804`, `2eef141` |
| B | A direction is cut out of its paragraph; the paragraph stays whole and keeps its row, and the direction follows as a CHAMBER_EVENT row. A parse of the cached reports changes 702 reports and leaves 1,153 fewer rows than the three-row split, with no text lost | `9050403` |
| C | `data/unattributed_speech.json` lists ten entries: the eight chair-resumption reports, 31083 and 24248's opening speech (30 rows). The rows in a listed range that carry the listed label get no speaker and kind SPEECH. 42017 is left out | `72d4d64` |
| D | The stopping rule weights Tier A and B by characters and requires a full source pass | this change |
| E | A `(proc text)` pair that wraps a whole block stays in the markdown (10,060 of 10,107 pairs); that line becomes a no-speaker PROCEDURAL row, inside collapsed reports too. Other pairs keep the old treatment. A parse of the cached reports changes 2,762 markdowns and 941 reports' rows, and 1,132 credited rows become PROCEDURAL | `0e4a110` |

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

B is commit `9050403`, C the 465 unlinks of brief decision 7, and E commit `0e4a110`, which acts on newer-system reports only and so has no row for Parliaments 0 to 11. Points are percentage points of the all-rows rate and text share for the scope of the table.

Detectors, pipeline hits per million tokens, against the source typo rate:

| Test | Stored, after write 2 | Source typos | Write 3 rehearsal |
|---|---|---|---|
| Dictionary | 31.8 | 106.6 | 9.84 |
| Punctuation | 12.66 | 6.24 | 3.66 |

Both detectors are now under their source typo rates; the punctuation detector was over it before. Pipeline hits fall from 2,038 to 632 (dictionary) and from 812 to 235 (punctuation) on 64.2 million tokens.

The ship candidate is plan v4 on `4174a7c`: 12,337 reports applied, 162 held, 627,303 speech updates (599,528 of them ordinal and kind only), 404,891 kind-only updates, 8,254 deletes, 12,388 inserts, 5,584 report and 44 sitting markdowns, and 45 junk attendance rows. It equals plan v3 on `72d4d64` plus the 12 newer-system reports that `4174a7c` fixes (it trims a space left inside a proc text tag). Both plans were rehearsed in full; the figures above are v4's, the detectors and the cause tables v3's, which differ by those 12 reports at most. The plan and the morning commands are in `plans/speech-fidelity-loop/write3/`. Over the 41,697 cached reports, before change E, the parser gives SPEECH 968,296 rows, PROCEDURAL 43,089, UNCLASSIFIED about 25,000, CHAMBER_EVENT 6,133, EDITORIAL_NOTE 2,534, DOCUMENT_TEXT 1,793 and HEADING 1,429. The largest UNCLASSIFIED classes are division lists, oath-roll names and unanchored procedural lines. `2eef141` changed no speaker and no transcript on any of those reports.

Rows by kind, whole table, after the rehearsal of plan v4: SPEECH with a speaker 963,407, SPEECH with no speaker 488, PROCEDURAL 46,868, CHAMBER_EVENT 5,800, EDITORIAL_NOTE 2,286, DOCUMENT_TEXT 2,584, HEADING 2,570, UNCLASSIFIED 20,579 and NULL 4,146.

Round 2 re-aggregated under both rules (details in the [stopping rule](../speech-fidelity-stopping-rule.md)): Tier A by rows 1.97% (bound 2.58%) and by characters 0.77% (1.04%); Tier B by rows 1.72% (2.60%) and by characters 0.88% (1.48%).

### Round 3 reading, provisional

Round 3 reads against a scratch copy with write 3 applied: the round 2 reports whose windows a write touched, then tranche 1 of a fresh draw. Its verdicts carry over only if the morning ship equals the rehearsal. Status: provisional, read on the rehearsal copy of write #3. Re-read: 158 reports. Tranche 1: 216 reports and 3,448 rows, Tier A 0.79% (bound 1.88%) and Tier B 0.90% (bound 1.42%), both by characters. These are pooled estimates: tranche 1 and the re-reads with the 174 round 2 reports whose windows write 3 does not touch, 548 reports and 9,824 rows in all. By rows, Tier A is 1.38% (bound 2.85%) and Tier B 1.14% (1.79%). Nine batches were read twice; single-reader recall was 100% for Tier A and 92.6% for Tier B, so no recall adjustment applies. Decision on tranche 2: Scenario S3 of the brief fired (Tier A point 0.79% by characters, above 0.7%), so tranche 2 was not read and the classes behind Tier A are the next fixes.

Tier A fails on one cluster. Report 22149, a Budget statement whose bold-italic headings were read as speaker labels, carries 0.55 of the 0.79 points. The classes to fix next, by weight: headings or footnote lines taken as speaker labels (22149; the `*Cols.` footnote rows in 21548; a division list credited to the Prime Minister in 39514); first readings credited to their presenter in older-system reports, which carry no proc text tag (17 reports); and procedural lines that miss an anchor ("Amendment by leave, withdrawn." without its comma, "Amendments, by leave, withdrawn.", a supply-head "ordered to stand part" line). Three older-system adjournment motions credited to their mover from the "- [Name]" tag were scored as accepted, as round 2 did; scored as Tier A they add little. Tier B passes on the sample (bound 1.42%, gate 2%) and on both detectors; its classes are paragraphs cut across rows inside `<pre>` blocks or at markers, and footnote digits glued to a word. Kind was not scored: readers flagged 184 of 6,672 round 3 rows, mostly UNCLASSIFIED rows that could be PROCEDURAL, DOCUMENT_TEXT or HEADING, and headings stored as SPEECH.

### Still open

- The user's go to ship write 3 with the delta shipper. Nothing was written to the remote speech table and nothing was pushed.
- Review findings 6 to 13, including finding 11 on the 1,568-report rebuild.
- Report 42017's seven rows are a notice of motion that no member spoke. They take kind UNCLASSIFIED, against brief decision 7, which said SPEECH ([ADR 0009](../adr/0009-speech-kind-column.md)). One 7-row UPDATE to SPEECH reverses the call.
- How a wrong `kind`, and a SPEECH row with no speaker, score under the stopping rule.
- A NOT NULL constraint on `kind`, an override file with the right speakers for the 465 rows, and round 3 tranche 2.
- The "Still open" list at the end of the Round 1 section above is out of date: write 2 fixed F5 and F4.

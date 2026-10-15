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

Every rate is weighted by N_h / n_h. The bound is the one-sided 95% Clopper-Pearson bound on the Kish effective sample size. A row keeps its verdict across rounds unless a later write touched its report. A Tier B or C class that touches fewer than about 100 rows and needs a row-count change goes on a residue list with its corpus count in `docs/vision.md`. Round 6 is a hard cap. If it ends first, the loop reports which gate failed and by how much.

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

# Speech fidelity loop

Started 14 October 2026. The loop checks stored speech rows against their source HTML, fixes the defects it finds, and repeats with a fresh sample until a round finds none. It began with report `00004736-WA.00002403-WA_1`, which stored "they are notlousier than Singapore", "Sir,I" and "reports.I". The source has `not&nbsp;lousier`.

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

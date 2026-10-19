This is the stopping rule as of 15 October 2026. Amended 16 October 2026; see "Amendments" at the end.

# Speech fidelity loop: stopping rule

Agreed with the user on 15 October 2026. This replaces "stop when a round finds zero errors" in step 5 of `speech-fidelity-loop-handoff.md`. The round 6 cap still holds.

Revised the same afternoon after the sweep study in `sweep-ideas/report.md`. Wrong-speaker errors and F4 cuts both cluster by report, so the gates are now measured on whole reports, not independent rows. The tier of headings, chamber events and time stamps credited to a speaker is now fixed.

## Why zero errors is not the gate

A round reads about 400 rows. Zero errors in 400 rows bounds the true rate below 0.75% at 95% confidence, and no lower. If the true rate is 0.5%, a 400-row round comes back clean only 13% of the time (0.995^400), so the gate fires reliably only near 0.2%. Classes that live in one report (F5) can turn up in any round, so the loop could run past round 6 with nothing left worth fixing.

## Tiers

Each finding's `error_class` maps to a tier. The tier says how much the error hurts a researcher using the speech table.

| Tier | `error_class` | Harm | Gate |
|---|---|---|---|
| A | `wrong_speaker`, `lost_text`, duplicated or reordered text, a chamber event credited to a speaker, and a first reading credited to its presenter | Corrupts the speaker index (vision objective 2) | Upper bound ≤ 1%, weighted by characters |
| B | `glue`, `split`, and a paragraph cut across rows at a column, page or preformatted line break (F4, filed as `other` in round 1) | Breaks word and phrase search; the pending `transcript_tsv` column would index the broken token | Both detectors below the source typo rate, and upper bound ≤ 2%, weighted by characters |
| C | `markup_residue`, `mangled_label` where the label still names the right person, a heading or bare time stamp credited to a speaker, a "Head NNNN -" preamble fragment kept as a row with no speaker (kind HEADING), and a `<pre>` table stored one row per line | A reader skips a stray `__` or a heading | No rate gate. Fix only with a mechanical rule whose write leaves zero unexplained rows |

Boundary cases:
- F4 goes in Tier B, not A. The text survives under the right speaker, in order, and only the row boundary is wrong. Wrapped prose inside `<pre>` (946651) is also F4. A `<pre>` table stored one row per line (27866, 36142) is Tier C.
- A `mangled_label` that names the wrong person, as F7's `****Mr X** :**` shape does in reports 22647, 22650 and 43315, is `wrong_speaker` and goes in Tier A.
- A chamber event credited to a speaker is Tier A, matching the 14 October non-speech repair. Round 1 scored this shape both ways (884024 as wrong_speaker, 779727 as accepted); score it as Tier A from round 2 on. Reader files from round 2 and earlier call it `stage_direction_credited`. A direction cut out of a paragraph into a row of its own, with no speaker and kind CHAMBER_EVENT, is correct, and its place inside the paragraph is lost by design (ADR 0007), so a reader does not flag that.
- A first reading collapsed under its presenter ("presented by the Minister ...; read the First time") is Tier A. Round 2's aggregator scored it as accepted, by analogy with the motion mover tag; the overnight brief of 15 October 2026 rules otherwise, consistent with ADR 0007, which gives the same text no speaker. Where the source tags a whole block `(proc text)`, the parser gives it no speaker and kind PROCEDURAL. A first reading the source does not tag stays credited to its presenter and counts.
- A heading (524 rows of `#### [... in the Chair]`, 1,978 italic titles) or a bare time stamp (1,262 rows) credited to a speaker is Tier C. List them with counts in `docs/vision.md`.

The 1% bound for Tier A beats the published peer figures in `docs/vision.md` and `sweep-ideas/report.md`: the Knesset corpus's 98.3% hand-checked speaker-name correctness (1.7% error), and GermaParl v2's 0.6% wrong speaker plus 0.64% missing.

## How to measure

- Weight Tier A and Tier B by characters. A row counts by its transcript's countable characters, the count `scripts/attribution_text_share.py` uses (`_get_countable_character_count`): whitespace and the markup characters `*`, `_`, `\`, `#` and `|` removed. A row with an error counts in full. The character rate is the weighted countable characters of error rows over the weighted countable characters of rows read. The character rate gates. Report the row rate beside it; it gates nothing. Report Tier C per row. Report Tier B per million tokens from the detectors.
- Weight every rate by the inverse of its selection probability. Never quote the unweighted share.
- Gate on a one-sided 95% upper bound, never the point estimate.
- **The unit of sampling for the gates is the report.** Round 1 logged one wrong-speaker row each in 17279, 33258 and 43017. Read whole, those reports held a 42-row run under The Chairman, 21 rows under sub-headings and five captions. F4 clusters too: 401 reports hold 19,195 of the 33,815 cut pairs. A bound that treats rows as independent comes out too narrow.
  - Draw reports stratified by version, type and era. Read every row of a report up to 60 rows. For a longer report, read a 41-row window at a random start, and weight it up to the report.
  - Estimate the Tier A and Tier B rates as weighted error characters over weighted characters read. Estimate the row rate, and Tier C, as weighted error rows over weighted rows read.
  - Bound it with a bootstrap over reports: resample reports within each stratum, 2,000 replicates, take the 95th percentile. The statistic in each replicate is the character rate.
- **Readers see the window cold first.** Each reader reads the rendered rows (`[ordinal] (speech id) SPEAKER {linked|unlinked|no speaker}: text`) and writes flags before opening any source. Then they classify each flag against the HTML. They log errors found only during the source check separately. `sweep-ideas/probes/build_coldread.py` builds the packets. This costs about twice the tokens of a row-level read.
- **Every reader does a full source pass.** After the cold read, the reader reads the whole source report against the rows of the window, and reports every error found in those rows, whether or not the cold read flagged it. The reader records the first and last ordinal checked for each report, so a half-checked window shows. Round 2 had one: report 21623, "checked [80] only, others assumed same". Single reads undercount. Round 2's second reads found as many or more Tier A rows than its first reads, and the aggregator's census added 54 Tier A rows, 17% of the total, that no reader flagged.
- **Census detectors count directly.** Rows found by a detector that reads every row, such as the unlinked-label census, count in full. They come out of the sampling frame, so they are not counted twice.
- Pool rounds. A report sampled in an earlier round keeps its verdicts if no later write touched it. Read it again if one did.
- The detector gate compares pipeline hits with source-typo hits on the same run. Rerun both detectors after every write.

### Sample size

This depends on how strongly errors cluster within a report, and that is not yet measured. Round 2's report sample gives the first figure. Until then, plan for more reading per round than the 400 rows of round 1. The row-level table in the first version of this rule assumed independent rows and understated the need.

## Residue instead of a fix

A Tier B or C class goes on the residue list instead of getting a fix when both hold:
- it touches fewer than about 100 rows corpus-wide (0.01% of 1.07M)
- the fix changes row counts, or touches stale or guard-refused reports

Tier A classes never go on the list this way. Each is fixed, or listed report by report.

## Done

The loop stops when all of these hold:
1. Tier A's weighted upper bound, by characters, is ≤ 1% on the pooled rounds.
2. Tier B's weighted upper bound, by characters, is ≤ 2%, and both detectors' pipeline rates are below their source typo rates.
3. Every remaining class, Tier C included, is listed with its corpus count under "Where more work stops paying" in `docs/vision.md`.

If round 6 ends first, stop anyway and report which gate failed and by how much.

## Where things stand

Round 1, from `r1/sample.json` and `r1/findings_all.json`, the 395 sampled rows only, panel rows left out. The bounds assume independent rows, so they are too narrow:

| Tier | Rows with an error | Unweighted | Weighted | Weighted upper bound (row-level) |
|---|---|---|---|---|
| A | 5 | 1.27% | 1.29% | 3.69% |
| B | 12 | 3.04% | 3.52% | 6.23% |
| C | 15 | 3.80% | 1.25% | n/a |
| Any | 31 | 7.85% | 6.00% | 9.18% |

The "about 7%" quoted for round 1 was the unweighted share. Weighted, it is 6.00%.

Corpus-wide, from `sweep-ideas/report.md` on the replica after round 1's combined write:
- F4: the cut rule flags 64,417 rows (6.03%) at 83% precision on a 60-row read, so about 5% of rows (estimated). F4 alone fails the 2% Tier B gate.
- Unlinked labels: about 1,320 rows (0.12%) are a heading or caption credited as a speaker (counted). Counted again on 16 October 2026 on the write 3 data, the same class is 907 rows (0.09%), and on 17 October after write 6 it is 123 rows (0.01%); see "Census of speaker labels, after write 6" in [speech-fidelity-loop.md](report/speech-fidelity-loop.md).

Detectors after round 0, per million tokens:

| Test | Pipeline | Source typos | Gate |
|---|---|---|---|
| Dictionary | 31.8 (2,041 hits) | about 107 (6,842 hits) | Passes |
| Punctuation | 12.8 (824 hits) | about 6.2 (399 hits) | Fails |

What this means for the plan:
- Fix F4 before round 2. Measure it before and after the fix with cut rule A (`sweep-ideas/data/cutoff_sweep.txt`, the SQL in `sweep-ideas/probes/cutoff_sweep.sql`) and the source-confirmed classifier (`sweep-ideas/probes/boundary_label_probe.py`, about 10 minutes for all reports).
- Tier A is the binding gate, and the handoff defers wrong-speaker classes (vision gap 3). They can no longer wait. Round 1's five are a table caption, a bold sub-heading inside a written answer, an unbolded stage direction, the Chairman's line followed by Grace Fu's unbolded speech, and a dropped final paragraph in a P14 written statement. The sweep adds `####` stage directions credited to the last speaker (614 rows, 14 of 15 read were Tier A) and inline bold runs with no letters that drop a whole paragraph (43 lines in 38 reports, among them 46433 and 11470).
- F5 is part of that inline-bold class and is Tier A, so the residue cutoff does not apply.
- F2, F3 and F6 should move the punctuation detector. Check it against 6.2 per million after the combined write.

## Outside the loop

These came out of the sweep study. They are separate changes, made after the loop and not by it:
- Add the 9 sets of byte-identical reports (26 reports) to `data/excluded_report_ids.json`. Recomputed on 17 October 2026 in the data sanity fix run: every byte-identical pair of one topic in one sitting is a DS-04 duplicate and is listed there. The other sets repeat source text under different questions, topics or sittings, and stay.
- Link "The Chief Minister" on 7 June 1956 (82 rows, probably David Marshall) by date, in the next stage 8 change.

## Amendments

### 16 October 2026

The user approved these changes on 15 October 2026 after an independent review of the loop's decisions, whose finding 3 is that the Tier A gate can pass on undercounted reads.

1. **Tier A and Tier B are weighted by characters.** A wrong speaker on one 3,000-word row counted the same as one on a one-line row. Plan v2 of write #3 inserts 13,051 rows, mostly short no-speaker rows that are easy to score as correct, and they dilute a row rate (decision review, finding 3). The character rate gates, and the row rate is reported beside it. Tier C stays per row and has no gate.
2. **Every reader does a full source pass.** The rule is in "How to measure".
3. **A first reading credited to its presenter is Tier A.** It was accepted in round 2 by the aggregator's ruling. It is now a boundary case under Tier A.
4. **Wording.** "Stage direction" is now "chamber event", the name of the CHAMBER_EVENT kind in ADR 0009. A "Head NNNN -" preamble fragment is Tier C.

Round 2 under both rules. The row columns are from the round 2 aggregate. The character rows use the same sample, normalisation and bootstrap, with each row counted by its countable characters.

| Tier | Gate | Row rate as scored in round 2 | Row rate, first readings Tier A | Character rate, first readings Tier A |
|---|---|---|---|---|
| A | ≤ 1% | 1.71%, bound 2.31% | 1.97%, bound 2.58% | 0.77%, bound 1.04% |
| B | ≤ 2% | 1.72%, bound 2.60% | 1.72%, bound 2.60% | 0.88%, bound 1.48% |

The row rates fail both gates. The first-reading ruling moves Tier A only. The pooling rule is unchanged: a round 2 report keeps its verdicts when no later write touched its window, and write #3 touches many windows, so those reports are read again under the full source pass.

Open, and not decided by the brief:
- How a wrong `kind` scores. Readers note it. It joins no gate until the user rules.
- How a row with kind SPEECH and no speaker scores. The rows named in `data/unattributed_speech.json` (the eight chair-resumption reports, 31083 and the opening speech of 24248) are in this group (ADR 0009). The speaker is missing, and no member is credited wrongly. Until ruled, a listed report stays in the sampling frame and its rows count as before.
- Whether round 1 and round 2 verdicts, read without the full source pass, stay in the pool as they are. The review suggested re-reading them or dividing by a measured reader recall. This amendment adopts neither.

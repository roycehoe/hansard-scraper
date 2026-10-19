# North star audit, second pass, 13 October 2026

An independent agent audited the project against `docs/vision.md` for records with a sitting date before 10 September 2012. It ran after the zero-row fix, the refetch of 1,691 skipped records and the guarded re-parse of 6,615 reports, in a git worktree frozen at `fb94560`, read-only on the database (snapshot 22:40 to 23:01 local). It formed its verdict before reading the project's own verdict, then reconciled. The brief repeated the first audit's four questions, added a fifth on whether the fixes flatter the result, and asked for a fresh hand check of about 100 speech rows, stratified by era and reported with a Wilson interval.

The orchestrating session checked four claims against the live database before recording this: sitting metadata lists are empty (confirmed: 0 of 1,333 sittings with HTML have sections, annexures, vernaculars or a PTBA list), "rose -" stage directions are linked to members (confirmed: 781 linked rows on a strict pattern, 1,001 on the auditor's looser one), the "_" exclusion hides real names (confirmed: "__MrChiam See Tong", "__Dr Teo Ho Pin", "__Mr Steve Chia Kiah Hong"), and three of the five wrong hand-check rows (confirmed by reading rows 145242, 275063 and 643914).

## Verdict

| Objective | Second audit | First audit |
|---|---|---|
| 1. Complete corpus coverage | Yes with caveats: about 99.3% of ranked search hits stored; about 147 skipped hits in early Parliament 12 never refetched | Yes with caveats |
| 2. Per-utterance speaker index | Partly | Partly |
| 3. Sitting metadata | Partly: attendance yes; PTBA, sections, annexures and vernaculars empty for all 1,333 sittings | Yes |
| 4. Speaker identity linking | Yes with caveats: 0 of 80 sampled links point to the wrong person | Partly |
| 5. High-fidelity markdown | Partly, now measured | Unverified |
| 6. Parsing-quality tracking | No | No |
| Overall | Partly | Partly |

The biggest gap: the headline rates count links that exist, not links that are right. A fresh hand check of 80 linked rows found 75 right (93.8%, Wilson 86.2% to 97.3%). About 85% of in-scope rows carry the right speaker for their text (90.59% of rows linked, times 93.8%), against a 97.6% ADR 0001 headline. Weighted by text the gap is small: 96.8% claimed text share against about 94.6% strict.

## Strict figures

| Measure | Project definition | Strict |
|---|---|---|
| Speech rows | ADR 0001 rate 97.61% | 90.59% of all in-scope rows linked (580,410 / 640,729); 89.4% counting only rows a fresh parse reproduces; about 85% after precision (78% to 88%) |
| Text share | 96.81% | 95.12% with no single-speaker collapse credit, a per-report cap, only rows a fresh parse reproduces, and the 0.41% html2text loss counted; about 94.6% after character-weighted precision |
| Report coverage | 21,132 of 21,693 records with text have rows (97.4%) | 96.7% of about 21,861 ranked search hits |

## Does `scripts/attribution_text_share.py` flatter the result?

Yes, by about 1.7 points. Its denominator is the markdown body after the parser's own start line, so it cannot see text html2text lost (report 22103 counts 0 body characters) and leaves out the 15 records with no text. Credit for single-speaker collapse is worth 0.90 points; stored rows the current parser would not produce are worth 0.40 points; the numerator has no per-report cap (0.04 points).

## What every "pass" check tests

`scripts/diagnose.py` passes a report when a start line is found. `scripts/run_sanity_check.py` passes when every speech has a non-empty speaker. `scripts/run_regression_check.py` passes when any `speaker_id` resolves, never checking which. `scripts/speech_speaker_match_rate.py` passes when a string resolves. All of them pass a report with a wrong speaker, lost text or merged text. Hand checks are the only correctness evidence.

## Found gaps the project chose or missed

- `utils/markdown_parser.py` deletes `&nbsp;` instead of replacing it with a space, gluing words ("Sir,schools") at 414,378 places in 18,044 reports. Overall 0.41% of HTML word tokens are lost; 120 reports lose more than 5%; report 22103 loses 97.7%.
- "X rose -" stage directions are stored as speech and linked to the member.
- Annex tables, division lists and clause text inherit the last speaker, usually "Mr Speaker".
- The ADR 0001 rule that drops speaker strings starting with "_" also drops real names written with a leading markup underscore.
- The 2,078 reports the re-parse guard refused hold 90,372 rows (11.2% of body text); 11,943 stored rows, 7,534 of them linked, would not come out of a fresh parse. 145 diverge by more than half. They include 673 linked "####" junk rows and table captions taken as speakers.
- In the 22 fallback reports, report 24248 drops Gan Kim Yong's 14,000-character mover's speech because his label merged into the heading, and 21988 stores a doubled label.
- About 147 Parliament 12 search hits before 10 September 2012 were never refetched, plus 6 gaps in the search numbering.

Gaps the source imposes: unnamed chairs (12,031 unlinked "The Chairman" rows in Parliaments 0 to 11), collective "hon. Members", procedural text with no speaker.

## Docs that disagreed with live data

| Doc claim | Live data |
|---|---|
| `docs/vision.md`: objective 3 "Yes" | Sitting lists are empty; PTBA text sits only in 41 sitting markdowns |
| `docs/vision.md`: 98.4% row precision | 93.8% in the fresh check; the 98.4% sample predates the rebuilds and capped 3 rows per key |
| `docs/vision.md`: about 11,600 unnamed-chair rows | 12,031 |
| `docs/vision.md` strategies: statistics exported after every run | `script.py` runs no report stage and exports nothing |
| `docs/data-dictionary.md`: `ordinal` starts at 0 | Starts at 1 |
| `docs/parsing.md`: about 1,449 zero-speech and 1,193 single-name docs | 576 zero-row reports; 3,032 single-speaker collapses |
| `docs/report/post-2012-text.md`: one record before 2012 lacks text | 15 |

## Not verified

Completeness against SPRS itself (no network), attendance precision, and role-holder links beyond the term tables in code.

# Vision

A complete, queryable record of Singapore's parliamentary proceedings, from the colonial Legislative Assembly through the present, for researchers studying political history at scale. The site built on it, openhansard.sg, is for people who read Hansard: someone who wants to find what an MP said and send it on, look up their own MP, quote a paragraph in an article, or question the name above it (hansard `docs/user-testing.md`).

The at-scale part of that goal needs the database published, and Parliament's terms of use require written permission to reproduce the content. The project will not ask for permission; it waits for a takedown request and acts on one. The site's `docs/corrections.md` and `docs/takedown.md` promise to take a report off the site within 2 working days of such a request. The unpublished database leaves the bulk-researcher goal unmet and outside the done tests.

## Scope

The project collects the record and sorts it so a reader can browse it, such as what a member spoke on and what they criticised in Parliament. It publishes no analysis of the record. Three kinds of analysis are out of scope even where the data would support them:

- Comparing parties with each other.
- Ranking members by a measure, such as how often they speak.
- Tracing how a member's views shifted over the years.

The test is whether a page sorts what the record prints or draws a conclusion from it. A member's speeches listed by date are in scope, and a summary of how their stand on a subject changed is not. The party breakdown of a division's vote is in scope too. It counts how each member voted, grouped by their party on the day, and draws no conclusion. Researchers who want such analysis can run it on the record themselves, which is what the bulk-researcher goal above is for.

The project is non-partisan on purpose. Its maintainers hold political views, as everyone does, and an analysis they chose to run and publish would carry those views in what it measured and how it framed the result. A reader who saw one side favoured there would have reason to doubt the record beside it. The site's colour scheme avoids party colours for the same reason (hansard `docs/palette.md`).

---

A write #N is one of the planned, rehearsed writes to the production database, numbered in the order they ran.

## Objectives

### 1. Complete corpus coverage

Fetch and store every Hansard entry published by SPRS, Parliament's Hansard site (sprs.parl.gov.sg), across all parliaments and all report types. No gaps from rate limits, format changes, or API quirks. The raw API response for every record is preserved exactly as received.

### 2. Per-utterance speaker index

Extract individual speeches from parliamentary transcripts and attribute each one to the correct speaker. Each `Speech` row is one utterance (a content line), with an `ordinal` preserving delivery order within its report. The speech table lets a researcher retrieve a speaker's speeches across the corpus in ordinal order. `Report.markdown_content` is the source of truth; speech rows form a derived index, not a line-for-line mirror.

Attribution should be as complete as the source allows. Only structurally unattributable documents, such as appendix link indexes and authorless colonial procedural orders, remain unattributed. Four structural limits apply by design:

- `Speech.speaker` may be `None` for utterances where no speaker attribution is possible. A row's `kind` says what a row with no speaker is ([ADR 0009](adr/0009-speech-kind-column.md)). The parser sets it on every row (`0969500`), and stored rows have it for every report rebuilt by write #3.
- Single-speaker documents are stored as one `Speech` row for the speaker's text rather than per-line rows. The report title is dropped from it, and procedural lines and a first reading become rows of their own with no speaker.
- Documents with multiple speakers but no bold speaker markup produce zero `Speech` rows.
- The report title, header fields, and blank lines get no `Speech` row. The parser keeps text before the first speaker as rows with no speaker under `e890946` ([ADR 0008](adr/0008-text-before-the-first-speaker-kept.md)); stored rows include it for every report rebuilt by write #3.

### 3. Rich sitting metadata

Capture every sitting's metadata: attendance, permissions to be absent, debate sections, vernacular speeches, and annexures. Both sitting date API formats are handled: the flat body of sittings before 10 September 2012, and the nested body from that date.

### 4. Speaker identity linking

Connect every speech and attendance record to a canonical speaker identity (name, party, and parliament number) sourced from parliament.gov.sg.

### 5. High-fidelity markdown

Convert HTML into readable markdown, removing html2text artifacts across the colonial, mid-era, and modern records without losing substantive content.

### 6. Parsing quality

Track parsing success rates per report type across the full corpus so regressions surface before they accumulate and improvement work is measurable.

### 7. Bills linked to their debates

Not met. After the Act-link write, three of the five tests below fall short of their targets: bill completeness (96.1% for 1961 to 2005, 99.3% from 2006, against 100%), outcome resolution (92.6% against 95%) and the review list (325 items against 0).

Group every `bill` and `bill-intro` report by bill, linking first reading, any select committee, committee stage, and third reading. Hansard prints no bill number, so the key is the bill's normalised title and the sitting date, with each bill closed at its third-reading line. Bills that no title rule can place go to a review queue. The feasibility study ([bill-debate-linking-2026-11-04.md](report/bill-debate-linking-2026-11-04.md)) found that the title and date rule reproduced the hand-built links for 72 of 72 sampled bills.

The goal is to hold every bill and link each one to its debates. Holding a bill means storing its bill number and a link to its text. Storing the text can follow later, because the links are the hard part. Five done tests apply, each reported by era (1955 to 1960, 1961 to 2005, 2006 on), from [bill-linking-rules-2026-11-08.md](report/bill-linking-rules-2026-11-08.md).

| Test | Measure | Target |
|---|---|---|
| 1. Bill completeness | From 1961, the bill numbers that have a `Bill` row, out of the highest number the Bills Supplement prints in each numbering series, so a missing number counts as a gap. Numbering is annual from 1966. Before that it ran in two series that crossed years: 124 to 214 from January 1961 to July 1963 (numbers 1 to 123 predate the listing and are left out) and 1 to 70 from October 1963 to December 1965. 1955 to 1960 has no outside list, so Hansard is its only list and it is reported apart | 100% from 1961 |
| 2. Debate completeness | Numbered bills whose group holds a first-reading report and, for a passed bill, a third-reading report | 100% |
| 3. Outcome resolved | Passed bills linked to an Act or to a published Act number, or classed as supply or repeal bills. Reported over every passed bill and, beside it, over the passed bills that are neither supply nor repeal (2,507 of 2,684 on 13 November 2026) | 95% |
| 4. Review list | Items the review-list script writes that no ruling has settled | 0 |
| 5. Precision | A hand-check sample of bill numbers, groups, and Act links, with a check run once on a known-bad input | [Tier A](#measuring-progress) under 1% |

Tests 1 to 4 come from a script; test 5 runs before the objective is called met and again after each rule change.

The bill-to-Act rules are in [bill-link-gap-2026-11-08.md](report/bill-link-gap-2026-11-08.md). A bill may link to a published Act number without its text or a guarantee that it is in force. `bill.act_number` and `bill.act_number_source` (first value ACTS_SUPPLEMENT_LISTING) store this claim separately from a current Act's Legislative History link. The planned printed-table path will store Act numbers with book and page; it is not built. The printed-bill-number fallback waits for the run over all 9,905 Legislative History entries. Refreshing the Act copies past October 2024 is on hold, because the eGazette links cover those 65 bills. For 1955 to 1960 only, a bill that exists only in print counts as held by a citation to volume, Supplement number, and page; nothing is built for it yet.

After the Act-link write, which read 526 Acts from copies fetched on 13 November 2026, production holds: 2,799 bills (2,684 passed), 5,833 reports grouped as readings, 2,936 budget reports attached to a Supply Bill, 526 Acts, and 10,258 Legislative History entries, 5,462 of them linked to a bill. Bill numbers come from the Bills Supplement listing for 2,344 bills and from the eGazette for 6, Act numbers from the Acts Supplement listing for 1,393 passed bills, and 441 passed bills link to a repealed Act's page. Current law is linked out to Singapore Statutes Online (SSO) and the eGazette, not hosted. Bills before 1961 and Acts as passed before 1985 have no free original text online, and the project will link their debates without one.

Five gaps remain. Bill-link counts below were counted on production on 13 November 2026; the site and permissions gap was counted on 6 November 2026:

- The site shows none of this yet. The `hansard` app reads none of the new tables, and `hansard_api` has no SELECT on them.
- 20 of the 67 passed bills last debated after 14 October 2024 have no Act history link. 11 of them, the 4 Supply Bills among them, link to their eGazette Acts Supplement, and the 9 passed from 4 August 2026 on have neither.
- 599 earlier passed bills have no Act history link, and 190 of them have no Act number, repealed Act page, or class either.
- The bills have not been compared with Parliament's count of 781 for 2006 to 2026.
- `scripts/remove_excluded_reports.py` can hit a foreign key error on a report that has a `billreport` row.

A passed bill whose Act is gone links to the SSO page that marks the Act repealed, so a reader can see the law no longer exists. The link is a separate claim (`bill.repealed_act_url`, source REPEALED_ACTS_LISTING), beside its Act history link and Act number. An amendment bill links to the Act it amended when that Act has since gone, and any other bill links to the Act of its title enacted in the year it was debated. Test 3 counts such a bill as resolved and prints the count apart. SSO lists only Acts repealed from 1985. A debate about a bill during the Parliament's term should link to that bill, so the `budget` reports (the Budget Statement and the Committee of Supply heads) attach to the year's Supply Bill as `billreport` rows with the role BUDGET_DEBATE, apart from the READING rows, when exactly one Supply Bill's debate window (first report less 45 days to last report plus 30) holds the report's date; a report whose title says supplementary, excess, or final goes to the Supplementary or Final Supply Bill instead. The measurement is in [bill-linking-build-2026-11-08.md](report/bill-linking-build-2026-11-08.md).

The current bill tests were counted after the Act-link write, in the review summary [`docs/figures/2026-11-13-bill-review.txt`](figures/2026-11-13-bill-review.txt). Test 1 holds 1,587 of 1,651 Supplement numbers for 1961 to 2005 (96.1%) and 763 of 768 from 2006 (99.3%), and test 2 is 100% in both eras. Test 3 resolves 2,485 of 2,684 passed bills (92.6%) and 2,308 of the 2,507 of no class (92.1%): 216 of 320 for 1955 to 1960, 1,504 of 1,590 for 1961 to 2005, and 765 of 774 from 2006. Test 4 lists 325 review items. The commands, in order, are in [bill-linking-build-2026-11-08.md](report/bill-linking-build-2026-11-08.md).

---

## Measuring progress

The project is not done. Tests 1 to 9 pass, test 7 with a listed residue and test 9 on being public only. Serving the whole corpus is unchecked, and takedowns are excluded by design. Test 10 is not met at 11 of 14 scheduled successes, counted on production on 2 November 2026; its deliberate-failure alert test passes.

Rerun the checks below before claiming any objective is met, and replace the current figures when they move. Move replaced figures and write history to [figures-history.md](report/figures-history.md). The corpus holds 41,801 reports.

Tier A errors corrupt the speaker index: wrong speaker, lost, duplicated, or reordered text, a chamber event credited to a speaker, or a first reading credited to its presenter ([tier definitions](speech-fidelity-stopping-rule.md#tiers)). Tier B errors break word and phrase search; Tier C errors include markup residue, headings, and time stamps.

### Next work and other gaps

Next work addresses the project's missed gaps; source limits and project choices remain separate. Rule D1 is the shared-link check in [CLAUDE.md, "Goal and how progress is measured"](../CLAUDE.md#goal-and-how-progress-is-measured): it checks where old shared links land after a write.

- The source imposes: unnamed chairs ("The Chairman" where the report gives no chair, 9,043 rows, and 67 "Mr Chairman", after the Chairman links), collective "hon. Members", bare "Mr Deputy Speaker" on two-holder days (454 rows across the table after the sitting-level links, which ADR 0002's refusals leave unlinked), annex pages that are lists of links, procedural lines with no speaker, and column markers the record skips, misprints or prints out of order (29,027 rows of Parliaments 0 to 11 with no column, 42 rows with a column that is likely misprinted and says so in a note).
- The project chose: the ADR 0001 denominator, collapsing single-speaker reports into one row, and a pass that means only that a title line was found.
- The project missed these, and they are the next work:

  1. After write #12, 19 reports keep rows from an older parser. Each needs a parser fix or a ruling before it can be rebuilt. The plan, the stored rows of every rebuilt report and two full `pg_dump` backups from before the guarded re-parse of 13 October 2026 were kept outside the repo; they are temporary unless moved.
  2. The stored rows drop 0.19% of body text inside reports with rows (after write #3). Headings, time stamps, chair annotations, and question numbers still get no row (decision review, finding 7, open). The split between the remaining classes is not measured.
  3. Unbolded speaker labels and lists inherit the last speaker. What remains is unbolded labels, lists inside a member's speech, 83 "Certificate of Urgency handed in." rows, 4 rows in two stale reports (26467, 27699) that the non-speech repair could not match, and 6 rows of a Budget statement in report 22691 resumed after a suspension, which have no speaker where they were credited to Mr Speaker. Annex tables after a heading are ministers' own tables in written answers and stay with them.
  4. Glued and split words, markup residue, lost text, and wrong speakers remain in the speech fidelity loop ([speech-fidelity-loop.md](report/speech-fidelity-loop.md)). Open work includes paragraphs cut inside `<pre>` blocks, the 5 footnote-digit rows of held report 23268, and review findings 6 to 13: the Tier C heading exemption, text dropped with no row, column numbers, vernacular marking, row identity, the 1,568-report rebuild sample, `footNote` and `mpNames`, and small points. The loop stops when Tier A's weighted upper bound by characters is 1% or less, Tier B's is 2% or less with both detectors below source typo rates, and every remaining class is listed with its corpus count here. Round 6 is a cap.
  5. The ADR 0001 rule that drops speaker strings starting with "_" also drops real names written with a leading underscore. Round 0 removed the stray `__` from 33 such labels, "__Dr Teo Ho Pin" among them. One name is left, `_S_ hawn Huang Wei Zhong (Jurong)` on 2 rows; the other 10 strings starting with "_" are italic headings.
  6. In report 24248 Gan Kim Yong's label merged into the heading, so the fallback start line once dropped his opening speech. The parser keeps it as 30 rows with no speaker and kind SPEECH (`052540d`), stored after write #3. The record prints no label for it, so the rows keep no label; `data/unlabelled_speech.json` credits them to Gan Kim Yong, and stage 8 stores the credit as a `speaker_id` once the write runs. The report is on the per-report Tier A list in [data-loss-register.md](data-loss-register.md).
  7. After write #3, for 465 stored rows in ten reports the speaker is known to be wrong. The right speaker is known for all of them except the 7 rows of 42017, a notice of motion that no member spoke, and it is not stored. The rows are unlinked. The ranges file now names the right member for nine of the ten reports, and stage 8 credits the rows without storing a label; 42017 stays out of the file.

### The three numbers

Three numbers measure how much of the record is linked to a member: the ADR 0001 rate, the all-rows rate, and text share. `scripts/attribution_text_share.py` prints all three for Parliaments 0 to 11. Parliament 0 is the Legislative Assembly, 1955 to 1965. Quote all three together. Never quote the first on its own.

| Metric | What it counts | Stored after write #13 ([figures](figures/2026-11-02-write13.txt)) |
|---|---|---|
| ADR 0001 rate | Linked rows / rows with a speaker string, minus "hon. Member(s)" and strings starting with "(" or "_" ([ADR 0001](adr/0001-attribution-denominator.md)) | 515,789 / 521,752 = 98.86% |
| All-rows rate | Linked rows and credited rows / every speech row, NULL-speaker rows included. A credited row has no label and a `speaker_id` | 515,789 / 609,915 = 84.57% |
| Text share | Characters of body text in a linked or credited row / characters of body text in every report with markdown, including reports with no rows. The denominator leaves out the report header fields (`Title:`, `MPs Speaking:`); the script (`efa477d`) leaves the `(proc text)` tag out of the count | 181,081,186 / 186,124,265 = 97.29% |

A row with no label and a `speaker_id` counts as linked in the all-rows rate and the text share, and stays out of the ADR 0001 rate, which is about labels. The table has no credited rows: credits from `data/unlabelled_speech.json` await a write (458 rows in 9 reports, plus 30 rows of 24248). The script logs credits separately, with JSON fields `credited_row_count` and `credited_character_count` beside linked counts.

Write #13 gave the clerk's record of a paper handed in, such as "Certificate of Urgency handed in.", no speaker and kind PROCEDURAL (`51ef90d`; the "A record that a paper was handed in" row in the [data loss register](data-loss-register.md)). It changed the speaker of 122 rows in 116 reports, all in Parliaments 0 to 11. After write #13 the speech table holds 1,115,837 rows.

Text share measures objectives 2 and 4 together: the record retrievable by speaker. Setting a row's speaker to NULL removes it from the ADR 0001 denominator, so that rate rises when the parser gives up on a line. The other two denominators retain those rows.

Text share overstates too. The [second audit](report/north-star-audit-2026-10-13.md), counted on 13 October 2026, found it about 1.7 points high: its denominator is the markdown after the parser's own start line, so text html2text lost is invisible, and a report collapsed to one speaker counts its whole body as attributed. Its strict text share is 95.12%, and about 94.6% after hand-checked precision. None of the three numbers says whether a link is right.

Where the body text goes, Parliaments 0 to 11, stored after write #3: 97.35% in linked rows, 0.67% in rows with an unlinked speaker string, 0.05% in ADR-excluded rows, 1.63% in rows with no speaker, 0.11% in reports with no rows, and 0.19% dropped inside reports that have rows. Every step that changes or drops source text, with its cost, whether it can be undone and who decided it, is in [data-loss-register.md](data-loss-register.md).

Whole-table rows by kind after write #5 ([ADR 0009](adr/0009-speech-kind-column.md)). The counts separate speech with no speaker from non-speech rows. A row with a speaker is always SPEECH.

| Kind | Rows, stored after write #5 |
| --- | --- |
| SPEECH, speaker known | 950,014 |
| SPEECH, speaker NULL | 488 |
| PROCEDURAL | 50,381 |
| CHAMBER_EVENT | 5,838 |
| EDITORIAL_NOTE | 3,186 |
| DOCUMENT_TEXT | 5,388 |
| HEADING | 12,358 |
| UNCLASSIFIED | 20,784 |
| kind NULL (reports write #3 did not rebuild) | 2,275 |

### What "parsed" means in each check

Automated passes do not establish that text has the right speaker.

| Check | Passes when | Misses |
|---|---|---|
| `scripts/diagnose.py` | A title line is found | Zero or wrong speeches; it discards the `get_speeches` output |
| `scripts/run_sanity_check.py` | Title found, at least one speech, no NULL speaker, on a fixed sample | Wrong speaker or lost text; it rewards crediting procedural lines to the last speaker |
| `scripts/run_no_speech_validation.py`, `scripts/run_exclusion_sanity_check.py` | A zero-row report has no bold speaker markup | Speeches without bold labels |
| `scripts/trace_speaker_links.py` | Stored links equal what the resolver returns today | Whether the resolver is right; role-context rows are not re-evaluated |
| `scripts/check_link_plausibility.py` | It always passes; it lists linked rows whose person was absent or unlisted that sitting, unlinked speaker strings outside the known-unlinkable classes, and sittings with a short attendance list | Wrong links to someone who was present; it cannot tell a wrong link from a wrong attendance row. Counted on 14 October 2026, it flagged 378 (report, person) pairs, and a 30-pair sample was 24 attendance errors, 0 link errors |

The only correctness evidence is by hand. The first hand check after write #10 found 996 of 1,000 right (99.6%, Wilson 99.0% to 99.8%). The precision of linked rows to quote is the second hand check, drawn after write #11 ([hand-check-2-2026-11-02.md](report/hand-check-2-2026-11-02.md)): 999 of 1,000 credited rows right, Wilson 99.44% to 99.98%. The same check compared every sampled row's words with the stored source. No row had a word lost, added, or changed (one-sided 95% ceiling 0.30%), and 7 of 1,000 had an error of any kind, 6 of them a stray space beside italics (ceiling 1.31%). Taken with the first hand check as one sample, 1,995 of 2,000 rows are right (Wilson 99.42% to 99.89%) and 14 have an error of any kind (ceiling 1.09%). By rows, Tier A is 0.07% (bound 0.12%) for Parliaments 0 to 11 and 0.02% (bound 0.04%) for Parliaments 12 to 14 ([round 5](report/speech-fidelity-loop.md#round-5)), and 0.00% for Parliament 15, where 0 errors in 5,754 rows give a bound of about 0.10% at round 5's design effect ([round 6](report/speech-fidelity-loop.md#round-6-parliament-15-20-october)).

### Parliaments 12 to 15, beside the headline

The latest stored figures for Parliaments 12 to 14 are after write #8 ([figures](figures/2026-10-18-write8.txt)); Parliament 15 is after its backfill (counted on 19 October 2026, [figures](figures/2026-10-19-backfill-15.txt)). `scripts/attribution_text_share.py` uses the same filters as the headline.

| Scope | ADR 0001 rate | All-rows rate | Text share |
|---|---|---|---|
| Parliament 12, stored after write #8 | 82,994 / 83,600 = 99.28% | 82,994 / 87,272 = 95.10% | 29,291,515 / 29,681,714 = 98.69% |
| Parliament 13, stored after write #8 | 133,042 / 134,514 = 98.91% | 133,042 / 139,601 = 95.30% | 41,854,202 / 42,329,888 = 98.88% |
| Parliament 14, stored after write #8 | 207,422 / 208,869 = 99.31% | 207,422 / 215,116 = 96.42% | 59,434,269 / 60,053,202 = 98.97% |
| Parliament 15, stored after the backfill | 62,050 / 62,292 = 99.61% | 62,050 / 63,909 = 97.09% | 17,789,377 / 17,926,064 = 99.24% |

The newer-system load has 5 unlinked "Mdm Speaker" misprints for "Mdm Deputy Speaker" (counted on 14 October 2026). [ADR 0002](adr/0002-role-holder-attribution.md) defines the role-holder rules. Whole-table source-gap counts are under "Next work and other gaps".

Only 2 attendance rows remain unlinked: A.V. Winslow's, because he has no `Speaker` row (counted on 2 November 2026). A hand alias links the Andrew Fong row to Fong Sip Chee. The Parliament 15 backfill log counts 4,106 new attendance rows, all linked.

The load's decisions, run order, judgement calls, and evidence are in [post-2012-load.md](report/post-2012-load.md).

### Verdict against the done tests, whole corpus

The done tests cover every record up to 15 April 2025, the end of Parliament 14, and include the hansard app, because a researcher must be able to reach the record. Parliament 15 falls after that cutoff; test 4 covers it through the link check counted on 19 October 2026, and test 2 through round 6 counted on 20 October 2026. Before launch, write #8 re-parsed every report with text with the current parser, except the 126 it held, and write #9 released 60 of those 126. The done tests come from the [third independent audit](report/north-star-audit-2026-10-17.md), after write #7 and the 750 sitting-level Deputy Speaker links, and the maintainers agreed them.

| Test | Verdict |
|---|---|
| 1. Coverage: every SPRS hit to the cutoff stored, textless records named | Pass for every hit SPRS returns, after the coverage refill; 6 hits the search engine counts are never returned, so they cannot be fetched. A crawl of SPRS finds 41,839 hits. The 18 textless reports other than `atbp` are source failures, named in Appendix A of the [data loss register](data-loss-register.md). [Crawl evidence](report/north-star-audit-2026-10-17.md#o1-the-crawl); [remaining gaps](coverage-gaps.md). |
| 2. Speaker index: stopping rule holds, Parliaments 0 to 11 and 12 to 14 separately | Pass after write #9. One-sided 95% upper bounds by characters for Tier A and B are 0.095% and 0.984% in Parliaments 0 to 11, and 0.003% and 0.045% in Parliaments 12 to 14, below the 1% and 2% gates. The detectors read below source typo rates when they last ran, on 18 October 2026, before write #8 and write #9. Parliament 15 has both bounds at 0.000% and no pipeline detector hit. [Round 5](report/speech-fidelity-loop.md#round-5), [post-write re-read](report/speech-fidelity-loop.md#round-5-reads-that-write-9-made-stale), and [round 6](report/speech-fidelity-loop.md#round-6-parliament-15-20-october). |
| 3. Sitting metadata: attendance everywhere, every newer-format list filled | Pass. The older format provides no sections, annexures, vernaculars or a2b list, so those are not gaps. |
| 4. Linking: Wilson lower bound of 95% on a fresh hand check | Pass after write #11: 999 of 1,000 credited rows right (99.9%, Wilson 99.44% to 99.98%). The missed paper-handed-in record is fixed by `51ef90d`, which write #13 stored. Write #10's figures are in [`docs/figures/2026-11-02-write10.txt`](figures/2026-11-02-write10.txt), with an entry in [figures-history.md](report/figures-history.md). [Second hand check](report/hand-check-2-2026-11-02.md#result); [first hand check](report/hand-check-2026-11-02.md). |
| 5. Markdown: stopping rule holds, reports losing over 5% of tokens fixed or listed | Pass with round 5 (test 2). All 19 reports losing over 5% of tokens are listed with their loss in [Appendix B of the data loss register](data-loss-register.md#b-reports-that-lose-more-than-5-of-their-html-word-tokens-19). The parser defect in 22103 (97.7% loss from a stray `<` before a heading) is fixed by `fee2dc3`; write #8 stored its markdown and 32 speech rows. |
| 6. Tracking: per report type figures after every write, kept in the repo | Pass. `scripts/attribution_text_share.py` prints the three numbers, the zero-row count and the single-speaker collapse share per report type within each Parliament group, `CLAUDE.md` makes every write end with a run, and the output is kept in `docs/figures/`, starting with `2026-10-17-round8.txt`. |
| 7. Stored rows equal a fresh parse, or the exception is listed with its reason | Pass, with a listed residue: 19 held reports after write #12 and 124 textless reports (114 with NULL content, 10 with an empty string). After write #9 every other report equalled the parser at `45b0a8a`. Write #11 and write #12 rebuilt the reports they released with the parser at `49617da`, and write #13 rebuilt 116 reports with the parser at `51ef90d` and released none. The pass does not say the held reports are fine: each still waits on a parser fix or a ruling. The [third audit](report/north-star-audit-2026-10-17.md#stored-rows-against-a-fresh-parse) made the first comparison; the exceptions and unexplained differences are below. |
| 8. Strategies section true of the code | Pass (`97ef7ff`, `2d7189f`). |
| 9. App served publicly over the whole corpus | Pass on being public. The site and API run as one container at hansard.fancybinary.sg, and on 23 October 2026 the home page and `/api/coverage` answered without a login. Serving every report is unchecked; takedowns answer 410 by design. [App audit](report/north-star-audit-2026-10-17.md#app). |
| 10. Freshness: 14 unattended successful runs in a row, and one deliberate failure that alerts | Not met. The reader's dates stay true only while the daily refresh keeps running, and this test measures that. The alert half passes: on 30 October 2026 a deliberate failure sent both the Telegram alert and the healthchecks.io failure ping. The run count, taken from `refresh_run` on production on 2 November 2026, is 11 of 14: the 11 latest rows, one a day from 23 October to 2 November, all `SUCCEEDED`, each started within 37 seconds of 04:00 SGT (`0 20 * * *` UTC). 3 more scheduled successes in a row would meet it. [Refresh and alerts](refresh.md). |

### Freshness check

Count the 14 latest `refresh_run` rows by `started_at`: all must be `SUCCEEDED` and start unattended on the 04:00 Singapore schedule (`0 20 * * *` UTC). For the alert half, break one run on purpose (a wrong `DATABASE_URL` on the refresh job is enough) and check that the Telegram alert and healthchecks.io `/fail` ping both arrive. [refresh.md](refresh.md) describes the alerts and exit-code ping.

### App behavior

Search uses a rum index, which cleared most of the search failure, and a second rum index on the sitting date of each speech row, which cleared the rest ([ADR 0010](adr/0010-speech-sitting-date-set-by-each-writer.md)). On production, relevance takes 0.12 to 6.28 s in every shape tested. With the API at hansard `b5608fb`, every date-order shape measured on production takes under 1 s: oldest first "government" 0.43 s and "housing" 0.22 s, newest first "government" 0.47 s, and a Parliament or one-year filter 0.05 to 0.10 s.

A member's party changes inside a Membership (one `Speaker` row per person per Parliament) are stored in `partyaffiliation` and shown as numbered notes beside the party: 39 Memberships and 92 dated spans, each with a source (hansard `0cfea3f`, `83c8946`, `bb46fb8`). The app change is in hansard (`bb46fb8`, adjusted by `fd26361`), and the methods page describes the notes as shipped. Their display on production is unchecked.

### The residue behind test 7

After write #12, the following 19 reports keep their stored rows. A report leaves the list only through a write that rebuilds it, and joins only through a ruling recorded here.

| Reason | Reports | Count |
|---|---|---|
| A parser fix, which the held-report review names with a fixture. 23268: a footnote run swallows the speech after it. 24685: an italic heading after a stripped `****` is dropped. 26696: the parse drops three bare language-note lines. 31083: italic headings in the preamble of a Budget speech with no label (its rows are also in [data/unlabelled_speech.json](../data/unlabelled_speech.json)). 32676: a time printed on its own line after "at" ends the sentence, and the parse drops it. 37959: unbolded bare-name labels. 38102: the header block of a written answer with no label. 38225: a bold fragment inside a paragraph, which the stored rows keep only as a label. 40150: a quoted newspaper headline that a member reads out is taken as a heading. 41944: a chamber event would be credited to Mr Speaker | 23268, 24685, 26696, 31083, 32676, 37959, 38102, 38225, 40150, 41944 | 10 |
| Held on purpose: a person edited the rows by hand, and the rows stay held ("Held on purpose" in the [data loss register](data-loss-register.md)) | 22647, 22650 | 2 |
| Held under rule D1 at write #12: the parse is better, but old shared links into the report would open another member's words. 8732 has 4 such links, 31722 5, 18272 2, and the others 1 each. 8732 and 18272 are also in [data/unlabelled_speech.json](../data/unlabelled_speech.json) | 8732, 18272, 22063, 31718, 31722, 39945, 41149 | 7 |

Separately, a read of 3,497 reports with a row starting with `_` found 206 rows in 90 non-held reports that differ in another way, and 8 non-held reports whose parse has another row count. In 84 of the 90, the stored row credits a "Resolved, That ..." motion to its mover, often the Leader of the House, while the parse gives no speaker. In 5 reports, 118 rows have no stored speaker where the parse gives one. These differences remain unexplained and unchanged.

All 19 differ from a fresh parse. The 7 D1 holds can follow if the maintainers accept link drift, because no tool preserves those links. The held file of write #12, `plans/held-release/held_option_b.json`, gives the reason for each.

Once test 10 passes, the scraper is in upkeep, with the standing aim to credit every word uttered in parliament to the person who said it, even procedural speeches. It runs the daily refresh, fixes errors readers report, and fixes every kind of serious (Tier A) error a hand check finds, however few rows it touches. Accuracy work has no end point. A hand check runs once a quarter, and after any write that changes more than 1% of credited rows (hansard `docs/adr/0009-ai-readers-person-judges-flags.md`).

### Where more work stops paying

Published peers report less than this project. The Knesset corpus reports 94.5% of speaker strings matched to its member database, and 98.3% speaker-name correctness on a hand-checked test set; a 2026 paper linking the UK Hansard corpus to MPs reports 89.3% for the Commons; ParlaMint, the Australian Hansard datasets, and TheyWorkForYou publish no linking rate. None found resolves an unnamed presiding officer to a person: ParlaMint tags the role, the Knesset corpus flags the chair, and Spain's ParlaMint corpus leaves them blank. So work on unnamed chairs, or resolver tuning that moves the rate by tenths of a point, is past the point of value. Work that moves text share, coverage, or measured precision is not. What peer projects do that this one does not is in [peer-projects.md](peer-projects.md).

The stopping rule requires a count for every remaining class. This census uses master `2b74a2b`, with three fixes included; rows mark later counts. The [round log](report/speech-fidelity-loop.md) holds the detail.

| Class | Rows | Reports | Countable characters | Harm |
|---|---|---|---|---|
| Italic title stored as a SPEECH row (60 of 60 read were headings) | 9,782 | 1,094 | 293,008 | Tier C |
| Of those, an italic title that closes a member's run and is credited to the previous member | 2,281 | 157 | 49,933 | Tier C |
| Bare time stamp credited to a speaker | 51 | 51 | 427 | Tier C |
| "#### [... in the Chair]" credited to a speaker | 0 | 0 | 0 | None left |
| `<pre>` table stored one row per line (about 15,500 of the rows are real tables) | 18,591 | 863 | 388,269 | Tier C |
| Prose cut across rows inside `<pre>`, a lower bound (542 cuts) | 1,021 | 162 | 37,103 | Tier B |
| Footnote digit glued to a word or number (`2f5cc5d`, `53eac45`); only 2 and 3 count as exponents, never after an apostrophe. Remaining stored rows counted on 26 October 2026 after `scripts/apply_footnote_markers.py` | 5 | 1 (23268, held) | not counted | Tier B |
| Labels that are not people: headings 52 rows in 7 reports, a table caption and cell in 22806 (8), a report title in 32642 (5), junk such as a bold "Question" or "To ask" (48) | 113 | 15 | 9,081 | Tier A where the text is a member's or the chair's (about 7,000 characters), otherwise Tier C |
| Member speech swallowed by a footnote run (23268, held) | 6 | 1 | 1,297 | Tier A |
| Caption text after a bold "Table N:" (23627, 43250), kept as HEADING rows with their text in both fresh parse and stored rows | 0 | 0 | 0 | None left |
| Caption-only bold lines, no row by design under WS3 | 42 lines | 28 | 475 words | Tier C |
| A column marker that leaves a `****` line, so a paragraph stays cut across it: 405 cuts, about 300 to 355 of them real (15 of 20 sampled); 684 rows, 259 reports and 678,438 characters without the 50 cuts after a link-title line; older system only; a lower bound | 770 | 293 | 694,905 | Tier B |
| Reports with markdown and no rows: 22 hold prose a person said or wrote (94,547 characters; 14 ministers' addenda to the President's Address with no label, 8 other addenda, 33574 alone 27,467), 16 hold procedural records or first readings (2,500), 664 are appendix stubs, assent lists, adjournment records, and order-read stubs | 0 | 702 | 220,800 (208,633 in Parliaments 0 to 11) | Lost text for the 22; the rest are stubs and records |
| Near-miss procedural lines left by fix 2: "The amendment(s) read(s) as follows:" with no marker (9), "Original Question put, and agreed to." (6), "Resolved." (5), "Bill accordingly read the Third time." (2), "+The following amendments stood ..." (2), five single rows. The parser gives the bare amendments note, "Original Question put, "That ..."", the plus-marked amendments note and "Bill accordingly committed" no speaker (`6560581`), and rules cover the other three, so the stored rows change at the next re-parse. A fresh parse still credits 15 lines in 13 reports: "Questions proposed." (31342), "Resolution, reported" (36434), "stood in the, name of" (33081), "Amendment(s) made:" (35601, 37255, 37912, 39657, 39659 twice), "Clause .2, as amended" (35601), "Clause 8 ... stand stand part" (37678), "Original Question, as amended, again proposed." (38530), "Main Question, as amended, (again) proposed." (41721, 41792) and "The following amendments stood on the Order" (29577). The 38 amendment lines listed after the 9 bare notes keep the member's speaker, because the note keeps the turn | 29 until a re-parse | up to 27 | 1,051 | Tier A, procedural line credited |
| First-reading leftovers: OCR-typo formulas (33648, 35994, 38770, 39997), 25885, 22343's split tail, trailing headings and time stamps in 6 reports, "theSenior" or "theSecond" glue in 13945, 13946 and 13953 | at least 12 | 15 | not counted | Tier A for 6 reports, Tier C for 6, Tier B for 3 |
| "The voting was as follows:-" (5 rows) and "Division Bells rung." (4 rows) credited to the chair. The parser gives the voting line no speaker (`4ab3497`), and a fresh parse already gives "Division Bells rung." none (37957), so the stored rows change at the next re-parse | 9 until a re-parse | not counted | not counted | Tier A until a re-parse |
| Footnote continuation lines (21601) | not counted | 1 | not counted | Tier A |
| A quoted motion after "Question proposed," credited to the previous member (40585, row 721650) | at least 1 | 1 | not counted | Tier A, scored by both round 5 readers |
| Double-marker notes (22949, 43048) and "(1)IATA" notes with no space (21163) | 4 | 3 | not counted | Tier A |
| Resumed Budget speech with no speaker in 22691, after the rebuild | not counted | 1 | 18,706 | Listed, not scored |
| Reports held after write #12, 7 under rule D1 | kind NULL on 2,275 | 19 | not counted | Stored rows from an older parser |
| Latent: a label title the parser did not know cut "Miss Penny Low (Pasir Ris-Punggol" at a bracket (24708). The parser counts Miss, Madam, Che, LG and COL as label titles (`31d727a`), and a fresh parse of 24708 keeps "Miss Penny Low (Pasir Ris-Punggol)" whole | 0 | 0 | 0 | None until a bold-only line with no colon appears. 6,828 "Miss" and "Madam" rows (2,461,263 characters) depend on the colon |
| Group labels ("An hon. Member" and 16 spellings) and real people whose label lacks an honorific the regexes know | 2,241 and 7,533 | 922 and 1,391 | 70,238 and 2,815,754 | Not errors; the ADR 0001 rate already excludes the "hon. Member(s)" forms |
| Markup residue: `**` in 50 rows and `__` in 247 rows (the write #4 replica, `hansard_replica`, recounted on 16 October 2026; the strip rule `1fc23a3` is written) | 50 and 247 | 22 and 164 | not counted | Tier C |
| Rows of kind UNCLASSIFIED, many of them PROCEDURAL, DOCUMENT_TEXT or HEADING in fact; readers flagged 199 of 9,043 round 3 and round 4 rows, and 59 of 8,773 round 5 rows (titles stored as DOCUMENT_TEXT, oath rolls and "Group N" captions as UNCLASSIFIED) | 20,944 | not counted | not counted | None; kind gates nothing |
| Text dropped inside reports that have rows: headings, time stamps, chair annotations, and question numbers | not counted | not counted | 0.19% of body text | Tier C (decision review, finding 7, open) |



## Strategies

### Raw first, derive second

Raw response tables store every external API response before transformation. Entity tables (`Report`, `Sitting`) keep every raw field; changed values are listed in [data-loss-register.md](data-loss-register.md): cleaned titles, sitting and session numbers filled from the header table, and empty strings stored as NULL. The source of truth is always recoverable. A stage skips rows that already exist, and dropping speech rows would lose their ids and links, so stored reports are rebuilt through planned, rehearsed writes.

### Staged, incremental population

`CLAUDE.md` lists the pipeline stages. `script.py` runs stages 5 to 9, the sitting, attendance, linking, and person stages. Stages 1 to 4 (search, report fetch, reports, and speeches) have no entry point there and run from the fill and rebuild tools. Each stage skips what is already stored, so a run resumes after an interruption. A rerun therefore never applies parser changes to stored rows.

### One request at a time, with backoff on 429

The gateway sends one request at a time, at least 2 seconds apart including retries, with a user agent naming the project. HTTP 429 triggers exponential backoff with jitter.

### Iterative parsing refinement

Parsing improvements follow a structured loop: inspect failure categories, apply a targeted fix, add a golden fixture, measure the attribution figures before and after, and commit to master. The speech fidelity loop ([speech-fidelity-loop.md](report/speech-fidelity-loop.md)) adds hand reads against the source and a stopping rule.

### Format-aware artifact removal

Raw HTML comes from two systems: sprs2 (sittings before 10 September 2012) and sprs3 (from that date). `utils/markdown_parser.py` and `services/speech.py` branch on `report_version` (the source-system version) where the two differ. Most cleaning steps, such as turning `&nbsp;` into a space and merging bold lines split across page breaks, run on every report. A step that applies to one system only is guarded by `report_version`, so the other system's output does not change.

### Principled attribution hierarchy

Bold speaker labels come first. For a report with none, attribution follows three fallback steps in `services/speech.py`:

1. If the `MPs Speaking` header lists exactly one name, the body goes to that speaker as one row.
2. Otherwise the report type decides: the speaker line of an `atbp` (Assent to Bills Passed) report, the minister of a President's Address addendum (or the President when no ministry heading appears), the mover of an adjournment motion, and the presenter of a bill or, in the newer system, a bill introduction.
3. If neither applies, the report stays unattributed. Multi-speaker appendix documents and authorless procedural orders get no invented speaker.

Nobody speaks an `atbp` notice of assent, but the Speaker writes and signs it, so its words are his, and it stands in for an announcement he would otherwise make in the House. The credit stays even when an accuracy sample counts it as an error.

### Diagnostic tooling as a first-class concern

Nothing exports statistics automatically. `scripts/attribution_text_share.py` prints the attribution figures by Parliament group and by report type when it is run, with the zero-row reports and single-speaker collapses, and `--output` keeps a copy in a file. `CLAUDE.md` asks for it before and after every parsing or linking change. The diagnostic scripts audit one failure category at a time without rerunning the full pipeline.

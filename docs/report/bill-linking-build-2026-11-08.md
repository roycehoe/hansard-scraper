# Bill linking build, 8 November 2026

What was built from the rulings on [bill-linking-rules-2026-11-08.md](bill-linking-rules-2026-11-08.md), what the two research fetches found, and the commands that put it on production. The build host had no database, so nothing here is written to production or the replica yet; every count below comes from the research rebuild, the test suite or the fetched files.

## What is on master

| Ruling | Built | Where |
|---|---|---|
| 1. Bills Supplement as a raw table, bill numbers by R1 | `billssupplementcapture` (11 Archive captures as received) and `billssupplemententry` (2,394 rows); `bill.bill_number` and `bill_number_source`; the 16 loose and similar links go to the review list | `scripts/apply_bills_supplement.py`, `services/bill.py`, migration `c4d8e2a1b7f3` and `d7e1f3a9c2b5` |
| 2. R3 split bills and R2 number check | Merges behind the bill-number conflict check; R2 kept in the plan and the dry-run log, never the stored link; the 9 reproduced hand-kept cases are golden tests in `tests/test_bill_number_rules.py` | `services/bill.py`, `services/act_link.py`, `populate/act_links.py` |
| 3. eGazette 2024 to 2026 | 177 PDFs on disk, one `egazettesupplement` row per PDF with the printed fields, R6 links from an Acts Supplement to its bill | `scripts/fetch_egazette_supplements.py`, `scripts/apply_egazette_supplements.py`, migration `e8a2b4c6d1f9` |
| 4. Repealed Acts in the Archive | Counted, not fetched in bulk (the PDF path); the listing itself is now stored and linked, see the repealed Act link below | `plans/bill-linking-build/repealed-acts-count.md` |
| Repealed Act link (Royce's direction of the night of 8 November) | `repealedactscapture` (2 Archive captures of the SSO Repealed Acts listing as received) and `repealedactentry` (286 Acts); `bill.repealed_act_url` and `repealed_act_url_source`; one review-list kind; test 3 counts the link and prints it apart | `scripts/apply_repealed_acts.py`, `services/repealed_acts.py`, `services/bill.py`, `populate/act_links.py`, migrations `b7c2d9e4f1a3` and `c8d3e1f6a2b9` |
| Budget debates attached to the Supply Bill (Royce's direction of the night of 8 November) | `billreport.role` (READING or BUDGET_DEBATE); every `budget` report in exactly one Supply Bill's debate window becomes a BUDGET_DEBATE row of that bill; two review-list kinds; a budget debates line in the review summary | `services/bill.py`, `services/act_link_write.py`, `populate/act_links.py`, migration `d9e4f2a7b3c1` |
| 5. Supply and repeal classes, R8 list | `bill.bill_class`; `scripts/list_bill_review_items.py` with done tests 1 to 4 by era | `services/bill.py`, `scripts/list_bill_review_items.py` |
| Acts Supplement link (evening ruling 1 of [bill-link-gap-2026-11-08.md](bill-link-gap-2026-11-08.md)) | `actssupplementcapture` (65 Archive captures as received) and `actssupplemententry` (1,487 rows); `bill.act_number` and `act_number_source`; two review-list kinds for the matches the rule refuses; test 3 also over the bills of no class | `scripts/apply_acts_supplement.py`, `services/acts_supplement.py`, `services/bill.py`, `populate/act_links.py`, migrations `f3a7c9e1b2d4` and `a9d4e7f2c1b8` |

One rule changed in review. The report's R3 refuses a merge when "R1 gives the two different bill numbers", and the first code read the tail's first report as its first reading, which from 1967 on falls outside every listing window, so the check never fired. The check now looks for a Supplement entry of the tail's title published between the head's last report and the tail's first, and refuses when it carries another number. The Housing and Development pair of 1962 and 1963 is still refused, and a "Roads (Amendment No. 2)" tail read 44 days after its own entry now stays apart from a "Roads (Amendment)" head. Entries with a misprinted publication date (R4) also give no number now, because their window is a year off.

## Acts Supplement link, measured on the shipped code

Built on the evening of 8 November from section 4 of [bill-link-gap-2026-11-08.md](bill-link-gap-2026-11-08.md). A passed bill takes the Act number of the Acts Supplement entries whose title key equals its own and whose publication date falls from one day before to 120 days after its last report, only when exactly one distinct Act number matches. The link is stored on the bill (`bill.act_number`, `bill.act_number_source` ACTS_SUPPLEMENT_LISTING), a separate claim from `acthistoryentry.bill_id`. It says the bill became an Act that was published, whose text the project does not hold; it says nothing about whether the Act is in force.

The inputs are the 65 Internet Archive captures the research fetched (one per year URL, 1961 to 2025; 2026 has no capture), copied to `plans/bill-linking-build/acts-supplement-captures/` with a manifest in the repo's shape. Nothing was fetched again. The measurement ran the shipped parser, services and rule over those captures and the research rebuild of the bills (`plans/bill-link-gap/data/bills.jsonl`, 2,682 passed bills, which matched production's count) and the 500 harvested Legislative History entries; the script is `plans/bill-linking-build/tools/measure_acts_supplement_link.py` and its output `plans/bill-linking-build/acts-supplement-measurement.txt`. Every figure is **rebuilt**: the shipped code on the research rebuild, not a database.

| Measurement | Research report | Shipped code |
|---|---|---|
| Distinct listing rows (12,486 rows across the captures) | 1,487 | 1,487, 1,486 Act numbers (53/2018 has two links) |
| Precision against the Act number a linked entry prints | 250 agree, 0 disagree | 250 agree, 0 disagree, 11 pairs the rule leaves unmatched |
| Pre-cutoff passed bills reached | 1,372 of 2,617 | 1,372 of 2,617 (0 of 319, 728 of 1,591, 644 of 707 by era) |
| Supply and repeal bills reached | 88 of 152, 8 of 21 | 88 of 152, 8 of 21 |
| Bills refused for two Act numbers in the window | 1 | 1, the Supplementary Supply (FY 2002) Bill (42/2002 and 3/2003) |
| Act numbers claimed by two bills | not measured | 0 |
| Passed after the cutoff and reached | not measured | 20 of 65 |

The gain estimate's inputs reproduce too: 96 supply and repeal bills reached, which is the firm floor because none of the 173 links today; 1,276 of the other 2,444 pre-cutoff passed bills reached; on the partial 30-Act harvest, bills with no current Act of their loose title key are reached at 62.7% (37 of 59) where already linked and 28.7% (193 of 673) where not (the report said 31.7%, measured over a slightly different set). The 190 to 280 range stands as an estimate until the full harvest runs; the production dry run of `apply_act_links.py` prints the exact count.

Known-bad runs. With every publication date moved 60 days later, reach falls to 1,262 of 2,617 and 15 of the 250 pairs drop to "no match", but no pair disagrees, because a wrong date cannot make a same-title Act of another year fall inside a 121-day window. With dates moved 365 days, 28 pairs disagree and 0 agree, so the precision check does fail on a bad input. The review list's refusal class is checked by the FY 2002 case above.

The review list gains two kinds. `ACTS_SUPPLEMENT_BILL_WITH_TWO_ACT_NUMBERS` (1 case) names the bill and the numbers. `ACTS_SUPPLEMENT_ENTRY_UNPLACED` (94 Act numbers in the rebuild, 87 of them with a passed bill of the same title somewhere) names the Act number, its publication date and the nearest passed bill of the title with the gap in days. The 509 pre-1985 passed bills whose title is listed only for later years are not items: the listing starts in 1985 and they can never match.

An Opus review of the rule against the report found no defect that would store a wrong number or count and no change to the bill numbers, classes, merges or Act history links. It noted two rule choices, which are questions 5 and 6 below.

Test 3 in `scripts/list_bill_review_items.py` reads the stored `bill.act_number`, so its counts move only after the production write of `apply_act_links.py`. The two review kinds come from the rebuilt grouping and the stored entries, so they appear as soon as `apply_acts_supplement.py` has run.

## eGazette fetch

Run on 8 November 2026 from this host, one request at a time, 3 s apart, with the project's user agent, through `gateway/egazette.py`.

| Host | Requests | 200 | 403 |
|---|---|---|---|
| assets.egazette.gov.sg | 197 (195 in the run, 2 HEAD probes) | 177 | 18 |
| web.archive.org | 23 (the repealed-Acts count) | 19 | 0, plus 1 × 503 and 2 × 504 and 1 empty write |
| sso.agc.gov.sg | 0 | | |

A 403 is S3's `AccessDenied` for a missing key, and each year's series stopped after three in a row. The files:

| Year | Bills Supplement | Acts Supplement |
|---|---|---|
| 2024 | 50 (01 to 50) | 46 |
| 2025 | 22 | 26 |
| 2026 | 14 | 19 |

All 177 parse. 23 Acts Supplements print no Act number. Six eGazette bill numbers have no Bills Supplement listing entry (36/2024, 37/2024, 38/2024, 12/2025, 17/2025, 14/2026), so the eGazette fills them. The PDFs sit in `plans/bill-linking-build/egazette/<year>/<bills|acts>/NN.pdf` (88 MiB, gitignored) with `fetches.json`.

The eGazette terms of use (updated 10 July 2026) permit automated extraction under clause 11 when it is not abusive, intrusive or deceptive and does not disrupt the site, and require attribution. Wherever the project reproduces the PDFs' content, the hansard site included, it shows these lines, which Royce should check against the terms page before they go live:

> The e-Gazettes are the copyright of the Government of Singapore and are reproduced with permission. Users may check www.egazette.gov.sg for the latest e-Gazettes. This project is responsible for the accuracy of what it reproduces, and is not affiliated with the Government of Singapore.

The permission can be revoked at any time, so the rows hold only the fields R6 needs and the files stay outside the repository and the database.

## Repealed Acts in the Archive (ruling 4)

Full notes in `plans/bill-linking-build/repealed-acts-count.md`. The PDF path (an Act's last in-force version, which alone carries a Legislative History) would link about 15 to 35 bills, because the Archive holds such PDFs for a few Acts repealed about 2015 or later. That fetch waits for Royce. The listing path below replaces it for the link Royce asked for.

## Repealed Act link, measured on the shipped code

Royce's direction on the night of 8 November: "If the law no longer exists, on AGC's website, there would be an indication that the law has been repealed. It should link to that." Built as the Acts Supplement listing was built. `repealedactscapture` holds the Internet Archive captures of `https://sso.agc.gov.sg/Browse/Act/Repealed/All?PageSize=500` as received, and `repealedactentry` one row per Act (`sso_code` unique, the first capture that lists it wins): the printed title with its `(Repealed)`, `(Spent)`, `(Expired)` or `(Omitted)` status, the chapter where the capture prints one, the link, and from the link the repeal date (`/Repealed/YYYYMMDD`), the last version date (`DocDate`) and the enactment year (the code's trailing four digits). The exact-URL CDX query showed two captures of the 500-row page, 20 October 2020 (227 rows) and 16 July 2024 (284 rows); the 2022 file the research saved is a 20-row page. Both parse to 511 rows and 286 Acts, one with no year (`CAAUNKNOWN`). 87 of the 2024 rows are Supply, Supplementary Supply and Final Supply Acts of 1985 to 2023, listed as Spent.

The stub sample: 30 Act pages, stratified by status and code decade, fetched from the Archive (`plans/bill-linking-build/repealed-acts-stub-sample.json`, pages under `fetched/stub-<code>/body`). In 30 of 30 the link's repeal date equals the page's "Status: Repealed/Spent on" date. In 22 of 22 pages that print an "Original Enactment" line, the code's year equals it; the other 8 pages carry the year in the Act's own title. No request went to sso.agc.gov.sg. Archive requests: 32, 8 s apart through the shared lock; openhansard.sg requests: 43, 2 s apart; all in `plans/bill-linking-build/repealed-acts-requests.log`.

The rule (`services/bill.py`): a passed bill links to the one repealed Act whose loose title key (status words, then the title year and the amendment and number words, removed) equals the bill's and whose dates fit. An amendment bill (its own title key holds "amendment") fits an Act enacted in or before its first report's year and repealed on or after its last report, so the link says the Act it amended has since gone. Any other bill fits an Act enacted in its first or last report's year, so a bill that became a new Act never links to the Act it replaced: the first draft, the life bracket for every bill, linked the Copyright Bill 1986 to the Copyright Act 1914 and disagreed with 45 of 88 labelled pairs. Exactly one distinct SSO code, else no link and a review item. Stored as `bill.repealed_act_url` (the SSO page) and `repealed_act_url_source` REPEALED_ACTS_LISTING, apart from the Act history link and the Act number. It says only that the bill's title matches an Act SSO lists as repealed, spent, expired or omitted and that the bill's dates fit that Act's enactment year and life.

Measured with `plans/bill-linking-build/tools/measure_repealed_act_link.py` (output `measure-repealed-act-link.txt`): the shipped parser, services and rule over the two captures and the research rebuild of the bills (`plans/bill-link-gap/data/bills.jsonl`), with the Acts Supplement pairs (`acts-supp-matches.jsonl`) and the 72-bill sample as the labelled sets. A principal bill's link is right when the Act number it took has the year of the Act's code. Every figure is rebuilt, not read from a database.

| Measurement | Shipped code |
|---|---|
| Passed bills linked | 442 (52 in 1955 to 1960, 333 in 1961 to 2005, 57 from 2006); 193 principal, 249 amendment; 77 supply bills |
| Precision, principal bills with an Acts Supplement number | 106 agree, 0 disagree |
| Precision, 72-bill sample | 15 sampled bills link (6 principal, 10 amendment; one 1956 record matches two bills); the 5 principal ones with an Act number agree with it, and every link lands on the Act the sample's own current-law notes name as repealed, spent or folded into a later Act (`PFA1958`, `CPCR1955`, `MA1959` among them) |
| Reach: pre-cutoff passed bills of no class with no Act history link | 359 of 2,161 (52 of 290, 289 of 1,349, 18 of 522 by era) |
| Of those, bills no Acts Supplement number reaches either | 249 (52, 195, 2) |
| Refused for two Acts of the title | 9: 8 Supplementary Supply Bills of 1994 to 2001, where SSO lists a Supplementary Supply Act and a Supplementary Supply (No. 2) Act of the year under one loose key, and the Supply Bill 2008, listed under two codes (`SA2008`, `7-2008`) |

SSO lists only Acts repealed from 1985, so a bill whose Act went before 1985 can never link: 1,802 of the 2,161 unresolved bills above stay unreached, most of them for that reason (the 1961 to 2005 era alone has 1,060 left). Known-bad runs: with every enactment year moved one later, 54 principal bills still link and all 54 disagree with their Act number (0 agree), so the precision check fails on a bad year; with every repeal date moved 15 years earlier, the amendment links fall from 249 to 169 and the principal links and pairs do not move, because the repeal date bears only on amendment bills.

Test 3 in `scripts/list_bill_review_items.py` counts a bill with a stored repealed Act link as resolved and prints the count beside it ("N passed bills link to a repealed Act's page, N of them resolved by that link alone"). The review kind `REPEALED_ACT_BILL_WITH_TWO_ACTS` names the bill and the codes.

## Budget debates attached to the Supply Bill, measured on the shipped code

Royce's direction on the night of 8 November: "Yearly budget bills is understandable, although if there is a debate about a particular bill during the parliament's term, the hansard record should link to that." The `budget` reports are that debate: the Budget Statement, the Committee of Supply heads ("BUDGET, MINISTRY OF ..."), the Estimates and Supplementary Estimates. No budget report title ends in "Bill", so none is grouped as a reading. The rule attaches each to the year's Supply Bill as a `billreport` row with the role BUDGET_DEBATE, beside the READING rows, so a reader can tell a head's debate from a reading. The bill's identity (its reading report ids) does not change, and no speech row changes.

The rule (`services/bill.py`): the candidates are the bills of class SUPPLY. A bill is a main Supply Bill when its title key is a Supply or Appropriation Bill with at most a number or financial year (`supplybill`, `supplyfy2002bill`, `appropriationbill`), otherwise it is a Supplementary, Final or Excess Supply Bill. A report whose title holds the word supplementary, excess or final goes to the second group, any other report to the first, and it attaches when exactly one bill of that group has the report's date inside its debate window, from 45 days before the bill's first report to 30 days after its last. Two bills or none give no row and a review item: `BUDGET_REPORT_WITH_TWO_SUPPLY_BILLS`, or `BUDGET_REPORT_WITHOUT_SUPPLY_BILL` when a supply-class bill has a report within 120 days.

The inputs: the 2,998 `budget` reports listed by openhansard.sg's public API (`/api/search/reports?report_type=budget`, by decade, 100 a page, 43 requests 2 s apart; `plans/bill-linking-build/budget-reports/reports.jsonl`) and the research rebuild's 163 supply-class bills, 74 of them main bills. The harness is `plans/bill-linking-build/tools/measure_budget_report_links.py`, its output `measure-budget-report-links.txt`. Every figure is rebuilt. A strict bracket (the bill's own first and last dates) attaches 2,541; the 45 and 30 day margins add the Budget Statement debated before the bill's first reading and the heads debated after its last report.

| Measurement | Shipped code |
|---|---|
| Budget reports attached | 2,936 of 2,998: 421 of 460 in 1955 to 1960, 1,638 of 1,659 in 1961 to 2005, 877 of 879 from 2006 |
| Two bills in the window | 9, every one a supplementary estimates report beside a Supplementary Supply Bill and a Supplementary Supply (No. 2) or Final Supply Bill debated the same weeks (1964, 1966, 1968, 1970, 2020) |
| No bill in the window | 53, of which 46 have a supply-class bill within 120 days; 35 are "SUPPLEMENTARY PROVISION" reports of 1955 to 1960, read as resolutions on a supplementary provision, not bills |
| 72-bill sample | The 1987, 1989 and 1995 Supply Bills take 28, 28 and 29 budget reports, every one inside the bill's own dates and none with a supplementary title; the 1980 Supplementary Supply (No. 2) Bill takes its one "First Supplementary Estimates" report |

Known-bad run: with every report date moved one year later, 2,522 reports still attach and every one lands on a Supply Bill of the year after the report's own, so the rule has no year check of its own and the window alone places a report; the check that catches it is the bill's first report year against the report's year, which the review of the dry run should read once. 476 fewer attach, because the shifted dates fall between the bills.

## The full R2 measurement

The 523-Act harvest is not on this host, so R2 ran only on fixtures here. The dry run of `apply_act_links.py` on the machine with the harvest prints the whole measurement over the 9,905 entries in one line:

```
Act and Ordinance entries by bill number rule outcome: number and title rules agree N, number and title rules disagree N, title rule only N, number rule only N, neither rule N, no bill number printed N
```

Quote it in the figures file. "Disagree" should be 0 or each case read before the commit; "number rule only" entries appear on the review list as `HISTORY_LINK_BY_NUMBER_ONLY`.

## Runbook

Run on a machine with `.env`, from a clean worktree of committed master, after `git pull`. Nothing here touches the speech table, so `attribution_text_share.py` and the shared-link check are not needed; if any step reports a speech count change, stop. The gitignored inputs are on the build host under `plans/bill-linking-build/` and must be copied first: `bills-supplement-captures/` (4.1 MB), `acts-supplement-captures/` (24 MB, 65 HTML files and `captures.json`), `repealed-acts-captures/` (540 KB, 2 HTML files and `captures.json`) and `egazette/` (88 MiB). `<harvest>` is the 523-Act harvest directory used for the 5 November write. `apply_act_links.py --harvest-directory` needs one `pdftotext -layout` text file per Act beside `acts.json`. This build host has no `pdftotext`, so a harvest fetched here (the one being fetched into `plans/bill-link-gap/` is PDFs under `pdfs/` plus a pypdf extraction under `harvest/text/`, not `pdftotext` text) must be converted on a machine that has it, or after `apt install poppler-utils` here, before that directory is given to the script.

```bash
cd ~/ghq/github.com/roycehoe/hansard-scraper && git pull
git worktree add ../hansard-write master && ln -s "$PWD/.env" ../hansard-write/.env
cd ../hansard-write && export PYTHONPATH="$PWD" && BUILD=~/ghq/github.com/roycehoe/hansard-scraper/plans/bill-linking-build

python -m alembic heads                      # one head; see the migration list below
python -m alembic upgrade head               # c4d8e2a1b7f3, e8a2b4c6d1f9, d7e1f3a9c2b5, f3a7c9e1b2d4, a9d4e7f2c1b8, b7c2d9e4f1a3, c8d3e1f6a2b9, d9e4f2a7b3c1 (sets role READING on every stored billreport row)
python -m alembic check

python -m scripts.apply_bills_supplement --captures-directory $BUILD/bills-supplement-captures --plan-file $BUILD/bills-supplement-plan.json
# expect: 11 captures, 2,394 entries, 48 duplicates
python -m scripts.apply_bills_supplement --captures-directory $BUILD/bills-supplement-captures --plan-file $BUILD/bills-supplement-plan.json --commit

python -m scripts.apply_egazette_supplements --harvest-directory $BUILD/egazette --plan-file $BUILD/egazette-plan.json
# expect: 177 supplements, 0 unparsed
python -m scripts.apply_egazette_supplements --harvest-directory $BUILD/egazette --plan-file $BUILD/egazette-plan.json --commit

python -m scripts.apply_acts_supplement --captures-directory $BUILD/acts-supplement-captures --plan-file $BUILD/acts-supplement-plan.json
# expect: 65 captures, 1,487 entries, 10,999 duplicates dropped; decades 1980s 134, 1990s 355, 2000s 410, 2010s 380, 2020s 208
python -m scripts.apply_acts_supplement --captures-directory $BUILD/acts-supplement-captures --plan-file $BUILD/acts-supplement-plan.json --commit

python -m scripts.apply_repealed_acts --captures-directory $BUILD/repealed-acts-captures --plan-file $BUILD/repealed-acts-plan.json
# expect: 2 captures, 511 rows, 286 entries, 225 duplicates, 1 entry with no enactment year; by decade of enactment 1930s to 2020s
python -m scripts.apply_repealed_acts --captures-directory $BUILD/repealed-acts-captures --plan-file $BUILD/repealed-acts-plan.json --commit

python -m scripts.apply_act_links --harvest-directory <harvest> --plan-file $BUILD/act-links-plan.json
# read before the commit:
#   Bills: about 2,811 less the merges; bill numbers by source about 2,306 from the listing plus the eGazette fills; classes about 152 supply and 21 repeal
#   Split bills merged: about 24; check each against data/hand_kept_bills.json (a merge equal to a hand-kept bill is expected; one that splits a hand-kept bill refuses the run)
#   eGazette Acts linked to a bill: up to 65
#   Act numbers by source: ACTS_SUPPLEMENT_LISTING about 1,392 (1,372 pre-cutoff passed bills plus about 20 passed after 14 October 2024); passed bills without an Act number about 1,290
#   Repealed Act links by source: REPEALED_ACTS_LISTING about 442; passed bills without one about 2,240
#   Budget reports linked to a supply bill: about 2,936 of 2,998; the write log then says about 2,936 budget report links inserted, 0 deleted
#   the R2 outcome line above; linked act history entries must not fall below 5,107
python -m scripts.apply_act_links --harvest-directory <harvest> --plan-file $BUILD/act-links-plan.json --commit

python -m scripts.list_bill_review_items --review-file $BUILD/bill-review-items.json --summary-file docs/figures/$(date +%F)-bill-review.txt
git add docs/figures && git commit -m "docs: add the bill review figures after the bill number write"
```

Expect in the review summary 1 `ACTS_SUPPLEMENT_BILL_WITH_TWO_ACT_NUMBERS`, about 94 `ACTS_SUPPLEMENT_ENTRY_UNPLACED`, 9 `REPEALED_ACT_BILL_WITH_TWO_ACTS`, 9 `BUDGET_REPORT_WITH_TWO_SUPPLY_BILLS` and about 46 `BUDGET_REPORT_WITHOUT_SUPPLY_BILL`, a budget debates line (about 2,936 of 2,998 budget reports attached; it carries no test number, because test 5 of `docs/vision.md` is the precision hand check), and test 3 printed twice per era, over every passed bill and over the bills of no class, with the repealed Act count beside it (about 442 linked, about 249 resolved by that link alone). The review file is the R8 list; each item is ruled once and the ruling goes into the hand-kept files. A hand-kept entry is retired only after the production dry run shows the rule rebuilding it with the same report ids: the plan's `split_merges` and each hand-kept bill's `report_ids`, and `bill_number_bill_index` beside each hand-kept Act link.

## Open questions, with recommendations

1. Fetch the 12 recently repealed Acts' PDFs from the Archive (about 20 requests) to link up to about 28 bills? Recommendation: yes, as a later small job, after the review list shows how many of those bills are still unresolved.
2. Retire the hand-kept bills and Act links that R3 and R2 reproduce? Recommendation: not yet; keep them until the production dry run prints the same report ids, then retire the 9 and keep Good Shepherd Nuns, the CLTPA (Amendment No. 2) report and CLTPA1955/7.
3. The attribution lines above are drafted from the research notes, not the terms page. Recommendation: read clause 11 once and amend the wording before the site shows eGazette fields.
4. `.basedpyright/baseline.json` grew by six entries of the three baselined SQLModel typing kinds (wide `select`, `Row(*row)` with an Optional id, `__tablename__` to the vacuum helper). Recommendation: accept; a typed fix for all 119 files is its own change.
5. The Act number rule compares the bill's title key as stored, so a Hansard title that starts with "The" never matches the Supplement's key, which drops the article. The bill number rule (R1) tries both forms. The review found 2 bills this misses (Kwong-Wai-Shiu Hospital 2017, Saint Maur 2024). Recommendation: adopt R1's two-form match in a later change and re-measure; it was left out so the shipped rule equals the measured one.
6. The rule does not refuse an Act number that two passed bills both take, which the bill number rule does refuse. The rebuild has 0 such cases. Recommendation: add the guard in the same later change, because a gap in a year's listing could make two same-title bills within 121 days claim one number.
7. The baseline grew by three more entries of the same kinds for the new CRUD modules and script, and lost one for the widened bill select. Recommendation: accept.
8. The repealed Act rule links a principal bill only to an Act enacted in the year of its first or last report, not to any Act whose life holds the bill. The brief read "dates inside the Act's life"; the life rule linked new Acts to the Acts they replaced (45 of 88 labelled pairs wrong). Recommendation: keep the year rule; it is the one measured at 106 of 106.
9. An amendment bill's link lands on the Act it amended, which is what SSO lists as repealed; the amending Act itself is never listed. Recommendation: the site's wording for this source should say "amended an Act since repealed", not "became an Act since repealed".
10. Acts listed as Expired, Omitted, Replaced or Renamed are candidates with the Repealed and Spent ones, which is how 77 Supply Bills (Spent, Expired) link. Recommendation: keep; the status is on the SSO page the link opens.
11. 8 Supplementary Supply Bills of 1994 to 2001 are refused because the loose key folds "(No. 2)" away and SSO lists both Acts of the year. Recommendation: a later change may try the strict key before the loose one; low value, since these bills carry the SUPPLY class already.
12. The budget window is 45 days before the Supply Bill's first report and 30 after its last. The strict bracket loses 395 reports (the Budget Statement debated before the first reading, heads after the last report). Recommendation: keep 45 and 30; the 72-sample bills take only reports inside their own dates, and the known-bad run shows the margins never reach another year's bill.
13. 35 "SUPPLEMENTARY PROVISION" reports of 1955 to 1960 attach to nothing, because the Assembly voted supplementary provision by resolution, not by bill. Recommendation: rule them not bills, so the review items close without a hand-kept entry.
14. The 9 two-bill refusals are supplementary estimates debated while a Supplementary Supply Bill and a (No. 2) or Final Supply Bill of the same year were both open. Recommendation: leave them unattached; a reader reaches both bills by date.
15. The site (`roycehoe/hansard`) reads no `billreport` row yet. Recommendation: when its bill page is built, it reads `role` and lists the BUDGET_DEBATE rows under their own heading, so a Committee of Supply head never reads as a reading.

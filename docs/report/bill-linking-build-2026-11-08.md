# Bill linking build, 8 November 2026

What was built from the rulings on [bill-linking-rules-2026-11-08.md](bill-linking-rules-2026-11-08.md), what the two research fetches found, and the commands that put it on production. The build host had no database, so nothing here is written to production or the replica yet; every count below comes from the research rebuild, the test suite or the fetched files.

## What is on master

| Ruling | Built | Where |
|---|---|---|
| 1. Bills Supplement as a raw table, bill numbers by R1 | `billssupplementcapture` (11 Archive captures as received) and `billssupplemententry` (2,394 rows); `bill.bill_number` and `bill_number_source`; the 16 loose and similar links go to the review list | `scripts/apply_bills_supplement.py`, `services/bill.py`, migration `c4d8e2a1b7f3` and `d7e1f3a9c2b5` |
| 2. R3 split bills and R2 number check | Merges behind the bill-number conflict check; R2 kept in the plan and the dry-run log, never the stored link; the 9 reproduced hand-kept cases are golden tests in `tests/test_bill_number_rules.py` | `services/bill.py`, `services/act_link.py`, `populate/act_links.py` |
| 3. eGazette 2024 to 2026 | 177 PDFs on disk, one `egazettesupplement` row per PDF with the printed fields, R6 links from an Acts Supplement to its bill | `scripts/fetch_egazette_supplements.py`, `scripts/apply_egazette_supplements.py`, migration `e8a2b4c6d1f9` |
| 4. Repealed Acts in the Archive | Counted, not fetched in bulk; see below | `plans/bill-linking-build/repealed-acts-count.md` |
| 5. Supply and repeal classes, R8 list | `bill.bill_class`; `scripts/list_bill_review_items.py` with done tests 1 to 4 by era | `services/bill.py`, `scripts/list_bill_review_items.py` |

One rule changed in review. The report's R3 refuses a merge when "R1 gives the two different bill numbers", and the first code read the tail's first report as its first reading, which from 1967 on falls outside every listing window, so the check never fired. The check now looks for a Supplement entry of the tail's title published between the head's last report and the tail's first, and refuses when it carries another number. The Housing and Development pair of 1962 and 1963 is still refused, and a "Roads (Amendment No. 2)" tail read 44 days after its own entry now stays apart from a "Roads (Amendment)" head. Entries with a misprinted publication date (R4) also give no number now, because their window is a year off.

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

Full notes in `plans/bill-linking-build/repealed-acts-count.md`. The answer: a bulk fetch would link about 15 to 35 of the 769 "parent not current" bills (the research file holds 769 such lines, not 732), because a repealed Act's SSO page carries no Legislative History. Only a PDF capture of the Act's last in-force version carries one, and the Archive holds such PDFs for a few Acts repealed about 2015 or later.

- The 2020 capture of `/Browse/Act/Repealed/All?PageSize=500` lists 227 repealed Acts, all repealed in 1985 or later. Acts repealed before the 1985 Revised Edition are not listed.
- Of 7 captures read, 3 held a history with bill numbers and reading dates (BA1995, MRBA1979, PSOA2006), all PDFs of Acts repealed in 2019 or 2020. The 4 HTML captures held none.
- By loose title key, 187 bills (127 titles) match 83 repealed Acts, an upper bound. 28 of them, under 12 Acts repealed in 2015 or later, are where PDFs exist.
- Cost: about 20 requests for the 12 recent Acts (3 minutes paced), 95 to 170 for all 83.

Recommendation: fetch only the 12 recent Acts, if at all. The bulk fetch waits for Royce.

## The full R2 measurement

The 523-Act harvest is not on this host, so R2 ran only on fixtures here. The dry run of `apply_act_links.py` on the machine with the harvest prints the whole measurement over the 9,905 entries in one line:

```
Act and Ordinance entries by bill number rule outcome: number and title rules agree N, number and title rules disagree N, title rule only N, number rule only N, neither rule N, no bill number printed N
```

Quote it in the figures file. "Disagree" should be 0 or each case read before the commit; "number rule only" entries appear on the review list as `HISTORY_LINK_BY_NUMBER_ONLY`.

## Runbook

Run on a machine with `.env`, from a clean worktree of committed master, after `git pull`. Nothing here touches the speech table, so `attribution_text_share.py` and the shared-link check are not needed; if any step reports a speech count change, stop. The gitignored inputs are on the build host under `plans/bill-linking-build/` and must be copied first: `bills-supplement-captures/` (4.1 MB) and `egazette/` (88 MiB). `<harvest>` is the 523-Act harvest directory used for the 5 November write.

```bash
cd ~/ghq/github.com/roycehoe/hansard-scraper && git pull
git worktree add ../hansard-write master && ln -s "$PWD/.env" ../hansard-write/.env
cd ../hansard-write && export PYTHONPATH="$PWD" && BUILD=~/ghq/github.com/roycehoe/hansard-scraper/plans/bill-linking-build

python -m alembic heads                      # d7e1f3a9c2b5 alone
python -m alembic upgrade head               # c4d8e2a1b7f3, e8a2b4c6d1f9, d7e1f3a9c2b5
python -m alembic check

python -m scripts.apply_bills_supplement --captures-directory $BUILD/bills-supplement-captures --plan-file $BUILD/bills-supplement-plan.json
# expect: 11 captures, 2,394 entries, 48 duplicates
python -m scripts.apply_bills_supplement --captures-directory $BUILD/bills-supplement-captures --plan-file $BUILD/bills-supplement-plan.json --commit

python -m scripts.apply_egazette_supplements --harvest-directory $BUILD/egazette --plan-file $BUILD/egazette-plan.json
# expect: 177 supplements, 0 unparsed
python -m scripts.apply_egazette_supplements --harvest-directory $BUILD/egazette --plan-file $BUILD/egazette-plan.json --commit

python -m scripts.apply_act_links --harvest-directory <harvest> --plan-file $BUILD/act-links-plan.json
# read before the commit:
#   Bills: about 2,811 less the merges; bill numbers by source about 2,306 from the listing plus the eGazette fills; classes about 152 supply and 21 repeal
#   Split bills merged: about 24; check each against data/hand_kept_bills.json (a merge equal to a hand-kept bill is expected; one that splits a hand-kept bill refuses the run)
#   eGazette Acts linked to a bill: up to 65
#   the R2 outcome line above; linked act history entries must not fall below 5,107
python -m scripts.apply_act_links --harvest-directory <harvest> --plan-file $BUILD/act-links-plan.json --commit

python -m scripts.list_bill_review_items --review-file $BUILD/bill-review-items.json --summary-file docs/figures/$(date +%F)-bill-review.txt
git add docs/figures && git commit -m "docs: add the bill review figures after the bill number write"
```

The review file is the R8 list; each item is ruled once and the ruling goes into the hand-kept files. A hand-kept entry is retired only after the production dry run shows the rule rebuilding it with the same report ids: the plan's `split_merges` and each hand-kept bill's `report_ids`, and `bill_number_bill_index` beside each hand-kept Act link.

## Open questions, with recommendations

1. Fetch the 12 recently repealed Acts' PDFs from the Archive (about 20 requests) to link up to about 28 bills? Recommendation: yes, as a later small job, after the review list shows how many of those bills are still unresolved.
2. Retire the hand-kept bills and Act links that R3 and R2 reproduce? Recommendation: not yet; keep them until the production dry run prints the same report ids, then retire the 9 and keep Good Shepherd Nuns, the CLTPA (Amendment No. 2) report and CLTPA1955/7.
3. The attribution lines above are drafted from the research notes, not the terms page. Recommendation: read clause 11 once and amend the wording before the site shows eGazette fields.
4. `.basedpyright/baseline.json` grew by six entries of the three baselined SQLModel typing kinds (wide `select`, `Row(*row)` with an Optional id, `__tablename__` to the vacuum helper). Recommendation: accept; a typed fix for all 119 files is its own change.

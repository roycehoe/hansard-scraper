# Bill linking rules without an LLM, 8 November 2026

## The question as I read it

Royce asked how to link bills "without having to do it with an LLM", using "hard rules we can codify, much like the hansard documents". I read that as three tasks:

1. Find every place where judgment fills a gap in objective 7 today: an LLM pass, a hand-kept file entry or a manual review.
2. For each gap, propose a rule a script can apply the same way every time. Each rule must read a printed field (a title, a date, a bill number) from a named source.
3. Measure each rule's precision and recall against labelled cases: the 72-bill sample of 4 November and the 14 hand-kept entries. Run each rule once on a known-bad input to show the measurement can fail.

The gaps are the ones `docs/vision.md` lists under objective 7: 598 unlinked passed bills, the 65 bills passed after 14 October 2024, Parliament's bill list and bill numbers, the hand-kept entries and the review queue. This is research. Nothing in the pipeline or either database changed.

## What I checked, and what I could not

- **No database.** `DATABASE_URL` on this host is the fallback default, and a read-only connect failed on authentication. Every count below comes from a rebuild of the bill reports from openhansard.sg's public API instead. That rebuild covers the `/api/search/reports` and `/api/search/speeches` endpoints, read 2 seconds apart.
- **The rebuild runs production's grouping code.** `services/bill.py::group_bills` runs unchanged over the rebuild, with the first- and third-reading patterns applied to search snippets. It matches production's counts: 5,839 bill and bill-intro reports, 5,806 grouped, 33 skipped and 2,682 passed bills. The rebuild has 2,822 bills where production has 2,811, because I left out the hand-kept bills and title corrections. That is deliberate: those entries are the labelled set.
- **Snippets cost some recall.** The rebuild finds reading lines in search snippets, not in full transcripts. A few bills show no first-reading line here that production may have.
- **Bills Supplement.** It comes from Internet Archive captures of SSO's Bills Supplement listing, 2,394 rows. No request went to sso.agc.gov.sg.
- **Legislative History.** It comes from six Act PDFs in Archive captures: ABA1965, CLTPA1955, CONS1963, MPA1995, NHBA1993 and BMSMA2004, parsed with `services/act_history.py`. The 523 texts production harvested are not on this host (`plans/bill-debate-linking/` is absent), so rule R2 is measured on 147 entries, not 9,905.
- **Report ids.** The site exposes SPRS report ids, not `report.id`. Where a rule reproduces a hand-kept bill, I matched it by its reports' dates and counts, not id by id.
- **Probe scripts.** They stay in `plans/bill-linking-rules/probes/` (gitignored). They read JSON files with dicts, so they do not follow STYLE.md and are not committed.

## Where judgment fills a gap today

| Gap | What fills it now | Size |
|---|---|---|
| Bills whose title changed between readings | `data/hand_kept_bills.json` | 6 entries |
| Bills whose report prints a misspelt title | `data/bill_title_corrections.json` | 5 entries |
| History entries no title rule reaches | `data/hand_kept_act_links.json` | 3 entries |
| The "72 of 72" grouping check | Built by Sonnet workers and a skeptic pass on 4 November | 72 bills |
| Why 598 passed bills have no Act link | 24 titles read by hand | 24 of 598 |
| Links with a third reading more than 40 days off | Spot-checked by hand | 22 links |
| Royce's rulings | Two-bill titles, report 35962, misprinted SSO dates kept as printed | 3 rulings |
| The review queue in objective 7 | Does not exist: no code, no table, no list | none |

Every link production holds today comes from code. Judgment enters through the 14 hand-kept entries and through the checks that vouch for the code.

## The sources a rule can key on

Hansard prints no bill number, but three other printed records do, and each carries a date that can be matched to a Hansard sitting:

| Source | Prints | Years | Status here |
|---|---|---|---|
| SSO Bills Supplement listing | Bill number, title as introduced, Gazette publication date (`DocDate` in the link) | 1961 to 2026 | 2,394 rows from Archive captures, on disk |
| Legislative History of each current Act | Bill number (not always), first, second and third reading dates, Act title | 1955 on | Production holds 9,905 entries; 6 Acts here |
| eGazette Acts Supplement PDF | Bill number, first-reading date, passing date, Act number | 1999 on | 3 PDFs (2025 and 2026) |

The other rules depend on the Bills Supplement, because it turns a bill number into a title and a date, and a title and a date are what our Bill rows hold.

## The rules

Each rule names its inputs, its result and what it was measured against.

### R1. Bills Supplement entry to bill

**Rule.** An entry links to the one bill that meets both conditions:
- its title key equals the entry's title key (`utils/title_key.py`, with a trailing "Ordinance" or "Act" read as "Bill" and a trailing year dropped);
- it holds a first-reading report between 0 and W days before the entry's `DocDate`.

W depends on the publication year: 35 days to 1966, 18 to 1989, 9 to 2010 and 4 from 2011.

**Fallbacks.** If no bill qualifies, two looser matches are tried in order, each needing exactly one bill in the same window:
- the loose key of `services/act_link.py::get_loose_title_key` (amendment and number words removed);
- a title similarity of at least 0.85.

The windows are the largest gaps seen between a unique same-title first reading and its publication date:

| Bill years | Entries | Gap in days (count) |
|---|---|---|
| 1961 to 1966 | 195 | 0 to 35, spread out |
| 1967 to 1989 | 759 | mostly 1 to 8; 12 published 34 to 42 days before the first reading |
| 1990 to 2010 | 809 | 1 day for 737; 3 or 4 days for 25 |
| 2011 to 2026 | 582 | 0 days for 566 |

**Result.** Of 2,394 entries, 2,335 link by exact title and first reading, 2 by the loose key and 14 by similarity. One has two similar candidates: 34/1973, where two Statutes of the Republic of Singapore (Miscellaneous Amendments) bills were read on one day. 42 link to nothing. No bill gets two entries. 2,351 of the rebuild's 2,822 bills get a bill number.

**Measured.**

| Test | Result |
|---|---|
| 72-sample bills with a Supplement entry | 66 of 66 linked to the bill whose reports the sample lists. Precision and recall 100%. The other 6 predate the Supplement (1955 to 1960). |
| Known-bad: every `DocDate` moved 60 days later | 15 false links in 2,394: 2 exact, 11 loose, 2 similar |
| Known-bad: two entries published the same day | 1,635 pairs, 0 linked to one bill |

So the exact rule is safe on its own: 2 false links in 2,394 under a wrong date. The two looser matches make 13 false links under a wrong date, so their 16 real links should go on the review list. All 16 read as typos or variants of one bill. For example, "MINOR OFFENCES (AMENDMENI) BILL" and "Statue Law Reform Bill" are corpus typos, and "Town Council" against "TOWN COUNCILS" is a variant. One needs a person: 23/1986 "Civil Defence (Amendment) Bill" links by loose key to "CIVIL DEFENCE BILL".

**The 42 left over.** Of the entries the window rule misses:
- 17 were published before the bill's first reading (12 of them in two 1970 batches, then one each in 1976, 1981, 2004, 2012 and 2013).
- 14 have a same-title bill whose first-reading line the rebuild does not see.
- 10 carry a misprinted date (R4).
- 1 prints its title as "Trade Unions (Amendment) Ordinance Bill" (19/1963).

### R1b. Bill-number neighbours, for the review list only

**Rule.** For an entry R1 misses, take the first readings of the nearest lower and higher linked numbers of the same year as bounds. Link the one same-title bill with a first reading between them.

**Measured.**
- Leave-one-out on 2,306 exact R1 links: 2,170 right, 0 wrong, 2 none, 2 with two candidates, and 132 with no neighbour on one side.
- On the 72 entries that narrower windows (30, 16 and 2 days) left: 57 linked, 5 none, 10 with no neighbour.
- Known-bad, each entry placed in the numbering of three years earlier: 84 false links in 1,722 placed, because titles such as "Supply Bill" recur every year.
- It also made one real error. Bill 6/2004 has two Supplement rows: the January introduction and the February reintroduction under a new title. R1b sent the January row to the February bill.

So R1b proposes, and a person confirms.

### R2. Legislative History entry to bill, by printed bill number

**Rule.** For an Act or Ordinance entry that prints a bill number:
1. Find the Supplement entry with that number, and its bill by R1.
2. Accept the link only if that bill holds a report within a day of the entry's first-reading date.
3. When production's title rule (`get_bill_link`) finds no bill, put the link on the review list with both titles, instead of storing it.

**Measured on 147 entries of six Acts, read from 22 April 1955 on:**

| Outcome | Entries |
|---|---|
| Number rule and title rule pick the same bill | 134 |
| Number rule only | 2: ABA1965/10 (Bill 39/1964, "Animals Ordinance") and NHBA1993/1 (Bill 17/1967, "National Records Centre Bill"). Both are hand-kept links, reproduced. |
| The two pick different bills | 4, each the two halves of one split bill (R3): CONS 24/1987, CONS 41/1989, BMSMA 6/2004 and Statutes (Miscellaneous Amendments) (No. 2) 30/2005 |
| Title rule only | 6: 1955 to 1960 entries whose number predates the Supplement or is printed "None" |
| Neither | 1: CLTPA1955/7, which prints no bill number |

**Known-bad: every printed number moved up by one.** The 134 agreements dropped to 0 and 130 became disagreements. The two number-only links became wrong links:
- ABA1965/10 went to the Slaughter-Houses and Meat Processing Factories Bill, read on the same two days.
- NHBA1993/1 went to a Criminal Procedure Code (Amendment) Bill.

The date check in step 2 caught neither wrong link, because bills read in one batch share their dates. That is why step 3 exists. A title bound looked possible: the right Supplement titles score 0.73 and 0.82 against the Act titles, and the wrong ones 0.38 and 0.57. But 0.57 is too close to 0.73 to set a bound on two cases. So a number-only link goes to a person until a run over production's 9,905 entries shows a safe bound.

### R3. Split bills: one bill stored as two

**Rule.** A *head* is a bill with a first-reading line and no third. A *tail* is a passed bill with no first-reading line. Merge a head with a tail when all of these hold:
- the tail's first report falls 1 to 800 days after the head's last;
- their title keys are at least 0.85 similar;
- no other head claims that tail;
- R1 does not give the two different bill numbers.

This needs no outside source.

**Measured.** The rebuild holds 116 heads and 47 tails, and the rule pairs 24.

| Pairs | What they are |
|---|---|
| 9 | Hand-kept cases, reproduced. The 4 split bills of `hand_kept_bills.json`: CONS 1987, CONS 1989, Maintenance of Parents 1994 to 1995 and Building Maintenance and Strata Management 2004. All 5 of `bill_title_corrections.json`: 43155, 12071, 40738, 35080 and 37275. |
| 1 | Wrong: Housing and Development (Amendment) 1962 paired with (Amendment No. 2) 1963. R1 gives them different bill numbers (183/1962 and 12/1963), so the last condition rejects it. |
| 14 | Unlabelled. On reading, 12 are typos or title variants ("INDUSTRAL RELATIONS BILL", "Statue Law Reform Bill", "The Society of Saint Maur"). The other 2 passed more than 366 days after their last earlier reading: National Sports Promotion Board (1969 to 1970) and Residential Property (1975 to 1976). |

**Known-bad: every head moved 1,800 days earlier.** 0 pairs, and no tail was claimed twice.

Recall on split-shaped hand-kept cases is 9 of 10. The miss is Good Shepherd Nuns (1958), introduced under a long title that scores under 0.85 against the short one.

The Legislative History gives a second, independent check. In all five R2 split cases, the history's first and third reading dates land on the head and the tail of one R3 pair. It also found one case nothing records: CONS1963/15, the Constitution (Amendment) Act 1971, Bill 7/1971. Its bill holds the first reading of 30 July 1971, but no third-reading half for 19 October 1971 is in the corpus.

### R4. Misprinted publication dates

**Rule.** Flag an entry whose `DocDate` falls before 1 January of the bill's year or after 31 January of the next year.

**Measured.** It flags 10 entries, and all 10 are misprints: 54 to 61/1970 dated 5 December 1971, 21/1986 dated 2011 and 16/2007 dated 2004. Worker C had named 21/1986 and 16/2007 before I wrote the check, so it caught both known-bad inputs. A stricter check, that dates rise with bill numbers, gave 54 flags, mostly batches published a day apart, so I dropped it.

### R5. Passed bills with no Act to link

Rules R1 to R3 give bill numbers and merge halves, but an Act link still needs a Legislative History entry. A current Act's history leaves out laws that were repealed, spent or replaced. So most of the 598 need a class, not a link.

| Class | Rule | Rebuild count, bills passed by 14 Oct 2024 |
|---|---|---|
| Supply | Title key matches `^(the)?(final\|further\|revised\|second\|third\|fourth\|supplementary)*(supply\|appropriation)(andbudgetadjustments)?(no\d+\|fy\d{2,4}\|\d{4})*bill$` | 152 |
| Repeal | Title key holds "repeal" and not "amendment" | 21 |
| Parent not current | No current Act has its loose key | 732 |
| Parent current | A current Act has its loose key | 1,523 |
| Parent re-enacted later | The matching Act's year is after the bill | 189 |

**Measured.**
- The supply pattern matched 150 Supplement titles, and all 150 are appropriation bills. It rejected the known-bad titles "Supply of Goods (Amendment)", "Liquor Control (Supply and Consumption)" and "Restrictions on the Supply of Petroleum and Electricity". It sent "Rehabilitation Loan Appropriation (Repeal)" to the repeal class.
- On the 72-sample, all 21 bills whose law is repealed or spent fell in the no-link classes (recall 100%). But only 21 of the 30 bills in those classes truly have no current Act (precision 70%). The misses were renamed Acts (Smoking Control became Tobacco), omnibus bills, "(As reported from Select Committee)" in a title, and histories that list a predecessor Act in an earlier Part.

So supply and repeal are rules (173 bills). "Parent not current" is triage for a person, not a verdict. I could not compare these classes bill by bill with production's 598, for want of the database.

### R6. Bills passed after 14 October 2024

Production's Act texts date from 2024, so no history lists these 65 bills.
- **Bill number.** R1 gives 50 of the 65 a bill number from the Archive captures. The 15 without one are 3 of 2024, 2 of 2025 and 10 of 2026, numbers the captured listings lack.
- **Act number.** The eGazette Acts Supplement PDF prints "Bill No. N/YYYY", the first-reading date, "passed by Parliament on <date>" and "No. N of YYYY". Its file number is not the Act number.
- **Rule.** Link an Act PDF to the bill R1 gives its bill number, and accept it only if the bill's third reading falls on the printed passing date.
- **Measured on 3 PDFs.** Food Safety and Security (Bill 49/2024, Act passed 8 January 2025), Electronic Conveyancing and Other Matters (Bill 11/2025, Act 20 of 2025) and Regulation of Imports and Exports (Amendment) (Bill 14/2025, Act 26 of 2025). All 3 land on the bill whose third reading is the printed date. The three passing dates differ, so swapping any two numbers fails the date check.

Three is a small sample. Q3 asks for the fetch that would measure all 65.

### R7. Parliament's bill list

Parliament's page counts 782 bills (its text says 781), but only the newest 10 are reachable without a browser. Its server action ignores its paging arguments, and `cms.parliament.gov.sg` answers 403.
- **Matching.** Matching by title key and first-reading date links 7 of the 10. The other 3 were first read on 3 and 4 November 2026, after the newest bill report in the rebuild (7 October 2026).
- **Count.** The Bills Supplement's highest numbers for 2006 to 2026 sum to 791 against Parliament's 782. I could not reconcile the 9 without the full list.
- **Terms.** Parliament's terms (clause 6) need written permission to reproduce its content.

The Bills Supplement carries the same bill numbers for 1961 on, so the list adds nothing a rule needs.

### R8. The review queue, as a list a script writes

Objective 7 names a review queue, and none exists. Every item above that a rule cannot settle falls into a class a script can list. I propose a read-only script that writes one file per run with these classes:

| Class | Count in the rebuild |
|---|---|
| Supplement links by loose key or similarity (R1) | 16 |
| Supplement entries with two candidates (R1) | 1 |
| Supplement entries with no bill, with R1b's proposal | 42 |
| Misprinted publication dates (R4) | 10 |
| Split-bill merges (R3) | 23 |
| History links by number only (R2) | 2 of 147 here, both right |
| History entries whose bill lacks the third-reading date | 2 of 147 here (MPA1995/1, which R3 merges, and CONS1963/15) |
| Passed bills from 1966 on with no Supplement entry | 76 |

A person rules each item once, and the ruling goes into a hand-kept file, as today. What changes is that a script writes the list, so a case missing from it points to a rule defect.

## The hand-kept entries, one by one

| Entry | Reproduced by | Note |
|---|---|---|
| Hand-kept bill: Building Maintenance and Strata Management, 2004 | R3, and R2 on BMSMA2004/1 | |
| Hand-kept bill: CONS (Amendment), 1987 to 1988 | R3, and R2 on CONS1963/31 | Supplement title "(Amendment No. 2)" |
| Hand-kept bill: CONS (Amendment), 1989 to 1990 | R3, and R2 on CONS1963/34 | |
| Hand-kept bill: Maintenance of Parents, 1994 to 1995 | R3, and the history dates of MPA1995/1 | Split by the 366-day rule |
| Hand-kept bill: Good Shepherd Nuns, 1958 | Not reproduced | Long title to short; before the Supplement |
| Hand-kept bill: CLTPA (Amendment No. 2), report 39429 | Not reproduced | All readings sit in a motion report |
| Title correction: 43155, Statutes (Miscellaneous Amendments) (No. 2) | R3; R1 loose key; R2 | |
| Title correction: 12071, Goods and Services Tax | R3 | |
| Title correction: 40738, Botanic Gardens | R3 | 1957, before the Supplement |
| Title correction: 35080, Evidence | R3; R1 similarity | |
| Title correction: 37275, Minor Offences | R3; R1 similarity | |
| Act link: ABA1965/10 | R2 (Bill 39/1964) | |
| Act link: NHBA1993/1 | R2 (Bill 17/1967) | |
| Act link: CLTPA1955/7 | Not reproduced | No bill number printed, 1960 |

That makes 11 of 14 reproduced. The 3 left are all from 1958 to 1960, before the Supplement begins, and two are the same bill. They stay hand-kept.

## What no rule here reaches

- **Bills from 1955 to 1960.** There are 319 passed bills in the rebuild. No Supplement listing covers them, and no free source online prints their numbers (see the companion report on archived sources). Their links rest on titles and dates alone, as now.
- **Repealed and replaced laws.** A current Act's history does not list them. Linking them needs the histories of repealed Acts, and I did not check whether the Archive holds those.
- **The 14 Supplement entries whose bill shows no first-reading line.** Some may be a rebuild artifact. A rerun on production's full transcripts would tell.

## Proposed changes to the pipeline (not shipped)

1. Store the Bills Supplement listing as a raw table, as received, and a `bill_number` on `Bill` set by R1. Record in `docs/data-loss-register.md` that R1 drops the link of entries it cannot place.
2. Add R3 to `services/bill.py` after grouping, behind the Supplement number check. Keep `hand_kept_bills.json` and `bill_title_corrections.json` as golden tests, and delete an entry only when a dry run produces the same report ids for it.
3. Add R2 to `services/act_link.py` after the title rules, with its date check, and send number-only links to the review list.
4. Add the supply and repeal classes to `Bill` as a closed enum. Leave "parent not current" out of the schema.
5. Add the R8 list as a read-only script in `scripts/`.
6. First, rerun the R2 measurement on production's 9,905 entries from the harvest directory. It needs no fetch.

## Requests sent

- openhansard.sg: about 300, 2 seconds apart, not logged one by one.
- web.archive.org: 55 by the Bills Supplement worker, including the six Act PDFs, 8 seconds apart or more, and 1 archive.org search by the sources worker.
- parliament.gov.sg hosts: 20. data.gov.sg: 7.
- assets.egazette.gov.sg: 6 by me, and 15 by the sources worker against a cap of 8. That worker stopped when it saw the count.
- sso.agc.gov.sg: none.

## Questions for Royce

No decision blocked the research, so none went to a decider agent. Each question below changes the pipeline or needs a fetch, so each waits for you.

1. **Store the Bills Supplement as a table and give `Bill` a bill number by R1?** The 2,394 rows are on disk from Archive captures, so it needs no new fetch. Recommendation: **Do**, with the 16 looser links on the review list.
2. **Add R3 and R2, and retire the 11 hand-kept entries they reproduce?** Recommendation: **Do**, but keep the 11 as test fixtures. Retire each only after a dry run on production gives its exact report ids, and run R2 on the full harvest first (proposal 6).
3. **Fetch the eGazette Bills and Acts Supplement PDFs for 2024 to 2026?** That is about 200 files at 3 seconds apart, under eGazette clause 11, with its attribution lines. It would fill the 15 missing bill numbers and give all 65 recent Acts their numbers and passing dates. Recommendation: **Do**, limited to 2024 on.
4. **Look for the histories of repealed Acts in the Archive?** That would cover most of the 732 "parent not current" bills. Recommendation: **Hold**. I would count the captures with one CDX query first and bring you the number.
5. **Store the supply and repeal classes, and build the R8 review list as a script?** Recommendation: **Do** for both. Keep "parent not current" as triage only (70% precision on the sample).
6. **Ask Parliament in writing for its bill list?** Recommendation: **Reject**. The Bills Supplement gives the same numbers from 1961, and the list adds nothing a rule needs.

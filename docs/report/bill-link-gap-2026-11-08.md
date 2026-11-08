# Why Act links are not 100%, and what sgparliament.com adds (8 November 2026)

Every figure below carries a label. **Measured** means this run computed it from a source it
read. **Rebuilt** means this run recomputed it off the database with the production code,
because this host has no database. **Production** means the number came from a run against
the real database, quoted here. **Estimated** means a rate measured on part of the set,
applied to the whole, with the bound stated.

No production or replica write was made. No request went to sso.agc.gov.sg. Requests:
web.archive.org 163, www.sgparliament.com 204, openhansard.sg 3.

## 1. The figure

A link means an `ActHistoryEntry.bill_id` pointing at a bill. A current Act's Legislative
History names a law, and the entry resolves to one of our bill groups.

| Quantity | Value | Label |
|---|---|---|
| Passed bills | 2,682 | rebuilt, exact match with production |
| Passed after 14 October 2024, the date the Act copies stop | 65 | rebuilt |
| Earlier passed bills with no Act link | 598 | production |
| Linked | 2,019 | arithmetic on the three above |

The rebuild reproduces 2,682 passed bills exactly, 5,825 grouped reports against production's
5,827, 23 split merges and 33 skipped reports. The 12-report difference is the hand-kept bills
and title corrections, which are keyed by production report ids this host does not hold. The
rebuild is close enough to use for rates; it is not used to restate 598, which stays
production's own number.

## 2. Where the mismatch lies

### One cause runs through the whole gap

A current Act's Legislative History begins at that Act's own enactment. Everything a
predecessor Act did belongs to the predecessor, whose own text is gone. So a bill is
unreachable whenever the Act it made or changed is not the Act of that name in force today,
and that holds whether or not an Act of that name is current.

The clearest proof is the Accountants Act. Of 146 passed bills whose Act was harvested and
whose loose title key matches a current Act, 5 do not link (measured). All 5 are Accountants
Bills, from 1971, 1980, 1987, 1998 and 2000. The current Accountants Act 2004 lists its own
amendments from 2004 on and nothing before. The five earlier bills amended the Act the 2004
Act repealed. No rule reaches them, because there is no entry to match.

### The cause table

Classes are exclusive and in this order: the Act copies stop; the bill class makes the Act
spent; no current Act carries the bill's loose title key; a current Act does but its history
does not reach the bill.

| Cause | Bills | Label |
|---|---|---|
| A supply bill. A Supply Act is never a current Act | 152 | measured: 0 of 152 linked |
| A repeal bill. The Act is spent once it has repealed | 21 | measured: 0 of 21 linked |
| No current Act carries the bill's loose title key | 367 | derived, 291 to 399 |
| A current Act carries it, but its history starts after the bill | 58 | estimated, 26 to 134 |
| Earlier passed bills with no Act link | 598 | production |
| Passed after the Act copies stop on 14 October 2024 | 65 | rebuilt |
| Total unlinked | 663 | |

The four causes sum to 598 exactly, because the third row is the residue. Only the fourth row
is measured as a rate: of 146 passed bills whose Act was harvested and whose loose title key
matches a current Act, 141 link, a rate of 96.6% with a 95% Wilson interval of 92.2% to 98.5%
(measured, 11 Acts). 1,712 of the 1,774 pre-cutoff passed bills in that class are neither
supply nor repeal, so the rate leaves 58 of them unlinked, between 26 and 134. The third row
takes the rest, and its range moves the other way.

The two classes are 1,774 bills whose loose title key matches one of the 523 current Acts and
843 whose does not (both rebuilt, and they sum to the 2,617 pre-cutoff passed bills). For the
arithmetic to close, 365 of the 732 non-supply non-repeal bills in the second class must link
through an Act of another name, by an omnibus amendment or a rename. The partial harvest
already shows 59 such links from 11 Acts, so the residue is consistent with what is measured.

### By era

Passed bills by the year of the bill's first report (rebuilt, sums to 2,682):

| Era | Current Act of the title key | Supply | Repeal | No current Act | After the cutoff | Total |
|---|---|---|---|---|---|---|
| 1955 to 1960 | 113 | 9 | 5 | 192 | 0 | 319 |
| 1961 to 2005 | 1,088 | 60 | 14 | 429 | 0 | 1,591 |
| 2006 on | 573 | 22 | 1 | 111 | 65 | 772 |

The gap is an old-bills problem. 192 of 319 bills from the first era have no current Act of
their title at all, against 111 of 707 from 2006 on.

### What is not the cause

Mis-grouping is not the cause. Of the 882 passed bills with no current Act of their loose
title key, 15 have no first reading detected, 48 hold one report, and 3 span over 366 days
(all measured). 629 of them carry a bill number from the Bills Supplement, so the bill itself
is well identified. What is missing is the Act, not the bill.

Parsing is not the cause. Across the harvested Acts the history parser produced no unparsed
entry and no Act with a missing history.

The title and date rules are not the cause. Of the 338 Act and Ordinance entries in the 11
harvested histories, 324 link
(95.9%, measured). The 14 that do not: 11 name a law whose reading predates 22 April 1955,
where the Hansard corpus starts, so no debate exists to link; 2 are reachable only by the
printed bill number; 1 finds no bill of its title and date.

### The entry side, and whether the two sets pair up

Production holds 9,905 history entries and links 5,107, so 4,798 are unlinked. On the
harvested Acts the kind mix is 308 ACT, 111 SUBSIDIARY_LEGISLATION, 41 REVISED_EDITION, 30
ORDINANCE, 10 OTHER (measured, 490 entries). 31% of entries are not linkable by kind by
design. Applied to 9,905 that puts about 3,070 of the 4,798 outside the question, leaving
about 1,730 linkable entries unlinked, most of them laws older than the corpus (estimated
from a 490-entry sample, so treat the split as indicative, not settled).

The two unlinked sets do not pair up. An unlinked bill has no entry anywhere, because its
Act is not current; an unlinked entry mostly names a law older than Hansard or is not a law
at all. For the 5 unlinked covered bills, no unlinked entry of their title key exists that
should have matched. Fixing the entry side would not move the bill side.

### What a link claims

Two claims share one column today. An entry at ordinal 1 of an Act's history says the bill
became that Act. Any later ordinal says the bill changed that Act. The database does not
record which, and the second claim is the common one.

## 3. sgparliament.com

I read robots.txt first. It says "The record is public and free to crawl, index and cite" and
disallows `/api/`. Only page routes were fetched. 204 requests, 2 s apart.

It has no bill page and no Act page. `/bills` answers 404, and the route manifest holds no
bill, legislation or Act route. A stratified sample of 120 passed bills, 16 strata of era
crossed with cause class, seed 20261108, was looked up by sitting date and title:

| Era | Bills sampled | Debate page found | Bill number on the page | Act link | Link to another reading |
|---|---|---|---|---|---|
| 1955 to 1960 | 19 | 11 | 0 | 0 | 0 |
| 1961 to 2005 | 48 | 35 | 0 | 0 | 0 |
| 2006 on | 53 | 50 | 0 | 0 | 0 |
| All | 120 | 96 | 0 | 0 | 0 |

All measured. No page carried a link to any host but sprs.parl.gov.sg. The one page flagged
for an Act reference, debate 9018, quotes the bill's own long title from Hansard ("to amend
the Arbitration Act (Chapter 10 of the 2002 Revised Edition)"), which our corpus holds
verbatim. It is text, not a link.

**Theory: sgparliament fills gaps we leave.** Evidence against it: 0 bill numbers, 0 Act
links and 0 cross-reading links on 96 pages spanning every era and every cause class. Evidence
for: none. Rejected.

**Theory: it chains a bill's readings by a rule we lack.** Its explorer calls
`/api/parliament/debate-groups` and labels groups `title_match`, so it groups sections with an
identical title. Tested against held-out cases: for the 1958 Good Shepherd Nuns bill, whose
four Hansard titles differ, it produces no chain, and for 1955 it returns no groups at all.
Our own grouping (title key, 366-day split, merges) is strictly stronger. Rejected.

Nothing was copied from sgparliament into our data, and nothing in the game plan derives from
it. It is also behind us on coverage: 24 of the 120 sampled bills have no page there at all,
including 8 of 19 from 1955 to 1960.

## 4. A source we are not using: the Acts Supplement listing

The Bills Supplement listing is already in the build. The **Acts** Supplement listing is not,
and it is the one source that reaches bills whose Act is gone, because it lists the Act as
published, repealed and spent Acts included.

One Internet Archive capture per year was fetched and parsed, giving 1,487 distinct rows over
act years 1980 to 2025, effectively 1985 on (1982 to 1984 are empty, 1980 and 1981 hold one
row each). The site's own "All" listing states 1,502 results, so the harvest holds about 99%
of what SSO publishes.

The rule I tested. A passed bill's last report is its third reading, so take Acts Supplement
rows whose title key equals the bill's and whose publication date falls between one day
before and 120 days after that reading, and accept only where exactly one Act number matches.
The window comes from 261 labelled pairs: minimum -36 days, median 33, 90th percentile 58.

| Measurement | Result | Label |
|---|---|---|
| Precision against the Act number a linked entry prints | 250 agree, 0 disagree | measured |
| Pre-cutoff passed bills reached | 1,372 of 2,617 (52.4%) | measured |
| 1955 to 1960 | 0 of 319 | measured |
| 1961 to 2005 | 728 of 1,591 (45.8%) | measured |
| 2006 on | 644 of 707 (91.1%) | measured |
| Supply bills reached | 88 of 152 | measured |
| Repeal bills reached | 8 of 21 | measured |
| Known-bad input: a title key two Act numbers share in one window | 1 case, refused | measured |

The known-bad run. The Supplementary Supply (FY 2002) Bill, third read 5 December 2002, has
both 42/2002 and 3/2003 in its window. The rule refused rather than guess, which is the
behaviour wanted.

The floor on what this adds is firm. Supply and repeal bills are measured at 0 of 173 linked
today, and the route reaches 96 of them, so 96 bills are gained with no assumption about
overlap. Beyond those, the route reaches 1,276 of the other 2,444 pre-cutoff passed bills, and
how many are already linked cannot be settled without the full Act harvest. On the partial
harvest, linked bills with no current Act of their title are reached at 62.7% and unlinked
ones at 31.7%, which puts the extra gain between about 90 and 180 bills (estimated). Call the
whole route 190 to 280 bills.

It changes what a link claims. Today a link says the bill touched an Act whose text we hold.
An Acts Supplement link would say the bill became an Act that was published, whose text we do
not hold and may not exist in force. That is a definition change, and it is question 1 below.

## 5. The printed bill number in a history entry

`populate/act_links.py` already computes the bill a history entry's printed bill number names
and logs it against the title rule, but never stores it. Measured over 490 entries:

- 2 entries that only the printed number reaches, both correct. ABA1965 entry 10 prints
  39/1964 for "Animals and Birds Ordinance, 1965", which is the ANIMALS BILL; NHBA1993 entry 1
  prints 17/1967 for "National Archives and Records Centre Act, 1967", which is the NATIONAL
  RECORDS CENTRE BILL. Both were renamed between first reading and passing, which no title
  rule can bridge.
- 2 entries where the printed number disagrees with the title rule, and the printed number is
  wrong. Income Tax Act entries 180 and 181 print 36/2012 and 39/2012 crossed: 36/2012 is the
  Computer Misuse Bill and 39/2012 is the Economic Expansion Incentives Bill, per the Bills
  Supplement listing. Both bills were first read on 12 November 2012 and third read on
  14 January 2013, so only the title tells them apart, and the title rule got both right.

That pair of findings fixes the design: use the printed bill number **only where no title rule
finds a bill**, never to override one. Under that design the two known disagreements are
unreachable and the two known gains stand. At 2 gains per 490 entries the whole corpus would
yield roughly 40 entries (estimated).

It is not implemented. `docs/report/bill-linking-rules-2026-11-08.md` records that a
number-only link goes to a person until a run over production's 9,905 entries shows a safe
bound, and 490 entries is 5% of that. The measurement is here for the ruling, not ahead of it.

## 6. The game plan, ranked by bills gained per unit of effort

| # | Change | Bills gained | Cost | Source needed | Kind |
|---|---|---|---|---|---|
| 1 | Store the Acts Supplement listing and link a passed bill to its Act number | 190 to 280 | 2 to 3 days: one table, one populate module, one script, a migration, the 67 captures already fetched | Internet Archive copies of the SSO Acts Supplement, already in hand | Rule plus a data load, after a ruling on what a link means |
| 2 | Fall back to the entry's printed bill number where no title rule finds a bill | about 40 entries, a few bills | Half a day: one enum value, one migration, one branch in `services/act_link.py`, tests | None, the data is already parsed | Rule, after a ruling |
| 3 | Refresh the Act copies past 14 October 2024 | up to 65 | One harvest run | SSO Act PDFs through the Internet Archive | Data fetch |
| 4 | Record whether a link means became or changed | 0 | Half a day | None | Rule |
| 5 | Fetch repealed Acts' PDFs for their histories | 15 to 35 | Measured already in the build: a repealed Act's SSO page carries no Legislative History, and Acts repealed before 1985 are not listed | Internet Archive | Mostly impossible |
| 6 | Reach bills whose Act predates 1985 and is gone | 0 by rule | A person in a library with the bound Acts of 1955 to 1984, or a gazette run | Printed Government Gazette | A person, not a rule |

## 7. 100% cannot mean what it sounds like

Three groups cannot link however good the rules get.

- **152 supply bills and 21 repeal bills.** A Supply Act is spent when the year ends and is
  never a current Act. Measured: 0 of 173 are linked today. Counting them in the denominator
  makes the target unreachable by construction.
- **367 bills whose Act was repealed or replaced.** The successor Act's history starts at
  its own enactment. Where the Act was published after 1985 the Acts Supplement names it, which
  is item 1. Where it was not, nothing online names it.
- **319 bills from 1955 to 1960.** The Acts Supplement harvest reaches none of them.

With item 1 and item 3 done, the linked count goes from 2,019 of 2,682 (75.3%) to roughly
2,270 to 2,360 (85% to 88%), estimated. The honest denominator is a different number: of 2,617
pre-cutoff passed bills, 2,444 are neither supply nor repeal, and against that denominator the
rate today is 82.6% and would become 92% to 95%.

## 8. Questions

1. **What may a link claim?** Item 1 would link a bill to an Act by number and title from the
   Acts Supplement listing, with no Act text held and no guarantee the Act is in force.
   Recommendation: allow it, as a separate claim with its own source value, so a reader can
   tell a bill linked to a current Act's history from one linked to a published Act number.
2. **Adopt the printed bill number as a fallback only?** 2 gains and 0 reachable errors on 490
   entries, against your recorded rule that a number-only link waits for a run over all 9,905.
   Recommendation: adopt it fallback-only, because the design makes the known failure
   unreachable; or say the word and the full 9,905-entry run happens once the Act harvest
   finishes.
3. **Should supply and repeal bills stay in the denominator?** Recommendation: report both
   rates, and make the headline the 2,444-bill denominator, because it is the one a rule can
   move.
4. **Refresh the Act copies past 14 October 2024?** 65 bills, one harvest run.
   Recommendation: yes, and fold it into the next Act harvest rather than running it alone.
5. **Finish the 523-Act harvest?** 30 of 523 Acts are in hand after about 50 minutes of
   paced fetching, so the rest is roughly 7 hours at 8 s a request and one worker. It would
   turn the one estimate in the cause table into a measurement and settle the overlap in item
   1. Recommendation: run it overnight, on its own, with the laptop plugged in.

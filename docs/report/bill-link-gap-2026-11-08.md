# Why Act links are not 100%, and what sgparliament.com adds (8 November 2026)

Every figure below carries a label. **Measured** means this run computed it from a source it
read. **Rebuilt** means this run recomputed it off the database with the production code,
because this host has no database. **Production** means the number came from a run against
the real database, quoted here. **Estimated** means a rate measured on part of the set,
applied to the whole, with the bound stated.

No production or replica write was made. No request went to sso.agc.gov.sg. Requests:
web.archive.org 454, www.sgparliament.com 204, openhansard.sg 3.

**Revised later the same night, over 263 of 523 Acts instead of 11.** The harvest ran on while
this was first written, and the bigger sample moved four figures, all against the first
reading. The link rate inside the harvested part fell from 96.6% on 146 bills to 92.1% on
1,436, because the first 11 Acts were the ones most bills share a title with and so the best
covered. Repeal bills are 3 of 21 linked, not 0 of 21. The history parser does leave entries
unparsed, 28 of 6,898. The printed bill number disagrees with the title rule 12 times, not 2.
Where the first version carried an estimate, this one carries a measurement, and the one
estimate left is named. Anything citing the earlier 96.6%, 31.7% or "no unparsed entry" should
take the figures below instead.

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

Of 1,436 passed bills whose Act was harvested and whose loose title key matches a current Act,
114 do not link (measured over 257 parsed histories). The Accountants Act shows the shape.
Five Accountants Bills, from 1971, 1980, 1987, 1998 and 2000, all fail, because the current
Accountants Act 2004 lists its own amendments from 2004 on and nothing before. The five
amended the Act the 2004 Act repealed. No rule reaches them, because there is no entry to
match.

### The cause table

Classes are exclusive and in this order: the Act copies stop; the bill class makes the Act
spent; no current Act carries the bill's loose title key; a current Act does but its history
does not reach the bill.

| Cause | Bills | Label |
|---|---|---|
| A supply bill. A Supply Act is never a current Act | 152 | measured: 0 of 152 linked |
| A repeal bill. The Act is usually spent once it has repealed | 18 | measured: 3 of 21 linked |
| No current Act carries the bill's loose title key | 292 | derived |
| A current Act carries it, but its history starts after the bill | 136 | measured rate, bound 114 to 162 |
| Earlier passed bills with no Act link | 598 | production |
| Passed after the Act copies stop on 14 October 2024 | 65 | rebuilt |
| Total unlinked | 663 | |

Three of the four causes are measured and the third row is the residue. The fourth row comes
from a rate: of the 1,436 harvested bills whose loose title key matches a current Act and which
are neither supply nor repeal, 1,322 link, a rate of 92.1% with a 95% Wilson interval of 90.5%
to 93.3%. Over all 1,712 such bills that leaves 136 unlinked, between 114 and 162.

The two classes are 1,774 bills whose loose title key matches one of the 523 current Acts and
843 whose does not (both rebuilt, summing to the 2,617 pre-cutoff passed bills). For the
arithmetic to close, 440 of the 732 non-supply non-repeal bills in the second class must link
through an Act of another name, by an omnibus amendment or a rename. The 263 Acts in hand
already supply 295 such links, and the remaining 260 Acts are the ones fewest bills share a
title with, so the residue is consistent with what is measured without being proved by it.

How far the rebuild reaches: 263 of 523 Acts give 6,898 of production's 9,905 history entries
(69.6%) and 1,715 of its 2,019 linked passed bills (84.9%). The harvest is ordered by how many
passed bills share each Act's title, which is why half the Acts carry five sixths of the links.

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

Parsing is close to free of fault, and what it drops is not linkable anyway. The parser leaves
28 of 6,898 entries unparsed (0.4%, measured), and every one is a Government Notification head
such as "G.N. No. S 394/1948", which is subsidiary legislation and never a bill. Six harvested
Acts hold no Legislative History at all, and all six were enacted between 2020 and 2024, so
they have no history to print yet.

The title and date rules are not the cause. Of the 4,499 Act and Ordinance entries in the
harvested histories, 3,802 link (84.5%, measured). Of the 697 that do not, 685 name a law whose
reading predates 22 April 1955, where the Hansard corpus starts, so no debate exists to link.
The remaining 12 are the whole of the rules' failure: 8 print no reading date, 3 are reachable
only by the printed bill number, and 1 finds no bill of its title and date.

### The entry side, and whether the two sets pair up

Production holds 9,905 history entries and links 5,107, so 4,798 are unlinked. Over the 263
harvested Acts the mix is 3,539 ACT, 1,165 REVISED_EDITION, 1,155 SUBSIDIARY_LEGISLATION, 960
ORDINANCE and 79 OTHER (measured, 6,898 entries), so 34.8% of entries name no law a bill could
have made. Of the 4,499 that do, 3,802 link and 685 of the 697 failures name a law read before
22 April 1955. Scaled to 9,905 entries that puts about 3,450 of the 4,798 outside the question
by kind and about 1,330 beyond the corpus by date, leaving a few dozen the rules genuinely
miss (the counts are measured, the scaling to 9,905 is estimated).

The two unlinked sets do not pair up. An unlinked bill has no entry anywhere, because its Act
is not current, while an unlinked entry almost always names a law older than Hansard or is not
a law at all. Fixing the entry side would move 12 entries and would not move the bill side.

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

## 4. The source we were not using: the Acts Supplement listing

The Bills Supplement listing was already in the build. The **Acts** Supplement listing was not,
and it is the one source that reaches bills whose Act is gone, because it lists the Act as
published, repealed and spent Acts included. It shipped on master the same evening, measured
again on the shipped code, and the figures below are what that build was based on.

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

What it adds is now measured rather than estimated. Of the 1,372 pre-cutoff passed bills the
route reaches, 1,033 already have an Act history link at 263 Acts and 339 do not. The 339 is an
upper bound that will fall as the rest of the harvest lands: the rebuild holds 903 unlinked
bills against production's 598, so 305 more will link, and if they are reached at the rate of
the unlinked set as a whole (339 of 903, 37.5%) then 114 of them are already in the 339. That
leaves about 225 bills gained, with a firm floor of 93, because 88 of the 152 supply bills are
reached and none of them links today, and 8 of the 21 repeal bills are reached against 3
linked.

It changes what a link claims. An Act history link says the bill touched an Act whose text we
hold. An Acts Supplement link says the bill became an Act that was published, whose text we do
not hold and which may not be in force. Royce ruled that a bill may carry that second claim as
long as it is stored separately, which is why the build put it on `bill.act_number` with its own
source value rather than in `acthistoryentry.bill_id`.

## 5. The printed bill number in a history entry

`populate/act_links.py` already computes the bill a history entry's printed bill number names
and logs it against the title rule, but never stores it. Measured over 6,898 entries:

- 3 entries that only the printed number reaches, all correct. ABA1965 entry 10 prints 39/1964
  for "Animals and Birds Ordinance, 1965", which is the ANIMALS BILL; NHBA1993 entry 1 prints
  17/1967 for "National Archives and Records Centre Act, 1967", which is the NATIONAL RECORDS
  CENTRE BILL. Both were renamed between first reading and passing, which no title rule can
  bridge.
- 12 entries where the printed number disagrees with the title rule. All 12 sit where a title
  rule already found a bill, and the two I checked by hand show the printed number is the wrong
  one: Income Tax Act entries 180 and 181 print 36/2012 and 39/2012 crossed, because 36/2012 is
  the Computer Misuse Bill and 39/2012 is the Economic Expansion Incentives Bill per the Bills
  Supplement listing. Both bills were first read on 12 November 2012 and third read on
  14 January 2013, so only the title tells them apart, and the title rule got both right.

That fixes the design. Use the printed bill number only where no title rule finds a bill, never
to override one. All 12 disagreements then become unreachable, because every one of them sits
on an entry a title rule already linked, and the 3 gains stand. Over 6,898 entries the
fallback-only rule has 3 gains and no reachable error.

It is not implemented, and after Royce's ruling of the same night it waits for the run over all
9,905 entries. 6,898 is 70% of that, so the remaining 3,007 entries would have to hold a
disagreement of a new shape, one with no title link, to change the design.

## 6. The game plan, and what has already shipped

Royce ruled on this plan the same night, and another session built items 1 and 5 from it. The
rulings are in `docs/vision.md`; the built code and its own measurement are in
`docs/report/bill-linking-build-2026-11-08.md`. The table records the state, so nobody reads a
shipped item as open work.

| # | Change | Bills gained | State |
|---|---|---|---|
| 1 | Store the Acts Supplement listing and link a passed bill to its Act number | about 225, floor 93 | Shipped on master, not yet run against production. Stored as `bill.act_number` with source ACTS_SUPPLEMENT_LISTING, a claim of its own |
| 5 | Link a passed bill to the SSO page of its repealed Act | 442 bills link, 359 of them otherwise unresolved | Shipped on master from Royce's own direction, which went further than this plan: the repealed Acts listing, not the PDFs. The PDF path I costed here at 15 to 35 bills was the wrong route |
| 2 | Fall back to the entry's printed bill number where no title rule finds a bill | 3 entries | Waiting. Royce ruled it waits for the run over all 9,905 entries; 6,898 are measured |
| 3 | Refresh the Act copies past 14 October 2024 | up to 65 | On hold. Royce ruled the eGazette links already cover those 65 bills |
| 4 | Record whether a link means became or changed | 0 | Open, and now partly answered by the three separate claims the build added |
| 6 | Reach bills whose Act predates 1985 and is gone | 0 by rule | A person in a library with the bound Acts of 1955 to 1984, or a gazette run. For 1955 to 1960 Royce ruled a citation to volume, Supplement number and page counts as held; nothing is built for it |

## 7. 100% cannot mean what it sounds like

Three groups cannot link to a current Act's history however good the rules get.

- **152 supply bills and 21 repeal bills.** A Supply Act is spent when the year ends and is
  never a current Act. Measured: 3 of the 173 are linked today, all three repeal bills.
  Counting them in the denominator makes the target unreachable by construction.
- **292 bills whose Act was repealed or replaced.** The successor Act's history starts at its
  own enactment, so the bill has no entry anywhere. The Acts Supplement names the Act where it
  was published after 1985, and the repealed Acts listing names the page where SSO still shows
  it, which is what items 1 and 5 now do.
- **319 bills from 1955 to 1960.** The Acts Supplement harvest reaches none of them, and SSO
  lists only Acts repealed from 1985.

The honest denominator is not 2,682. Of the 2,617 pre-cutoff passed bills, 2,444 are neither
supply nor repeal, and against that denominator the Act history link stands at 82.6% today
(production). What the two shipped claims add cannot be stated as one rate, because they are
three different claims about a bill: it changed an Act we hold, it became an Act that was
published, or the Act it touched is one SSO shows as gone. Royce's test 3 counts all three as
the outcome being resolved, and the production dry run of `apply_act_links.py` will print the
number. On the rebuild, 359 of the 2,161 unresolved pre-cutoff bills of no class gain the
repealed Act link and about 225 gain an Act number, which is why test 3's 95% target is now
within reach while the Act history link itself stays near 83%.

## 8. Questions

Royce ruled on questions 1 to 4 on the night of 8 November, and `docs/vision.md` records the
rulings: a bill may link to an Act number whose text we do not hold, as its own claim with its
own source; the printed bill number waits for the full 9,905-entry run; test 3 keeps 2,682 as
the headline denominator and prints the 2,444 rate beside it; the Act copy refresh is on hold
because the eGazette links cover those 65 bills. He also directed the repealed Act link and the
budget debate links, which went past anything this report proposed.

One question is left, and it is mine to ask rather than his to rule:

1. **Finish the 523-Act harvest?** 276 of 523 Acts are in hand, and the remaining 247 are
   roughly 3 hours at 8 s a request with one worker. It would replace the last estimate in the
   cause table, settle the 339 upper bound on item 1's gain, and give the printed bill number
   rule the full 9,905-entry run his ruling asks for. Recommendation: let it finish tonight, on
   its own, with the laptop plugged in and the lid open.

# Sources for archived bills, and the SSO Bills Supplement, 8 November 2026

## The question as I read it

There are two parts:
- **Archived bills before 2006** (where Parliament's own list starts). For each source: which years it covers, the form its text takes, what its terms allow, and a fetch route that keeps to its rate limits. Probe a handful of URLs to confirm it.
- **The AGC Bills Supplement on SSO.** What an entry carries, how far back it goes, how to key it to our `Bill` rows without judgment, and whether the project needs it.

The companion report, [bill-linking-rules-2026-11-08.md](bill-linking-rules-2026-11-08.md), measures the rules that use these sources.

## What I checked

Sources:
- Internet Archive captures of SSO, read through the CDX index and saved captures. No request went to sso.agc.gov.sg: SSO's terms allow automated extraction only from 03:00 to 07:00 SGT (clause 13(d)(i)), and its firewall answered a trial at 03:00 with empty 202 pages after 6 requests.
- A few files on the eGazette assets host.
- Parliament's bills page and data.gov.sg.
- The NUS legal history guide, plus a search of archive.org, HathiTrust, CommonLII and AsianLII.

Practice:
- Every request sent the project's user agent, at least 2 seconds apart (8 for the Archive).
- One worker sent 15 requests to `assets.egazette.gov.sg` against a cap of 8. It stopped when it saw the count. No host answered 429.
- Before this run the repo held bill numbers only for the 72 sampled bills (`docs/report/bill-debate-linking-2026-11-04.json`), and production holds the numbers its Legislative History entries print (`act_history_entry.printed_bill_number`). It held no bill text, and `plans/` held nothing on these sources.

## Coverage by era

| Years | Source that lists the bills | Text form | Bill number printed | Free online |
|---|---|---|---|---|
| 1955 to 1960 | Government Gazette Supplement (NUS print, K7449 S); Hansard debates (held) | Print | In the Legislative History of a current Act, for some Ordinances (CLTPA1955 prints 10/1955, 170/1958, 212/1959 and 17/1959; others print "None") | No |
| 1961 to 1965 | SSO Bills Supplement, old series | HTML bill page | Yes, running numbers past 100 (158 in 1961, 214 in 1963) | Through Archive captures; partial (31 of 158 in 1961) |
| 1966 to 1998 | SSO Bills Supplement | HTML bill page | Yes | Through Archive captures; complete but for 7 numbers |
| 1999 to 2005 | SSO Bills Supplement; eGazette Bills and Acts Supplement | HTML; born-digital PDF with a text layer | Yes ("Bill No. 1/99" in 1999, two-digit year) | Yes |
| 2006 on | The above, plus Parliament's bill list (782 bills) | PDF | Yes | Yes, but Parliament's list beyond the newest 10 needs a browser |

## The SSO Bills Supplement

### What an entry carries

A listing row has three fields: the title as introduced, "Bill N of YYYY", and from about 2010 a PDF link with its size. Examples, as captured:

- 1961: "Advocates and Solicitors (Amendment) Ordinance", Bill 144 of 1961, link `/Bills-Supp/144-1961/Published/19610602?DocDate=19610602`.
- 1973: "Prohibition on Smoking in Certain Places (Amendment) Bill", Bill 49 of 1973.
- 2026: "Supply Bill", Bill 4 of 2026, with a PDF of 228.8 KB.

The listing has no date column. The only date is `DocDate` in the link, which the bill page labels "Published in Bills Supplement on". It is the Gazette date, not the first reading. Taking the first reading from the Hansard sitting matched by title, the gap is 0 days for 566 of 582 bills from 2011, 1 day for 737 of 809 bills from 1990 to 2010, and up to 35 days before 1967.

The bill page carries more: "Bill No: N/YYYY", "Read the first time: <date>", the publication date and the bill's text. One older body reads: "Bill No. 70/1965 Read the first time on 31st December 1965."

Titles are the bill as introduced, which matters for linking. Bill 17/1967 is the "National Records Centre Bill", which became the National Archives and Records Centre Act. 24/1987 and 41/1989 are "Constitution (Amendment No. 2)" bills that passed as "(Amendment)". The one exception seen is 6/2004, printed with its new title and a year.

### How far back, and how complete

- The listing starts in 1961.
- The Archive holds 2,394 rows (2,393 distinct numbers) for 1961 to 2026. The all-years view at 500 rows a page gave 2,336 rows in 5 requests. The per-year captures for 1961, 1965, 1990, 2004 and 2023 matched that set.
- Real gaps in the numbering, missing from both the listing and the bill-page captures: 1966 (16, 22, 27, 39), 1975 (44), 1990 (22) and 1996 (24).
- 1961 to 1965 use an older series with high numbers. Only part of it appears (for example 31 rows for 1961, numbers up to 158).
- Recent years are short: 2024 has 47 of 50 (36 to 38 missing), 2025 has 20 of 22, and 2026 has 13, as of the capture of 24 May 2026. Bill-page captures run to 25/2026.
- 16,404 captures sit under `/Bills-Supp/`, 5,505 of them bill pages, covering nearly every number in the listing. 596 bills have a captured PDF, 572 of them from 2006 to 2026.

Faults in the source:
- Two dates are plain typos: 21/1986 is dated 11 October 2011 and 16/2007 is dated 10 April 2004.
- Bills 54 to 61/1970 are dated 5 December 1971, a year after their December 1970 first readings.
- One number has two rows. 6/2004 is "Building Maintenance and Management Bill" (read 6 January 2004) and "Building Maintenance and Strata Management Bill 2004" (read 6 February 2004). So the key is the number plus the publication date, not the number alone.

### The key to our Bill rows

The key is the bill whose title key equals the entry's, and whose first-reading report falls between 0 and a set number of days before `DocDate` (35 to 1966, 18 to 1989, 9 to 2010, 4 from 2011). That is rule R1 in the companion report.
- It links 2,335 of 2,394 entries by exact title, and 16 more by a looser title match that a person should confirm.
- It gets 66 of 66 sampled bills right.
- Under a known-bad date shift it makes 2 false links in 2,394.
- No bill gets two entries.

### Is it needed?

Yes, though not for grouping reports into bills, which works without it. It is the only free source that gives a bill number for each bill from 1961 to 2005, and the number is what four other things need:
- the Legislative History entries that print a bill number but a different title (two of the three hand-kept Act links);
- the guard that keeps two different bills from being merged as one split bill;
- the eGazette Acts Supplement, which names a bill by number only;
- any later join to Parliament's list.

It does not need a live SSO fetch. The listing is already on disk from Archive captures, and R1 supplies the first-reading date from Hansard, so the per-bill pages are not needed either.

## The other sources

### eGazette (assets.egazette.gov.sg)

- **Coverage.** Bills Supplement and Acts Supplement PDFs from 1999 to 2026. 1997 and 1998 answer 403.
- **A 403 means no file.** The body of each 403 is S3's `AccessDenied`, which S3 also returns for a missing key when the caller cannot list the bucket.
- **Names.** 2005 files have zero-padded names: `2005/.../Bills%20Supplement/01.pdf` answered 200 where `1.pdf` answered 403. That clears up the earlier "2005 bill 1 is 403".
- **Form.** Born-digital PDFs with a text layer. Page one of 1999/1 prints the title, "Bill No. 1/99." and "Read the first time on 20th January 1999."
- **The Acts Supplement.** Each PDF prints the Act number, the bill number, the first-reading date and "passed by Parliament on <date>". Its file number is not the Act number: 2026/01.pdf holds Act 20 of 2025.
- **URL.** `https://assets.egazette.gov.sg/YYYY/Legislative%20Supplements/Bills%20Supplement/N.pdf`, and the same under `Acts%20Supplement`.
- **Terms.** The terms of use (updated 10 July 2026) bar reproduction "without the prior written permission of MDDI", except under clause 11. Clause 11 allows extraction "through automated means" if it is not "abusive or intrusive, or a deceptive" and does not "disrupt or affect the Website's performance". It requires lines saying the e-Gazettes are Government copyright and reproduced with permission. The permission can be revoked at any time.
- **robots.txt** allows everything except `/search`. No rate limit is stated, and none was seen.

### Parliament (parliament.gov.sg)

- **Coverage.** 2006 on: 782 bills by its `filter_count` (the page text says 781). Its CMS row holds bill number, title, first and second reading dates and passing date, but no Act number.
- **Only 10 reachable.** The server action behind the search ignores its arguments, the same in 7 variations. The CMS host answers 403. Those 10 are the newest (19/2026 to 28/2026).
- **Terms.** Clause 6 needs written permission to reproduce its content.

### data.gov.sg

- Two Bills Supplement datasets: 2021 (43 rows) and 2024 (33 of 50). Each row carries bill number, title and publication date.
- Their PDF links point at `storage.egazette.gov.sg`, which the 4 November study found no longer resolves.
- Singapore Open Data Licence.

### Before 1961

No free source online was found.
- NUS's guide lists the 1946 to 1962 bills in the Gazette Supplement, in print only.
- CommonLII and AsianLII answered 403, and HathiTrust a Cloudflare challenge. A search of archive.org's texts returned 646 hits, none of them a Singapore gazette or bill.
- The National Archives and NLB pages are JavaScript apps that returned empty pages, so their holdings and terms are unresolved.
- LawNet is by subscription. The project's earlier reading of its terms (clause 4.2.4 bans downloading to build a search facility) was not checked again.
- For these years the only printed bill numbers are the ones a current Act's Legislative History carries.

## Fetch routes that keep to the limits

| Source | Route | Requests | Status |
|---|---|---|---|
| SSO Bills Supplement listing | Archive captures of `/Browse/Bills-Supp/Published/All?PageSize=500`, 8 s apart | 5 for 2,336 rows | Done; on disk |
| SSO bill pages, if text is ever wanted | Archive captures, one per bill | About 2,400, about 5.5 hours at 8 s | Not needed for linking |
| eGazette, 2024 to 2026 | Walk N up per year and stop after a run of 403s; whole PDFs, 3 s apart; clause 11 lines | About 100 bills (50, 22 and 28) and as many Acts, so about 200 | Needs Royce's go (question 3 of the rules report) |
| eGazette, 1999 to 2023 | The same | 998 bills by the Supplement's highest numbers, and nearly as many Acts, so about 1,900 | Not proposed; the SSO listing covers these years |

## URLs probed

| URL | Answer | What it showed |
|---|---|---|
| web.archive.org CDX, `sso.agc.gov.sg/Bills-Supp/*` | 200 | 16,404 captures |
| Archive capture, `/Browse/Bills-Supp/Published/All?PageSize=500` and pages 1 to 4 | 200 | 2,336 rows, "2336 results in 5 pages" |
| Archive capture, `/Bills-Supp/70-1965/Published/19660103?DocDate=19660103` | 200 | "Read the first time on 31st December 1965"; published 3 January 1966 |
| Archive captures, the two 6/2004 bill pages | 200 | Two bills under one number, read 6 January and 6 February 2004 |
| assets.egazette.gov.sg, 1999 Bills Supplement 1.pdf | 200 | "Bill No. 1/99", read 20 January 1999 |
| assets.egazette.gov.sg, 1997 and 1998 Bills Supplement 1.pdf | 403 | S3 AccessDenied: no file |
| assets.egazette.gov.sg, 2005 Bills Supplement 01.pdf (HEAD) | 200 | Zero-padded names in 2005 |
| assets.egazette.gov.sg, 2025 Bills Supplement 11.pdf (HEAD) | 200 | Present |
| assets.egazette.gov.sg, 2025 Acts Supplement 01.pdf | 200 | Bill 49/2024, read 12 November 2024, passed 8 January 2025 |
| assets.egazette.gov.sg, 2026 Acts Supplement 01.pdf and 10.pdf | 200 | Acts 20 and 26 of 2025, from Bills 11/2025 and 14/2025 |
| parliament.gov.sg, bills-introduced page and server action (7 variations) | 200 | The same newest 10 rows each time |
| cms.parliament.gov.sg/items/bills_introduced | 403 | "Request blocked" |
| commonlii.org/sg and asianlii.org/sg | 403 | Blocked |
| catalog.hathitrust.org search | 403 | Cloudflare challenge |

## What this means for the project

- **1961 to 2005.** These years are covered by a listing already on disk, with no new fetch.
- **2024 to 2026.** The gaps (3 numbers of 2024, 2 of 2025, and 2026 from number 14) and the Act numbers of the 65 bills passed after 14 October 2024 need about 200 eGazette PDFs.
- **1955 to 1960.** There is no free source for these years, and their links rest on titles, dates and the bill numbers a current Act's history prints.

# How researchers get Singapore's bills, and where the Act harvest is, 8 November 2026

I could not reach the production database, its replica or the machine that ran the 5 November write, so the production figures here (2,811 bills, 598 unlinked passed bills and so on) come from `docs/vision.md`, dated 6 November, and are not rechecked. I checked each source below live on 8 November 2026 with curl through one shared pacer, except where a row says blocked. No request went to sso.agc.gov.sg, and nothing changed in the pipeline or any database.

## In short

- **The harvest is not on this host, and the cheapest route is free.** It should still be on the machine that ran the 5 November write, because the notes from that day say to keep it. If it is gone, 523 Internet Archive requests over about 70 minutes rebuild it from the capture list committed beside this report. All 523 Acts have a capture in the window. For 461 the file is the same whichever capture was used. For the other 62, taking the newest capture in the window reproduces the figures the 5 November run recorded (93, 358 and 72) exactly, once captures made after 25 June 2026 are left out.
- **sgparliament.com is not a source.** It has no bill pages, no bill numbers and no Act links. It republishes SPRS and groups debates with the same title.
- **"No free source online before 1961" was half wrong.** NUS Digital Gems lists the Ordinances of 1947 to 1959 and marks the 1956 volume Open Access, though its terms bar automated use. NLB's catalogue lists digitised Colony gazettes to June 1959, 81 digitised Bills Supplement issues of 1965 to 1979 and 56 Acts Supplement issues of 1965 to 1980. The bills themselves are in print at NUS, NLB and Kew. I found no bill text from before 1961 that a program can read, and whether NLB's digitised gazettes include the bill Supplements needs one person with a browser to check.
- **Done test 1 cannot pass as written.** Bill numbers of 1961 to 1965 run across years, so "the highest number each year" counts 507 numbers that never belonged to those years. The real gap for 1961 to 1965 is 13 numbers, not 520.
- **Done test 3 needs about 291 more resolved bills, and one library visit could supply them.** NLB's Lee Kong Chian Reference Library holds printed tables of the written laws from 1819, which should name the Acts that no current Legislative History lists. I have read the catalogue records, not the books.

## 1. The 523-Act harvest

### What the code needs and what is here

`scripts/apply_act_links.py --harvest-directory DIR` reads `DIR/acts.json`, a list of `sso_code` and `title` pairs with extra keys refused, and `DIR/<sso_code>.txt`, the `pdftotext -layout` output of each Act's PDF (`populate/act_links.py:395-407`, `schemas/harvested_act.py`).

The harvest is not on this host. A search of the disk found only `plans/bill-linking-rules/act-pdfs/`, 6 Acts taken by a newest-capture rule that reaches 2025 and 2026, so they are not the 5 November inputs. `git worktree list` shows master alone, so `act-ship-96bd1da` and `act-ship-b6f6c93` are elsewhere. The session that built the harvest left no transcript here. open-sg-law's database on port 5436, with 509 stored PDFs, is not running on this host, and its rule is the latest capture of any year, so it would not match. No storage bucket is named in the notes or docs, and I used no cloud credentials.

This host does have enough to rebuild the inputs. `plans/bill-linking-rules/bills-supp/current-acts.jsonl` holds the 523 codes and titles of the July 2024 listing, and the Archive's index still lists every PDF.

### Which capture of each Act was used

The data-loss register says each Act was read from "an Internet Archive copy of its SSO PDF captured between July and December 2024". One index query per first letter of the codes shows that all 523 Acts have such a capture. For 461 of them every capture in that window is the same file, so it makes no difference which was read. The other 62 each have two or more versions in the window, and those are the Acts where the choice matters.

The 5 November notes record three figures: 93 Acts have a later version in a 2025 or 2026 capture, 358 have no newer capture, and that leaves 72 with a newer capture of the same version. I tested four rules against them.

| Rule for choosing the capture | Later version | No newer capture | Newer, same version |
|---|---|---|---|
| Recorded on 5 November | 93 | 358 | 72 |
| Newest capture in the window, captures from 26 June 2026 on left out | 93 | 358 | 72 |
| Newest capture in the window, today's index | 97 | 352 | 74 |
| Newest version stamp in the window | 88 | 242 | 193 |
| The July 2024 listing's version, else newest | 99 | 33 | 391 |
| Oldest capture in the window | 100 | 19 | 404 |

The newest capture in the window is the only rule that fits, and no other comes near on the middle column. I cannot say why the recorded figures stop at about 25 June 2026, when the run was in November. The Archive's index may have lagged, or the figures may come from an older reading of it. For the 62 this is an inference from three counts, and only the harvest itself would prove it.

`docs/report/bill-sources-2026-11-08-act-captures.tsv` lists the capture this rule picks for each Act, with its timestamp, URL, index digest and compressed length. Its `bodies_in_window` column is above 1 for the 62.

### The route, cheapest first

**1. Look on the machine that ran the write.** The notes from 5 November say "Keep harvest/ and archive-harvest/ for the newer-text work". I cannot reach that machine. On it, run:

```
ls ~/ghq/github.com/roycehoe/hansard-scraper/plans/bill-debate-linking/harvest/acts.json
ls ~/ghq/github.com/roycehoe/hansard-scraper/plans/bill-debate-linking/harvest/*.txt | wc -l
```

The second line should print 523. Then follow the runbook in `docs/report/bill-linking-build-2026-11-08.md` with that directory. The cost is a minute.

**2. If it is gone, refetch from the capture list.** Save the script below as `refetch_act_harvest.py` and run:

```
python3 refetch_act_harvest.py docs/report/bill-sources-2026-11-08-act-captures.tsv plans/bill-debate-linking/harvest
```

It sends 523 requests to web.archive.org, 8 s apart, with none to sso.agc.gov.sg and no index queries. That is 70 minutes of pacing, plus the transfer of roughly 180 MB of PDFs (137 MB by the index's compressed sizes), plus retries. Of today's 67 Archive requests, 19 answered 503 or 504, all of them index queries, so PDF fetches may do better. The machine needs `pdftotext` (`brew install poppler` or `apt install poppler-utils`), which this host lacks. A run that stops can be restarted and skips the PDFs it holds. The script checks each body against the index's SHA-1 digest before saving it.

I tested it on one Act, AA1928. With the right digest it wrote a `%PDF-1.4` file of 93,071 bytes, and with a wrong digest it stopped and wrote nothing. `pdftotext` was a stub in that test, so the conversion step has not run. **I have not run the 523 fetches, and they wait for Royce's go.**

```python
"""usage: python3 refetch_act_harvest.py <captures.tsv> <output-directory>. Needs pdftotext. Resumes: a PDF already saved is not fetched again."""
import base64, csv, hashlib, json, pathlib, subprocess, sys, time, urllib.error, urllib.request

AGENT = "hansard-scraper-research (+https://github.com/roycehoe/hansard-scraper)"
GAP_SECONDS = 8

def fetch(url):
    for _ in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENT}), timeout=300) as answer:
                return answer.read()
        except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
            wait = 300 if getattr(error, "code", 0) == 429 else 60
            print(f"retry in {wait}s: {url}: {error}", flush=True)
            time.sleep(wait)
    sys.exit(f"gave up on {url}")

captures, output = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(captures.open(encoding="utf8"), delimiter="\t"))
for row in rows:
    pdf = output / f"{row['sso_code']}.pdf"
    if not pdf.exists():
        body = fetch(f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}")
        digest = base64.b32encode(hashlib.sha1(body).digest()).decode()
        if digest != row["digest"]:
            sys.exit(f"{row['sso_code']}: body digest {digest}, CDX digest {row['digest']}")
        pdf.write_bytes(body)
        print(row["sso_code"], len(body), flush=True)
        time.sleep(GAP_SECONDS)
    subprocess.run(["pdftotext", "-layout", str(pdf), str(output / f"{row['sso_code']}.txt")], check=True)
listing = [{"sso_code": row["sso_code"], "title": row["title"]} for row in rows]
(output / "acts.json").write_text(json.dumps(listing, ensure_ascii=False, indent=1), encoding="utf8")
```

### How to tell a rebuilt directory is right

On a machine with database access, the dry run in the runbook should log 523 Acts, 9,905 entries, 6,158 Act and Ordinance entries, 27 Acts with no Legislative History and 0 unparsed entries. Its "what the write would change" lines should show no Act inserted, updated or deleted, no entry inserted or deleted, and entries updated only where a bill link moves, because the 8 November build changes the bills. An Act whose entries still differ is either one of the 62, so try its earlier version in the window, or a difference between `pdftotext` versions.

### Where having no database limits this

I could not compare these captures with production's `act.sso_code`, `act.title` or stored history rows, and I could not run the dry run. So the evidence for the 62 is the three counts, not a comparison of text, and the `pdftotext` version used on 5 November is unknown.

## 2. How sgparliament.com gets bills

It does not get them. Its About page says the record is "every sitting that Parliament's own site (sprs.parl.gov.sg) publishes", and SPRS is the only outside host on any page read.

- **No bill pages.** `https://www.sgparliament.com/bills` answers 404, and the site's route manifest has no bills, Acts or legislation route. A bill's readings are `/debate/[id]` pages, one per SPRS report.
- **Fields on a debate page, the same in every era tested** (1955: 34602, 1958: 36300, 1975: 42103, 1990: 47417, 2018: 11136). Title, date, Parliament, volume and sitting numbers, speakers, text, previous and next links. No bill number, Act number, reading dates, link to bill text or link to an Act in any era.
- **Linking.** Its explorer returns groups typed `title_match`, every section with the same title, for example "Public Sector (Governance) Bill" on 6 November 2017 and 8 January 2018. It states no method in words. Same-title bills of different years merge, so one group holds the Criminal Law (Temporary Provisions) (Amendment) Bill of 1975 and of 1976. The 1955 and 1958 dates tried returned no groups, and Good Shepherd Nuns 1958 has four titles, so nothing chains. The grouping in `services/bill.py` already does more than this.
- **1955 to 1960.** It holds nothing we lack.
- **Terms.** No licence page. `robots.txt` says "The record is public and free to crawl, index and cite" and also `Disallow: /api/`.
- **Repository.** None found. The author's Substack (`sgparliament.substack.com`) links none.

Royce asked to look at how sgparliament does it. The answer is that it stops at Hansard, so nothing in it helps hold a bill.

## 3. How researchers get these documents

### What citations show

A worker read about 50 citations to items of 1955 to 1965 in Wikipedia wikitext, the Singapore Journal of Legal Studies and the NUS guide. About 29 cite Legislative Assembly Debates by volume and column, 7 cite select committee papers ("L.A. 16 of 1960"), about 8 give an Ordinance number alone, 4 cite a bill by number, and 2 cite a Gazette. For example, Leong Wai Kum, [2008] Sing JLS 1, cites 11 Debates, 3 L.A. papers and 1 Gazette Extraordinary (vol 14 no 51, 2 June 1959). None of the journal or Wikipedia citations read names an archive or call number; those appear only in library guides. So scholars reach bills of those years through the debates, and a bill number before 1961 is almost never cited. Book footnotes (Tan, Woon, Phang), JSTOR and SOAS were not reached.

The one guide that states the route is NUS's Historical Sources of Singapore Law, which says bills of 1946 to 1962 are "found in the Supplement to the government gazette/government gazette supplement" (K7449 S).

### Sources by era

A source is working only if a concrete document was read in it, and a catalogue record only if a record names the item. Terms marked in the table are quoted below it.

**Before 1961: bills, Ordinances and Assembly papers**

| Source | Years and kinds | How a person gets it | Text form | Terms | Test | Verdict |
|---|---|---|---|---|---|---|
| NUS, Supplement to the government gazette, K7449 S | Record: 1947 to 1962. Bills, Ordinances, subsidiary legislation. Stack items listed for 1947 to 1952 only; later years not tested | NUS staff or student, or NUS's rare-materials request form. Closed stacks | Print | None seen | `linc.nus.edu.sg/record=b1758530`: "Includes bills, ordinances and subsidiary legislations" | Catalogue record |
| NLB, Colony of Singapore Government Gazette supplement | 32 items, years printed "19XX" | In person, Lee Kong Chian Reference Library Level 11, closed access, reference only | Print | NLB | Call number 348.5957 SGGCSG, record 12598033 | Catalogue record |
| NLB, digitised Colony of Singapore Government Gazette | Quarterly volumes seen from January 1949 to June 1959; a worker saw April 1946 on. Whether the bill Supplements are inside: not tested | Free in a browser, from `catalogue.nlb.gov.sg` to the Digitised Periodical link. curl gets an empty 202 | Not tested | NLB | Record "Oct.-Dec. 1957", `nlb.gov.sg/main/book-detail?cmsuuid=8346a57c-d0a6-48dd-a1a2-8ae844cde491`; page not opened | Catalogue record |
| Kew, CO 932, Singapore Government Gazettes | 1945 to 1970, 123 volumes. Supplements pieces for 1949 and 1952 to 1962. Bills named only in pieces 77 (1963), 89 (1965) and 98 (1966); whether earlier "Supplements" hold bills: not tested | Kew reading room, free. Paid copy starts with a £9.92 page check, about 29 working days | Print; a copy is an image | Not read | Discovery API: CO 932/42 "1955 July - December : Supplement"; CO 932/54 shows digitised false | Catalogue record |
| NUS Digital Gems, Colony of Singapore Ordinances, K7399 Ord | Record b1756303 lists 1947 to 1959 and 1962. Ordinances as passed, with Ordinance numbers, not bill numbers | Free to read in a browser | Not tested; not downloaded | Digital Gems | `digitalgems.nus.edu.sg/view/340913` (1956), item page: Open Access | Working for reading; automated use barred |
| Kew and NUS, CO 940, Sessional Papers | 1946 to 1965. Votes and Proceedings 1956 to 1959, Assembly papers | Kew; NUS 71 microfilm reels; NUS PDFs from a 2009 Kew DVD-ROM, NUS login only | Microfilm, image PDF | NUS licence | Discovery pieces; `linc.nus.edu.sg/record=b2663083` | Catalogue record |
| NLB, Legislative Assembly sessional papers and select committee reports | 94 items in the series; Report from the Select Committee on the Labour Bill, 1955 on | In person, reference only | Print | NLB | Record 201903572 | Catalogue record |
| National Archives, Papers Presented to Parliament | NUS's guide says papers from 1955 are being digitised; not tested | Web, behind a copyright gate; a request route was seen in a search snippet only | Not read | NAS | `S.3of1974.pdf` answers the gate page, not the PDF | Blocked by gate |
| Colony annual reports, archive.org | 1955, 1956 and 1957 found. Lists Ordinances with numbers in a Legislation chapter | Open web | OCR | Not read | `singapore-annual-report-1957`: "Forty-seven Ordinances were enacted during 1957", "(Ord. 4/57)" | Working, secondary |
| Malayan Law Journal, archive.org | Volumes to 2005. Quotes Ordinance numbers | Open web | OCR | Not read | `mlj_1963_1`: "the Criminal Law (Temporary Provisions) Ordinance, 1955 (No. 26 of 1955)" | Working, secondary |
| CIA Reading Room copy, archive.org | One Ordinance as passed | Open web | OCR and scan | Not read | `cia-readingroom-document-cia-rdp70-00241r000600020005-4`: "COLONY OF SINGAPORE. No. 25 of 1955" | Working, one document |
| HathiTrust | Laws of the Colony of Singapore, 1955 edition, volumes 1 to 5 and 8 | Search-only. A person searches in a browser, then requests the pages by interlibrary loan | Scan, not shown | Not read | Record 010445989; `uc1.31210021177918`, rights "ic" | Catalogue record |
| Lincoln's Inn Library | "Ordinances 1946 - 1964", guide of June 2026 | In person, London | Print | Not read | `lincolnsinn.org.uk/wp-content/uploads/2026/07/Singapore-Guide.pdf` | Catalogue listing |
| NLB, one printed bill | "A bill intituled: an ordinance to constitute a Housing and Development Board", 1959 | In person, reference only | Print | NLB | Call number 348.01095957 SIN | Catalogue record |

**1961 to 1984: bills, Acts as passed, tables of the laws**

| Source | Years and kinds | How a person gets it | Text form | Terms | Test | Verdict |
|---|---|---|---|---|---|---|
| SSO Bills Supplement, Archive captures | 2,393 distinct numbers, 1961 to 2026 | Web; already on disk | HTML | SSO | `plans/bill-linking-build/bills-supplement-captures/` | Working |
| NLB, digitised Bills Supplement issues | 81 issues of 1965 to 1979 in the 782 search results read. Each record names its bills. A selection, since 1973 alone reached issue 59 and only 12 of that year are listed | Free in a browser. curl gets an empty 202 on the page; the catalogue JSON the site calls answers | Not tested | NLB | "Bills Supplement, n.2. 8-Mar-72", cmsuuid 6737d078-23e2-467a-a1ac-14f57ddbe55b. Another reads "informs of the introduction of the Income Tax (Amendment) Act, the National Registration Act, and the Destitute Persons Act" | Catalogue record |
| NLB and NUS, Bills Supplement in print | 1963 on | NLB 348.5957 SGGBS, in person. NUS K7499 SB, record b1199812, closed stacks | Print | NLB | `linc.nus.edu.sg/record=b1199812` | Catalogue record |
| Kew, CO 932/77, 89 and 98 | 1963, 1965 and 1966 Bills Supplements | As CO 932 above | Print | Not read | Discovery search "Bills" in CO 932 returns these 3 | Catalogue record |
| LawNet | SMU's guide: "Singapore bills are available from 1961" | Subscription | Not tested | Earlier reading: clause 4.2.4 bars downloading to build a search facility; not rechecked | Not tested | Not tested |
| NLB, digitised Acts Supplement issues | 56 issues of 1965 to 1980, a selection | Browser, as above | Not tested | NLB | "Acts supplement, n. 7. 2-Jan-70", cmsuuid 1424347a-1614-4265-bf54-0b3e75a36385 | Catalogue record |
| NLB and NUS, Acts in print | NLB Acts passed during the year, 1960 to 1980, 12 items, 348.595 MLSGGA; NLB Acts Supplement 348.5957 SGGAS. NUS K7399 SA | In person, reference only; NUS closed stacks | Print | NLB | `linc.nus.edu.sg/record=b1191266` | Catalogue record |
| Kew, CO 932 legislative pieces | 76 (1963 Ordinances), 88 (1965 Ordinances), 97 (1966 Acts), 103, 109, 114, 120 (1967 to 1970) | As CO 932 above | Print | Not read | Discovery records | Catalogue record |
| Tables of the written laws | NLB: Tables of the written laws of the Republic of Singapore, 1819 to 1971, with Supplements 1 to 7 (348.5957028 SRI), and 1982 edition (348.5957028 TAB). NUS: Sesquicentennial chronological tables, 1834 to 1984 (K7574 1984). NLB also has 1958 and 1970 chronological tables | In person, reference only; NUS use in library | Print | NLB | NLB catalogue; `linc.nus.edu.sg/record=b1501285`. Contents not read | Catalogue record |
| SSO Revised Edition 1985, Archive captures | 1,447 PDF rows among the first 3,000 URLs | Web | PDF with text | SSO | `/Act-Rev/1/...ViewType=Pdf`: "Interpretation Act (Chapter 1), Act 10 of 1965, Amended by 14 of 1969, Revised Edition 1985" | Working |
| SSO Repealed Acts, Archive captures | 227 to 246 Acts, all repealed in 1985 or later. Stub pages give the original Act number, not a history | Web | HTML | SSO | `plans/bill-linking-build/repealed-acts-count.md`: PIA1957 stub | Working |
| SSO Historical versions, Archive PDFs | Legislative History prints only in PDF captures | Web | PDF | SSO | BA1995 history with Bill 16/94, first reading 25 July 1994 | Working for the few Acts captured |
| CommonLII, AsianLII, WorldLII, Archive captures | Consolidated Acts only: 23, 23 and 1 captured URLs | Web. The live sites answered 403 earlier | HTML, PDF | Not read | AsianLII Land Acquisition Act: "Deleted by Act 38/2002"; no history, no bill number | Working, adds nothing |
| eGazette | From September 1998 | Web | PDF | eGazette | FAQ: "Gazettes published before Sep 1998 are available in print and copies are available in the Lee Kong Chian Reference Library" | Working, nothing before 1998 |

**Services that blocked the check**

| Service | Answer | What a person does |
|---|---|---|
| HathiTrust full-text and catalogue search | Cloudflare 403 | Search in a browser, tick "Full view only" |
| Google Books API | 429, daily quota | Search books.google.com, Full view, 1946 to 1984 |
| WorldCat | 429 | Search worldcat.org in a browser |
| Library of Congress JSON | Cloudflare 403 | loc.gov in a browser. A search summary says it holds the Colony gazette to 2 June 1959 on paper; unconfirmed |
| Center for Research Libraries | 403 | A member library requests a loan; holdings unconfirmed |
| UK Library Hub Discover | 403 | Search in a browser for British Library, Bodleian, Cambridge and SOAS holdings |
| National Library of Australia catalogue | Anubis proof-of-work page, not solved. Trove's API needs a key | Search in a browser |
| IA Scholar | Proof-of-work page | Search in a browser |
| NLB book-detail and BookSG pages | Empty 202 | Open in a browser |
| ScholarBank thesis text, Oxford ORA | 401 login; Cloudflare 403 | NUS login; browser |
| HeinOnline | No public title list reached. A web search found only modern Singapore Constitution records under World Constitutions Illustrated, and no colonial law or gazette collection for Singapore | A library user searches "Straits Settlements" or "Singapore Government Gazette" inside HeinOnline |

Among commercial sets I found no named Adam Matthew, ProQuest, Readex, Brill or IDC gazette set for Singapore. Gale's State Papers Online, Colonial Asia Part III, is an unconfirmed lead. Wikisource holds Malayan Ordinances, not Singapore's. Wikimedia Commons holds one Colony gazette Supplement of 1951, reprinted by the UN (E/NL.1951/43-46), which is subsidiary legislation on drugs.

### Terms that restrict the project

- **NLB**, Terms of Use, Archive copy of 17 December 2025, clause 2.1: "No part or parts hereof may be reproduced, distributed, adapted, modified, republished, displayed, broadcast, hyperlinked, framed or transmitted in any manner or by any means or stored in an information retrieval system without the prior written permission", and "You also may not, without the permission of NLB DIGITAL LIBRARY, insert a hyperlink to this website on any other website". Royce's ruling holds a bill when the project stores its number and a link to its text, so a link to an NLB page needs NLB's permission.
- **NUS Digital Gems**, clause 4.1: users must not "access, download, scrape, crawl, harvest or collect DG Content using automated means". Clause 4.3 says users must not "extract DG Content to create datasets, corpora, or structured collections". Clause 5.1 bars "deriving, storing, or creating any content or databases" from it. Reading by hand is allowed. Building a table of Ordinances from it needs written permission from NUS Libraries.
- **NUS guides**: "Conducting text and data mining without prior approval from NUS Libraries, including the use of artificial intelligence tools, are prohibited."
- **National Archives** gate: "You may download the contents on this website for private research use only. Any other use including for purposes of publication, exhibition, or online use will require written permission."
- **SSO** clause 13(d), from the Archive copy quoted in the 4 November report: automated extraction "must only be carried out during the hours of 3 a.m. to 7 a.m. (Singapore Time)" and not "in an abusive or intrusive, or a deceptive, manner". The harvest route reads the Archive and sends nothing to SSO.
- **eGazette** clause 11 bars automated extraction "in an abusive or intrusive, or a deceptive, manner" and requires the attribution lines in `docs/report/bill-linking-build-2026-11-08.md`. It holds nothing before September 1998.
- **Parliament** clause 6: "To use any parts of the Contents of this Site, the user must seek permission in writing, stating the Contents for use; intent of use; manner of use; time frame of use and identity of the user." Royce ruled on 2 November to wait for a takedown request instead.

## 4. Route per gap, cheapest first

| # | Gap | Route | Cost | Needs |
|---|---|---|---|---|
| 1 | The Act harvest | Look on the machine that ran the 5 November write | A minute | Royce |
| 2 | Test 1's denominator | Count by numbering series, not by year (section 5) | A ruling | Royce |
| 3 | Do NLB's digitised gazettes hold bills? | Open one 1957 volume and one Bills Supplement issue in a browser | Five minutes | A person with a browser |
| 4 | The harvest, if it is gone | Refetch the 523 PDFs from the committed capture list (section 1) | 523 Archive requests, about 70 minutes plus retries | Royce's go; a machine with `pdftotext` |
| 5 | Repealed Acts of 1985 on | Fetch the PDFs of the 12 Acts repealed in 2015 or later from the Archive | About 20 requests, up to about 28 bills | Royce's go; already proposed in the build report |
| 6 | Test 3's remaining bills | One visit to the Lee Kong Chian Reference Library, Level 11, for the Tables of the written laws, 1819 to 1971, the Supplements and the 1982 edition. Photograph the pages; store the numbers and titles only | Half a day, plus typing | A person, in the library |
| 7 | The 20 missing bill numbers | Same visit: Bills Supplement 348.5957 SGGBS for 1963 on. K7449 S at NUS for 1961 and 1962 | Part of the same visit, plus an NUS request | A person, in the library |
| 8 | Bill numbers of 1955 to 1960 | First the digitised gazettes if check 3 passes. Otherwise NLB's Supplement, 32 items, same library | Days of reading, about 12 half-year volumes | A person, in the library |
| 9 | Links to a text on NLB or Digital Gems | Written permission from NLB and NUS Libraries | A letter each; weeks | Royce |
| 10 | Whatever only Kew holds | Paid page check on CO 932/77 first | £9.92 and fees, about 29 working days | Royce; slow |

Items 6, 7, 8 and 10 need a person in a library or a paid order. CO 940 and CO 276 as PDFs need an NUS login. LawNet and HeinOnline need a subscription. I did not check whether the Lee Kong Chian Reference Library needs an NLB card at the desk.

## 5. What would move done tests 1 and 3

### Test 1, bill completeness from 1961

The test divides by the highest number the Bills Supplement prints each year. From 1961 to 1965 the numbers run across years in two series, so that divisor is wrong.

| Series | Dates | Numbers | Held in the listing | Missing |
|---|---|---|---|---|
| A | January 1961 to July 1963 | 124 to 214 | 83 of 91 | 141, 142, 147, 150, 177, 200, 201, 202 |
| B | October 1963 to December 1965 | 1 to 70 | 65 of 70 | 27, 29, 30, 41, 42 |

Numbers 1 to 123 of series A are bills of 1959 and 1960, before the listing starts. I infer that from a Legislative History that prints 17/1959 after 212/1959, and from 1961's lowest number being 124. Annual numbering starts in 1966.

So the test as written has a divisor of 2,925 (2,393 held plus 532 "missing"), of which 507 never existed in those years. By series the divisor is 2,418, and 20 numbers stay unfound after the eGazette fills the five of 2024 and 2025: 13 from 1961 to 1965 and 7 from 1966 to 1996 (1966: 16, 22, 27, 39; 1975: 44; 1990: 22; 1996: 24). That is a ceiling of 99.2% without a library visit, and the test also needs each number to have a `Bill` row, so the measured figure will be lower. Some of the 20 may be numbers never used. None has an Archive capture.

### Test 3, outcome resolved

These are arithmetic on the 6 November figures, which I could not recheck. Of 2,682 passed bills, 2,019 are linked (75.3%). The eGazette Acts add up to 65 (77.7%). The supply and repeal classes add at most 173 (84.2%), and fewer if some of those bills are already linked. The target of 95% is 2,548 bills, so about 291 more must resolve.

The Acts that no current Legislative History lists are mostly repealed or spent, so a current Act's history can never reach them. A repealed Act's own history exists only for Acts repealed around 2015 or later (15 to 35 bills, from the build report). The printed tables of the written laws are the route with enough reach, if they list each law from 1819 with its number, year and fate as their titles suggest. I have not seen a page of them. It also needs Royce's ruling that an Act number from a table counts as "linked to an Act", since `act` holds only the 523 current Acts today.

## 6. Corrections to earlier reports

- `docs/report/archived-bills-sources-2026-11-08.md` says "Only part of it appears (for example 31 rows for 1961, numbers up to 158)" and its table says "partial (31 of 158 in 1961)". The listing is nearly complete for 1961 to 1965: 148 of 161 numbers.
- The same report says "No free source online was found" before 1961. Digital Gems marks the 1956 Ordinances Open Access, and NLB's digitised gazettes are listed. I still read no bill text from before 1961 online.
- `docs/vision.md` says "Bills before 1961 and Acts as passed before 1985 have no free original text online". That is now unproven in both halves and should change once check 3 is done. I left the file alone.
- The CommonLII and AsianLII 403s lost nothing. Their captured Singapore legislation is consolidated text with no history or bill number.

## 7. Requests and conduct

The run sent 325 requests to 46 hosts, logged in `plans/bill-sources-investigation/requests.log`, and none to sso.agc.gov.sg. All went through one pacer with a named user agent, 8 s apart for web.archive.org and 2 s for other hosts, except 2 Archive requests that tested the refetch script. Workers' web searches are not in that log.

| Host | Requests |
|---|---|
| web.archive.org | 67 |
| archive.org | 46 |
| www.sgparliament.com | 36 |
| sg-prod.iiivega.com (NLB's catalogue) | 31 |
| discovery.nationalarchives.gov.uk | 30 |
| libguides.nus.edu.sg | 14 |
| en.wikipedia.org | 8 |
| linc.nus.edu.sg | 7 |
| digitalgems.nus.edu.sg | 7 |
| 37 other hosts, 1 to 5 each | 79 |

Answers were 270 OK, 14 of 503, 11 of 403, 7 of 404, 7 empty 202s, 6 of 504, 6 with no connection, 2 of 429, 1 of 401 and 1 of 500. The first index run stopped at its 25-minute limit after letter R, and I reran letters S to W with more retries. I set the verdict column in section 3 myself from the stored responses, because those claims decide where money or a library visit goes.

These went against the limits or the terms, and each has stopped:

- The sgparliament worker sent 12 requests to `/api/`, which `robots.txt` disallows, before it read `robots.txt`.
- Workers sent 7 requests to Digital Gems, 2 of them for its terms and the rest for list and item pages, by a script. Clause 4.1 bars automated access. No document was downloaded, and I made no further requests there.
- Workers read 14 NUS guide pages, which carry the text-mining sentence quoted above. I read the guide's call numbers from those stored pages and made no further requests.

## 8. Questions for Royce

1. **Is `plans/bill-debate-linking/harvest/` still on the machine that ran the 5 November write?** Recommendation: check with the command in section 1 before anything else.
2. **If it is gone, run the refetch?** It is 523 Archive requests over about 70 minutes, none to SSO, on a machine with `pdftotext`. Recommendation: **Do**, only if question 1 comes back empty.
3. **Change done test 1 to count numbers within each series, and report 1961 to 1965 by series?** Recommendation: **Do**. As written it cannot pass.
4. **Can an Act number from a printed table count as "linked to an Act" for test 3?** It needs a new source class and a place to store a law that is not in `act`. Recommendation: **Do**, stored as printed with the book and page, and reported apart from links to a current Act.
5. **Will you or someone open two NLB pages in a browser?** The links are the Oct.-Dec. 1957 gazette and Bills Supplement n.2 of 8 March 1972 in section 3. It settles whether routes 7 and 8 need a library. Recommendation: **Do** first, five minutes.
6. **Will someone visit the Lee Kong Chian Reference Library, Level 11?** One trip covers the tables, the 20 numbers and a first look at the 1955 to 1960 Supplement. Recommendation: **Do** after question 5, and photograph pages for facts only, since the project would store numbers and titles.
7. **For a bill that exists only in print, what counts as held?** Your ruling needs a link to the text. Recommendation: accept a citation to volume, Supplement number and page in place of a link, for 1955 to 1960 only.
8. **Write to NLB and NUS Libraries for permission?** NLB's clause 2.1 bars hyperlinks and storage without it, and Digital Gems bars building a table. Recommendation: **Do** for NLB, asking about links and its catalogue metadata together. **Hold** NUS until question 7 is settled.
9. **Order a Kew page check on CO 932/77?** Recommendation: **Hold**. Kew is the slowest route, and NLB and NUS both list the Bills Supplement from 1963 in Singapore.
10. **Correct the sentence in `docs/vision.md` about free text before 1961?** Recommendation: **Do** after question 5, with what the browser check shows.

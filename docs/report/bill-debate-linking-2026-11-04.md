# Bill and legislation linking feasibility, 4 November 2026

This study asks whether the project can link bills and Acts to the Hansard debates on them, and host Singapore's current laws beside the debates. Royce has not adopted the goal, so `docs/vision.md` is unchanged. The 72 per-bill records are in [bill-debate-linking-2026-11-04.json](bill-debate-linking-2026-11-04.json).

In short, bills can be linked to their debates now, from our own reports and with no outside source. A title and date rule reproduced the hand-built links for 72 of 72 sampled bills. Acts can be linked through the Legislative History that SSO prints at the end of each Act, which gives each amending Act's bill number and reading dates back to 1955, but harvesting it at scale means fetching SSO inside its 03:00 to 07:00 window, which nobody has tried. Hosting the text of current law is allowed by SSO's terms on four conditions, and AGC can withdraw that permission without notice. I recommend adopting the first stage, running a small SSO trial before committing to the second, and linking out to SSO rather than hosting text in the third.

## The question

The database holds 5,244 `bill` reports from 1955 and 595 `bill-intro` reports from 2010. Hansard prints no bill text. Royce asked whether the project can do three things, in this order.

1. Link each bill to the Hansard debates on it, from first reading through any select committee and the committee stage to third reading.
2. Link legislation to those debates. That means each Act as passed, including an amendment Act whose text has since been folded into a principal Act.
3. Host a copy of Singapore's current laws beside the debates.

For each sampled bill the workers looked for the bill as introduced and the Act as passed, free to read online in full, and opened each copy to check it is that bill. A title-only listing does not count. A later Revised Edition does not count as the original either, and goes under current law instead. Votes are out of scope.

## How the sample was drawn

The sample is one passed bill per year from 1955 to 2026, so 72 bills. The frame is the 2,673 `bill` reports that hold a procedural third-reading line. `plans/bill-debate-linking/sample.py` finds the line with a regular expression for "read a Third time" or "read the Third time" after the word Bill, which also catches the 1955 and 1956 lines that lack "and passed". It drops lines containing "be now read", which is the motion rather than its result, and lines opening with I, Now, Sir or Mr. In each year it takes the report with the lowest `md5(id || seed)`, seed `bill-debate-feasibility-2026-11-04`. The smallest year in the frame has 10 reports (1985) and the largest has 77 (1960).

The frame matches an independent count. Clustering every `bill` report by title gives 2,675 passed bills, 2 more than the frame's 2,673.

The frame leaves out three groups.

- Bills passed outside a `bill` report. Of the 14 reports of other types that hold a third-reading line, 4 are Budget reports of 1955 to 1958 carrying the Appropriation Bill, 8 are motion reports (some of them bills misfiled on 16 October 2003) and 2 are oral-answer reports of 27 April 2010. A few of the 14 are not bills at all.
- Bills that never passed. About 117 of 2,792 title clusters have no third-reading line, because the bill lapsed, was withdrawn or is still before Parliament.
- Proportion. Each year counts once whatever its frame size, so a 1985 bill stands for 10 frame reports and a 1960 bill for 77. The counts below describe years, not the population of bills.

## How the records were checked

Sonnet workers wrote the 72 records. A skeptic then re-checked 121 claims across 64 of the 72 years. It confirmed 110, corrected 11 and refuted none. Nine of its 11 corrections moved a text from found to blocked because the archive copy stopped partway or dropped the Schedule. They are the bills of 1969, 1972, 1977, 1984, 1989 and 1993, and the Acts of 1989, 1993 and 2008. It moved the 1957 bill from blocked to not found, and marked report 49083, the 2025 assent list, as matched by date alone. Every Internet Archive copy of SSO leaves out the Explanatory Statement, so the skeptic counted a copy as full when every numbered provision and Schedule in its table of contents appears in the body.

I made these checks before writing.

1. I read back all 218 report ids the records cite. 218 of 218 exist with the cited type and date, and 3 of the 218 titles differ in wording only.
2. I ran an automatic title and date rule over the 72 sampled third-reading reports (method under "Can bills be linked to debates"). It returned the hand-built set of `bill` and `bill-intro` reports for 72 of 72 bills.
3. 2007. Both texts were marked blocked because the SSO archive copies are partial. The eGazette PDFs of Bill 13/2007 (13 pages) and Act 26 of 2007 (10 pages) hold the whole of both, Schedules included. I corrected both to found.
4. 2019 and 2023. Both Acts were marked blocked for the same reason. I found Act 21 of 2019 in file 31 of the 2019 Acts Supplement (41 pages, to section 52) and Act 18 of 2023 in file 24 of the 2023 Acts Supplement (86 pages, to section 45), each saying it was passed on the Hansard third-reading date. I corrected both to found.
5. 1974 and 1976 share a title, Criminal Law (Temporary Provisions) (Amendment) Bill. The database confirms both sets of debate links (report 35250 for 1974, reports 35074, 35038 and 34889 for 1976). The 1974 record said SSO's history does not list the 1974 Act. An Internet Archive copy of the principal Act's PDF lists it as item 16, Act 15 of 1974, Bill No. 19/1974, all three readings on 28 August 1974. I corrected the record and set its Act number.
6. 2025. The Act PDF prints Bill No. 11/2025, "passed by Parliament on 15 October 2025" and "No. 20 of 2025", as the record says. Report 49083 has no content and 0 speech rows, so its link rests on date alone.
7. 2026. Report 49634 (3 February) opens "Order for Second Reading read". Report 49579 (4 February) opens "Resumption of Debate on Question [3 February 2026]" and holds the end of the second reading at row 256 and the third reading at row 259. One debate, two reports, as the record says.
8. 2006. The database has four MONEYLENDERS (AMENDMENT) BILL reports, two for a 2005 bill (23829, 43156) and two for the sampled 2006 bill (23536, 23461). The record pairs them correctly. The 2006 first-reading row is stored as mojibake, with broken characters in place of its opening quotation mark.
9. 1988. I re-read the archive copy of Act 10 of 1988 without relying on the skeptic. It prints "passed by Parliament on 18th May 1988", the Hansard third-reading date, and holds sections 1 to 26 and the re-enacted Second Schedule.
10. I re-read the SSO Terms of Use from an Internet Archive copy, and the eGazette and Parliament terms live, for the quotes in the hosting section.

I applied my corrections to the JSON only, each with a note in the field starting "Judge:". The records under `plans/` are unchanged. Besides checks 3 to 5, I changed 1978, 1982 and 1986 from "history does not list this Act" to unknown, for the reason given under "Can legislation be linked to debates". Before my corrections the sample had 51 of 72 bills and 31 of 72 Acts read in full. After them it has 52 of 72 and 34 of 72.

Royce's rule for this study is no request of any kind to sso.agc.gov.sg, and every SSO page in the per-bill records and in this report's quotes comes from the Internet Archive. Before he set the rule, though, the hosting worker fetched two SSO pages live at 09:30 to 10:30 SGT (the Terms of Use and the Misuse of Drugs Act 1973), and workers in the first three batches sent live requests that SSO answered with an AWS WAF challenge (HTTP 202 and an empty body). The hosting worker's finding on the amendment timeline rests on that live Misuse of Drugs Act page.

## All 72 bills

Bill and Act text cells read as follows. "Full" means read in full from the eGazette or parliament.gov.sg. "Full (IA)" means read in full from an Internet Archive copy of SSO. "On SSO, IA partial" means the SSO page exists and its header matches the bill, but every archive copy stops partway or drops the Schedule. "Not found" means no free full copy turned up in any source. In the law column "(IA)" marks a status that rests on an archive copy of SSO. The reports column gives the number of distinct reports, then the stages in each as the workers labelled them. A report labelled 2R often also holds the committee stage and third reading. "assent" is an Assent to Bills Passed list, SC a select committee report, M a later mention and O another related report such as a business motion, an appendix or a written correction.

| Year | Hansard title | Bill no. | Debate reports found | Bill text online | Act text online | Current law |
|---|---|---|---|---|---|---|
| 1955 | Undesirable Publications (Amendment) Bill | 15/1955 | 4: 1R, 2R, C, assent | Not found | Not found | Repealed |
| 1956 | Silver Jubilee Fund (Singapore) (Amendment) Bill | not found | 3: 1R, 2R, assent | Not found | Not found | Repealed (IA) |
| 1957 | Raffles Museum Bill | not found | 3: 1R, 2R+C+3R, assent | Not found | Not found | Unknown |
| 1958 | Hospitals Board (Amendment) Bill | not found | 2: 1R, 2R+C+3R | Not found | Not found | Repealed |
| 1959 | Laws of Singapore (Miscellaneous Amendments) Bill | 215/1959 | 3: 1R, 2R, assent | Not found | Not found | Spent |
| 1960 | Hospitals Board (Repeal) Bill | not found | 3: 1R, 2R, assent | Not found | Not found | Repealed (IA) |
| 1961 | Police Force (Amendment) Bill | 133/1961 | 3: 1R, 2R+C+3R, assent | Full (IA) | Not found | Folded |
| 1962 | Criminal Procedure Code (Amendment) Bill | 157/1961 | 2: 1R, 2R+C+3R | Full (IA) | Not found | Folded |
| 1963 | People's Association (Amendment) Bill | 17/1963 | 2: 1R, 2R | Full (IA) | Not found | Folded |
| 1964 | Entertainments Duty (Amendment) Bill | 22/1964 | 4: 1R, 2R, M, assent | Full (IA) | Not found | Repealed (IA) |
| 1965 | Probate and Administration (Amendment) Bill | 48/1965 | 4: 1R, O, 2R+C+3R, assent | Full (IA) | Not found | Folded |
| 1966 | Revised Edition of the Laws Bill | 2/1966 | 2: 1R, 2R+C+3R | Full (IA) | Not found | Repealed (IA) |
| 1967 | Rubber Association of Singapore (Incorporation) Bill | 22/1967 | 3: 1R, 2R, assent | On SSO, IA partial | Not found | Repealed |
| 1968 | Public Utilities (Amendment) Bill | 46/1968 | 3: 1R, 2R, assent | Full (IA) | Not found | Repealed (IA) |
| 1969 | Drugs (Prevention of Misuse) Bill | 7/1969 | 3: 1R, 2R+C+3R, assent | On SSO, IA partial | Not found | Repealed |
| 1970 | Banking Bill | 29/1970 | 2: 1R, 2R+C+3R | On SSO, IA partial | Not found | In force (IA) |
| 1971 | Parliamentary Membership Bill | 14/1971 | 4: 1R, O, 2R, assent | Full (IA) | Not found | Unknown |
| 1972 | Development Loan Bill | 15/1972 | 3: 1R, 2R, assent | On SSO, IA partial | Not found | Unknown (IA) |
| 1973 | Destruction of Disease-Bearing Insects (Amendment) Bill | 25/1973 | 3: 1R, 2R+C+3R, assent | Full (IA) | Not found | Repealed |
| 1974 | Criminal Law (Temporary Provisions) (Amendment) Bill | 19/1974 | 1: 1R+2R+C+3R | Full (IA) | Not found | Folded (IA) |
| 1975 | Companies (Amendment No. 2) Bill | 56/1975 | 3: 1R, 2R, assent | Full (IA) | Not found | Folded |
| 1976 | Criminal Law (Temporary Provisions) (Amendment) Bill | 36/1975 | 4: 1R, 2R, 3R, assent | Full (IA) | Not found | Folded (IA) |
| 1977 | Singapore Labour Foundation Bill | 10/1977 | 3: 1R, 2R+C+3R, assent | On SSO, IA partial | Not found | In force |
| 1978 | Jurong Town Corporation (Amendment) Bill | 6/1978 | 2: 1R, 2R+C+3R | Full (IA) | Not found | Folded (IA) |
| 1979 | Legal Profession (Amendment) Bill | 6/1979 | 3: 1R, 2R, assent | Full (IA) | Not found | Folded (IA) |
| 1980 | Supplementary Supply (No. 2) Bill | 16/1980 | 4: 1R, O, 2R, assent | Full (IA) | Not found | Unknown |
| 1981 | Prevention of Pollution of the Sea (Amendment) Bill | 16/1981 | 4: 1R, 2R+C+3R, O, assent | Full (IA) | Not found | Folded |
| 1982 | Societies (Amendment) Bill | 7/1982 | 2: 1R, 2R+C+3R | Full (IA) | Not found | Folded (IA) |
| 1983 | Statutes (Miscellaneous Amendments) Bill | 25/1982 | 2: 1R, 2R | On SSO, IA partial | Not found | Spent |
| 1984 | Construction Industry Development Board Bill | 17/1983 | 3: 1R, 2R, assent | On SSO, IA partial | Not found | Repealed (IA) |
| 1985 | Income Tax (Amendment) Bill | 10/1985 | 3: 1R, 2R+C+3R, assent | Full (IA) | Full (IA) | Folded |
| 1986 | Pensions (Amendment) Bill | 17/1986 | 2: 1R, 2R+C+3R | Full (IA) | Full (IA) | Folded (IA) |
| 1987 | Supply Bill | 4/1987 | 3: 1R, O, 2R | On SSO, IA partial | On SSO, IA partial | Spent |
| 1988 | Parliamentary Elections (Amendment) Bill | 23/1987 | 7: 1R, 2R, O, 2R, SC, 3R, assent | Full (IA) | Full (IA) | Folded (IA) |
| 1989 | Supply Bill | 17/1989 | 4: 1R, O, 2R+3R, assent | On SSO, IA partial | On SSO, IA partial | Spent |
| 1990 | National Parks Bill | 12/1990 | 2: 1R, 2R+C+3R | On SSO, IA partial | On SSO, IA partial | Repealed (IA) |
| 1991 | Nanyang Technological University Bill | 8/1991 | 3: 1R, 2R, assent | On SSO, IA partial | On SSO, IA partial | Repealed (IA) |
| 1992 | Criminal Procedure Code (Amendment) Bill | 12/1992 | 3: 1R, 2R, assent | Full (IA) | Full (IA) | Repealed (IA) |
| 1993 | Smoking (Control of Advertisements and Sale of Tobacco) Bill | 3/1993 | 3: 1R, 2R+C+3R, assent | On SSO, IA partial | On SSO, IA partial | In force |
| 1994 | Singapore Armed Forces (Amendment No. 2) Bill | 22/1994 | 4: 1R, 3R, O, assent | Full (IA) | Full (IA) | Folded (IA) |
| 1995 | Supply Bill | 12/1995 | 3: 1R, O, 2R | On SSO, IA partial | On SSO, IA partial | Spent |
| 1996 | Road Traffic (Amendment) Bill | 3/1996 | 3: 1R, 2R, assent | Full (IA) | Full (IA) | Folded (IA) |
| 1997 | Customs (Amendment) Bill | 10/1997 | 3: 1R, 2R+C+3R, assent | Full (IA) | Full (IA) | Folded |
| 1998 | Constitution of the Republic of Singapore (Amendment) Bill | 9/1998 | 3: 1R, 3R, assent | Full (IA) | Full (IA) | Folded (IA) |
| 1999 | Road Traffic (Amendment) Bill | 35/1999 | 3: 1R, 2R, assent | Full (IA) | Full (IA) | Folded (IA) |
| 2000 | Singapore Management University Bill | 8/2000 | 3: 1R, 2R, assent | Full | Full | In force (IA) |
| 2001 | Official Secrets (Amendment) Bill | 26/2001 | 3: 1R, 2R+C+3R, assent | Full | Full | Folded |
| 2002 | Newspaper and Printing Presses (Amendment) Bill | 20/2002 | 4: 1R, 3R, O, assent | Full (IA) | Full (IA) | Folded (IA) |
| 2003 | Road Traffic (Amendment No. 2) Bill | 45/2002 | 2: 1R, 2R | Full (IA) | Full (IA) | Folded (IA) |
| 2004 | Electronic Transactions (Amendment) Bill | 49/2004 | 3: 1R, 2R, assent | Full | Full | Repealed (IA) |
| 2005 | Parking Places (Amendment) Bill | 66/2004 | 3: 1R, 2R+C+3R, assent | Full | Full | Folded |
| 2006 | Moneylenders (Amendment) Bill | 12/2006 | 2: 1R, 3R | Full (IA) | Full (IA) | Repealed (IA) |
| 2007 | Environmental Pollution Control (Amendment) Bill | 13/2007 | 3: 1R, 2R, assent | Full | Full | Folded (IA) |
| 2008 | Limited Partnerships Bill | 35/2008 | 3: 1R, 2R, assent | Full | On SSO, IA partial | In force (IA) |
| 2009 | Civil Aviation Authority of Singapore Bill | 10/2009 | 3: 1R, 2R+C+3R, assent | Full | Full | In force |
| 2010 | Economic Expansion Incentives (Relief from Income Tax) (Amendment) Bill | 28/2010 | 2: 1R, 3R | Full (IA) | Full (IA) | Folded (IA) |
| 2011 | Income Tax (Amendment) Bill | 14/2011 | 4: 1R, O, 2R, assent | Full (IA) | Full (IA) | Folded (IA) |
| 2012 | Land Transport Authority of Singapore (Amendment) Bill | 15/2012 | 5: 1R, 2R, 2R, 2R, C | Full | Full | Folded (IA) |
| 2013 | Terrorism (Suppression of Financing) (Amendment) Bill | 11/2013 | 3: 1R, 2R+C+3R, assent | Full | Full | Folded |
| 2014 | Government Procurement (Amendment) Bill | 23/2013 | 2: 1R, 3R | Full (IA) | Full (IA) | Folded (IA) |
| 2015 | Land Acquisition (Amendment) Bill | 7/2015 | 2: 1R, 2R | Full (IA) | Full (IA) | Folded (IA) |
| 2016 | Bretton Woods Agreements (Amendment) Bill | 18/2016 | 4: 1R, 2R, M, M | Full | Full | Folded (IA) |
| 2017 | Registered Designs (Amendment) Bill | 23/2017 | 3: 1R, 2R+C+3R, assent | Full | Full | Folded |
| 2018 | Goods and Services Tax (Amendment) Bill | 46/2018 | 2: 1R, 3R | Full (IA) | Full (IA) | Folded (IA) |
| 2019 | Home Team Science and Technology Agency Bill | 15/2019 | 2: 1R, 2R | Full | Full | In force |
| 2020 | Apostille Bill | 35/2020 | 2: 1R, 2R | Full | Full | In force (IA) |
| 2021 | Energy (Resilience Measures and Miscellaneous Amendments) Bill | 34/2021 | 4: 1R, 2R+C+3R, M, assent | Full | Full | Folded |
| 2022 | Stamp Duties (Amendment) Bill | 13/2022 | 4: 1R, 3R, O, M | Full (IA) | Full (IA) | Folded (IA) |
| 2023 | Family Justice Reform Bill | 15/2023 | 3: 1R, 2R, 3R | Full | Full | In force |
| 2024 | ACRA (Registry and Regulatory Enhancements) Bill | 17/2024 | 3: 1R, 2R, M | Full | Full | Folded (IA) |
| 2025 | Electronic Conveyancing and Other Matters Bill | 11/2025 | 3: 1R, 2R+C+3R, assent | Full | Full | Unknown |
| 2026 | Land Transport and Related Matters Bill | 1/2026 | 5: 1R, 2R, 3R, O, O | Listed on SSO, no IA copy | Not found | Unknown |

## Coverage by era

The era boundaries follow the sources. SSO's Bills Supplement starts in 1961. Its Acts Supplement holds only Act 27 of 1980 and Act 15 of 1981 before it resumes in 1985, the year of the Revised Edition. The eGazette serves Bills and Acts Supplement PDFs from about 1999 and answers 403 for earlier years. "Read in full or on SSO" adds the texts that SSO holds but this study could read only in part, because the archive copy is partial or, for Bill 1 of 2026, missing. "(IA)" counts the texts read from an Internet Archive copy.

| Era | Bills | Bill read in full | Bill read in full or on SSO | Act read in full | Act read in full or on SSO |
|---|---|---|---|---|---|
| 1955 to 1960 | 6 | 0 of 6 | 0 of 6 | 0 of 6 | 0 of 6 |
| 1961 to 1984 | 24 | 17 of 24 (17 IA) | 24 of 24 | 0 of 24 | 0 of 24 |
| 1985 to 1999 | 15 | 9 of 15 (9 IA) | 15 of 15 | 9 of 15 (9 IA) | 15 of 15 |
| 2000 to 2026 | 27 | 26 of 27 (9 IA) | 27 of 27 | 25 of 27 (9 IA) | 26 of 27 |
| All | 72 | 52 of 72 (35 IA) | 66 of 72 | 34 of 72 (18 IA) | 41 of 72 |

Current law, by the same eras:

| Era | Folded into a principal Act | In force as its own Act | Repealed | Spent | Unknown |
|---|---|---|---|---|---|
| 1955 to 1960 | 0 of 6 | 0 of 6 | 4 of 6 | 1 of 6 | 1 of 6 |
| 1961 to 1984 | 11 of 24 | 2 of 24 | 7 of 24 | 1 of 24 | 3 of 24 |
| 1985 to 1999 | 8 of 15 | 1 of 15 | 3 of 15 | 3 of 15 | 0 of 15 |
| 2000 to 2026 | 17 of 27 | 6 of 27 | 2 of 27 | 0 of 27 | 2 of 27 |
| All | 36 of 72 | 9 of 72 | 16 of 72 | 5 of 72 | 6 of 72 |

What the eras show:

- Before 1961 nothing is online. No free copy of any of the 6 bills or Ordinances turned up in SSO, the eGazette, the National Archives, BookSG, Google Books or a web search.
- From 1961 to 1984 the bill is on SSO in 24 of 24 years, and this study read 17 in full. The other 7 are partial archive copies that a live fetch inside SSO's window would probably settle. The Act as passed is online in 0 of 24 years, so for these years the only text of the Act is a later Revised Edition.
- From 1985 to 1999 SSO holds both texts in 15 of 15 years, but only through archive copies, and 6 of 15 are partial in both. Supply Bills (1987, 1989, 1995) lose their Schedule, the list of expenditure heads, in every capture.
- From 2000 the eGazette and parliament.gov.sg give the original PDFs without going through SSO. 25 of 27 years have both texts in full. The gaps are the 2008 Act, whose eGazette issue answers 403, and the 2026 bill and Act, too new for an archive copy.

## Can bills be linked to debates

Yes. The keys are the bill's normalised title and the sitting date, and the mechanism follows from how Hansard files a bill. Before 2010 a bill is usually two `bill` reports, a one-row first-reading report and a report holding the second reading, committee stage and third reading. From 2010 the first reading moves to a `bill-intro` report. Grouping reports by normalised title (lower case, letters and digits only) and closing each group at a third-reading line puts each bill's reports together, and the closing line keeps a later bill with the same title in a group of its own.

I tested that rule on the sample. For each of the 72 sampled third-reading reports, the query took every `bill` and `bill-intro` report with the same normalised title in the 730 days up to it, after the last earlier same-title report holding a third-reading line. It returned exactly the hand-built set for 72 of 72 bills. The workers found most of those reports by title search themselves, so the test shows the rule matches careful title work; it cannot see a report whose title drifted.

The corpus-wide figures from `corpus-keys.md` set the expected accuracy. 579 of 595 `bill-intro` titles (97.3%) exactly match a later `bill` report, and 9 more match once punctuation or a typo is allowed. 74 of 595 (12%) have two or more same-title bills within two years, which the closing third-reading line resolves. In the older system, 50 first-reading stubs and 76 debate groups (about 3% each) have no same-title partner, and 28 of those 50 stubs match a debate at a similarity ratio of 0.85 or more. 54 of 5,244 `bill` reports (1.0%) show some sign of holding more than one bill. An automated matcher should therefore link about 97% of bills on exact normalised title and date. Most of the remaining 3% link by fuzzy title, and they need a review queue. The 1% of multi-bill reports needs a many-to-many link.

Hansard does not print the bill number. Among the 72 bills only the 1988 select committee motion prints one ("Bill No. 23/87"), and across the corpus "Bill No." followed by a number appears in 21 of about 255,000 bill and bill-intro speech rows, all passing references. The study found the bill number from outside sources for 68 of 72 bills, all but 1956, 1957, 1958 and 1960. Outside sources also give dates to check the match against. The SSO bill page prints "Read the first time on", the Act prints "passed by Parliament on", the Act PDF from about 2016 also reprints the bill number and first-reading date, and the Legislative History gives every reading date. Each of the 66 records from 1961 on cites at least one such date. The dates can be a day out. parliament.gov.sg gives 14 October 2025 for the 2025 bill, which Hansard and the Act show passing on 15 October, and an MHA release gives 5 February 2026 for the 2026 bill against Hansard's 4 February, probably a sitting that ran past midnight. A matcher should allow one day either way.

What breaks a title and date matcher, from the sample:

- Recurring titles. Supply, Income Tax (Amendment) and Constitution amendment bills come back every year, and 12 of 72 records rate their links medium confidence, mostly for this reason. In 2006 an identical Moneylenders (Amendment) Bill passed four months earlier, so the rule pairs the 2006 first reading correctly only because the 2005 bill's third-reading line closes its group first.
- Title drift. The 1998 first-reading title has no space in "(AMENDMENT)BILL", which normalisation absorbs. The 1960 bill was debated as the Hospitals Board (Repeal) Bill and became the Government Hospitals Ordinance. In 1999 and 2003 the bill's title differs from the Act's.
- Near-identical titles. The 2026 Land Transport and Related Matters Bill has a September 2026 sequel, the "(No 2) Bill". A normaliser that drops "(No 2)" merges two bills.
- Split debates. The 1988 and 2026 second readings each run over two sittings in separate reports, and the 2012 debate sits in four same-title reports.
- Bills that cross a year. 8 of 72 bills were introduced in the year before they passed. The 1976 bill spent 339 days in a select committee, inside the 366-day gap the corpus rule allows.
- Related reports the title rule never returns. 51 of 72 records also cite an assent list, a select committee motion, a business motion, an appendix or a written correction, found by phrase search or by date. 45 of 72 cite an assent list, and 4 of those 45 (2013, 2017, 2021, 2025) have no stored text, because SPRS returns newer-system assent lists empty, so they link by date alone.
- Stored text faults. The 2006 first-reading row is mojibake, so a key read from its text needs the character repair first.

## Can legislation be linked to debates

Yes, through the Legislative History section at the end of each Act on SSO, which the Law Revision Commission compiles. Each entry gives the amending law's number and title, its bill number and its reading dates. I read it in an Internet Archive copy of the Criminal Law (Temporary Provisions) Act PDF (https://web.archive.org/web/20240811173604id_/https://sso.agc.gov.sg/Act/CLTPA1955/Historical/20181008?DocDate=20180404&ValidDate=20181008&ViewType=Pdf&_=20240705172342). It starts at Ordinance 26 of 1955, first reading 18 August 1955, and runs through Ordinance 25 of 1958 (Bill No. 165/1958) to Act 15 of 1974 (Bill No. 19/1974) and Act 12 of 1976 (Bill 36/1975, with its select committee report). Workers read the section itself for four records (1976, 1979, 2011, 2016) and saw it in search snippets for more.

The join runs from a Legislative History entry, by bill number and first-reading date, to the bill group from the first stage. The page an entry sits on is the principal Act's, so an amendment Act folded into a principal Act links to it through that entry, and the principal Act's current text is the law as it stands. An omnibus bill such as the Statutes (Miscellaneous Amendments) Bill (1959 and 1983 in the sample) appears in the history of every Act it amends, so one debate links to many Acts.

In the sample, a source shows the principal Act's history listing the sampled Act for 39 of 72 bills and not listing it for 2 of 72 (1962 and 1966). The other 31 are unknown, mostly because the Act is a principal Act itself or the history was never opened.

Two traps came out of the checks.

- SSO's Act page has two histories, and only one reaches back before 1985. The amendment timeline, whose links carry each amending Act's number and commencement date, starts at the 1985 Revised Edition (30 March 1987). The Legislative History reaches back to 1955, but the HTML page fills it in with a later script call, so archive copies of the page rarely hold it, while the PDF view prints it. Workers who read only the timeline marked pre-1985 amending Acts as not listed. That was wrong for 1974, so I changed 1974 to listed and 1978, 1982 and 1986 to unknown.
- The Legislative History can disagree with Hansard. For Ordinance 26 of 1955 it gives 22 September 1955 as the date of the second and third readings. Hansard has the second reading ending that day (report 41600) and the committee stage and third reading on 12 October 1955 (report 41633), which the history gives as the commencement date. I checked this one entry outside the sample and no others. A matcher should join on bill number and first-reading date and flag, not reject, a third-reading date that disagrees.

Before 1985 the route still works where the law survives, since a surviving Act's history covers its amending Ordinances back to 1955. That gives a current SSO page for 13 of the 30 sampled bills from 1955 to 1984 (11 folded into a principal Act, 2 in force as their own Act). The other 17 of 30 amend or create a law that was repealed, spent or not identified. SSO keeps pages for some repealed Acts (the Government Hospitals Act, repealed in 2005, has one), but a law repealed before the 1985 Revised Edition has none. For those bills the first-reading text names the amended Ordinance, often with its chapter or its number and year ("Customs Ordinance, 1960 (No. 44 of 1960)"), which links the debate to the law's name with no page to point at. No Act as passed before 1985 is online (0 of 30).

From 2000 a second route needs no SSO request. The eGazette Acts Supplement PDF prints "passed by Parliament on" with the Hansard third-reading date, and from about 2016 the bill number and first-reading date. A harvester has to open each file, because the eGazette numbers files by supplement issue. The Bills Supplement file number equalled the bill number for 13 of 13 sampled bills, but the Acts Supplement file number equalled the Act number for only 3 of 16 sampled Acts. Some issues answer 403, such as the 2008 issues 36 to 44 and the 2009 issues 1 to 8 that the 2008 worker tried.

## Can current laws be hosted

SSO's terms allow it, under a permission AGC can withdraw at any time. The terms are at https://sso.agc.gov.sg/Terms-of-Use. I read them from the Internet Archive copy at https://web.archive.org/web/20260107190212/https://sso.agc.gov.sg/Terms-of-Use (page dated "Last updated 8 Jan 2026"), and the hosting worker's live reading of 4 November 2026 gives the same clauses.

- Clause 5 is the default bar. Except under clause 13, the contents "shall not be used, reproduced, republished, uploaded, posted, transmitted or otherwise distributed in any way, without the prior written permission of AGC".
- Clause 13 is the standing permission. "AGC has granted permission to the users of SSO to use/reproduce any Singapore legislation for the purposes of any print or electronic material or platform", on conditions. The platform must state "that the Singapore legislation is subject to copyright of the Singapore Government and is used/reproduced for the purposes of the relevant material/platform with the permission of AGC" and "that the users of the relevant material/platform may check SSO for the latest version of the Singapore legislation" (13(a)). Its producers "are responsible for ensuring the accuracy of the Singapore legislation used/reproduced" (13(b)). The use "must not convey or create any suggestion that AGC or SSO is associated or affiliated in any manner with, or endorses" the platform (13(c)). Automated extraction "must only be carried out during the hours of 3 a.m. to 7 a.m. (Singapore Time)" and not "in an abusive or intrusive, or a deceptive, manner" (13(d)).
- Clause 14 says AGC "may, at any time and without ascribing any reason or giving any prior notice, revoke the permission, or modify the permission or the conditions of the permission". Under clause 15 AGC may deny access if 13(d) is breached.
- Clause 7 says "Modification of any of the Contents ... will be a violation of AGC's copyright", so reformatting is the limit and the legal text must stay as SSO prints it.
- Clause 8 says SSO "consolidates and reproduces an unofficial version of Singapore legislation". The Gazette is the authoritative text.

The eGazette terms (https://www.egazette.gov.sg/terms-of-use/, "Last updated on 10 July 2026", read live) grant the same permission "to reproduce any e-Gazettes in any print or electronic material or platform", with the copyright and latest-version notices, the accuracy duty, no suggestion of endorsement, and no automated extraction "in an abusive or intrusive, or a deceptive, manner". They have no hours window, and the Government "may, at any time and without ascribing any reason or giving any prior notice, revoke the permission".

Parliament's terms (https://www.parliament.gov.sg/terms-of-use, clause 6, read live) give no standing permission. "To use any parts of the Contents of this Site, the user must seek permission in writing, stating the Contents for use; intent of use; manner of use; time frame of use and identity of the user." That covers the parliament.gov.sg bill PDFs, and also the Hansard text this project already hosts.

The Singapore Open Data Licence (https://data.gov.sg/open-data-licence) allows commercial reuse with attribution, but it covers only two thin data.gov.sg Bills Supplement datasets (2021, 43 rows; 2024, 33 rows) of bill number, title and date, whose PDF links point at a host that no longer resolves. Neither SSO nor AGC offers an API or a bulk download. SSO has a PDF per Act and version (`ViewType=Pdf`), a point-in-time view (`ValidDate=YYYYMMDD`) and a per-Act amendments RSS feed that nobody opened.

So hosting the text of current law needs the two notices on every page, a link to SSO for each Act, our own check that the text matches SSO, harvesting only between 03:00 and 07:00 SGT, and a way to take the text down if AGC withdraws permission. Linking each debate to the Act's SSO page needs none of that.

## Blockers

1. SSO access. Royce's rule bars SSO requests in this study, and SSO's own terms allow automated extraction only between 03:00 and 07:00 SGT. Outside that window live SSO answered scripted requests with an AWS WAF challenge, and nobody knows whether the challenge lifts inside it. The second stage for 1961 to 1999, and the bill numbers for those years, depend on getting through.
2. Partial archive copies. 13 of 72 bill texts and 7 of 72 Act texts are on SSO but only partly readable, because SSO loads long documents in pieces and the archive kept the first piece. For 2000 on, the eGazette settled 4 of the 4 such texts I tried.
3. No free text before 1961 for bills (0 of 6) or before 1985 for Acts as passed (0 of 30). Nothing in this study points to a free source, and the known copies are in print at the NUS law library.
4. Revocable permission. Clause 14 lets AGC end the hosting permission without notice, so anything built on hosted text needs a way to switch it off.
5. The parliament.gov.sg bills list (781 bills from 2006) loads through a Next.js server action that ignored scripted arguments, so reading it in full needs a browser. The eGazette and SSO cover the same bills.

## Recommendation

Adopt the first stage now, since it needs nothing from outside the database. Make the second stage depend on a small SSO trial inside the 03:00 to 07:00 window. For the third, link out to SSO and host no legislation text until AGC has confirmed in writing that a bulk rehost falls under clause 13.

Stage 1, bills to debates. This stage needs no outside source and no SSO request.

- A `bill` table and a table linking each bill to its reports, built with the grouping rule above (normalised title, closed at a third-reading line, a 366-day gap). That means a migration and a data-loss register row, because the grouping drops the 27 `bill` reports whose title names no bill (ADJOURNMENT, EXEMPTED BUSINESS and similar).
- Golden fixtures for the traps the sample found: the 2006 same-title pair, the 1998 typo, the 2026 two-day split and its "(No 2)" sequel, the 1988 select committee and appendix, and the 1974 and 1976 same-title bills.
- A review queue for the roughly 3% of first readings with no same-title debate and the 1% of reports holding several bills.
- A hand check on a fresh random sample of bills, against outside first-reading and passing dates, before calling it done.

Stage 1b, bill numbers. For 2000 to 2025 the eGazette Bills Supplement serves each bill as a PDF whose file number was the bill number in 13 of 13 sampled cases, and whose first page prints "Bill No. N/YYYY. Read the first time on" a date. For 1961 to 1999 the numbers come from SSO's Bills Supplement listing and bill pages, so they wait on the SSO trial. Before 1961 the Legislative History gives the bill number where one was assigned ("No Bill number given" for Ordinance 26 of 1955).

Stage 2, Acts to debates.

- Royce's ruling on live SSO inside the window, then a trial of about 20 pages, one request at a time and 8 seconds apart, to see whether the WAF challenge lifts.
- If it does, harvest each Act's PDF, current Acts first and then repealed Acts that have pages, and parse the Legislative History entries. Store each entry as SSO prints it (ADR 0013) and join it to the stage 1 bills on bill number, then on first-reading date within one day, then on title. At 8 seconds a page a four-hour window allows about 1,800 pages a night. This study did not count current Acts; SSO lists about 1,533 Acts Supplement entries.
- For 2000 on, check each join against the eGazette Acts Supplement's "passed by Parliament on" date, which needs no SSO request.
- Before 1985, link the debate to the principal Act's current page where one exists (13 of 30 sampled), and otherwise to the law's name from the first-reading text, with no text of the Act as passed.

Stage 3, current law.

- First, link each debate to the Act's SSO page, and from 2000 to the eGazette PDF. This reproduces no legislation.
- Before hosting any text, write to AGC's Legislation Division to confirm that clause 13 covers a bulk rehost and to ask whether a bulk route exists. Then build the two notices, the per-Act SSO link, a check of our copy against the SSO PDF on each harvest, and a switch that takes the text down.

## Open questions for Royce

1. Do you adopt stage 1 as an objective in `docs/vision.md`? I recommend yes for stage 1 alone, and deciding on stage 2 after the SSO trial.
2. May a scheduled job fetch live SSO between 03:00 and 07:00 SGT? I recommend yes, starting with the 20-page trial at one request every 8 seconds, and stopping if the WAF challenge answers.
3. May any route use a browser, for example to read the full parliament.gov.sg bills list? I recommend no. The eGazette covers 2000 on and SSO covers 1961 on.
4. Do you accept that bills before 1961 and Acts as passed before 1985 will show debate links but no original text? I recommend yes, with no scanning or print-copy work.
5. For stage 3, link out or host the text? I recommend linking out, and writing to AGC before any hosting.
6. Parliament's clause 6 asks for written permission to reuse Hansard, which the project already does. Do you want to write to Parliament? I recommend one letter covering Hansard and the bill PDFs, decided apart from this goal because it bears on the existing site.
7. May the report and its JSON be committed? I recommend yes once you have read them, on master as your rule for your own repos says. The working tree is on `feat/pq-roles`.

## Royce's rulings, 4 November 2026

Royce took the recommendation on questions 1 to 5 and 7.

1. Stage 1 is adopted as objective 7 in `docs/vision.md`. Stage 2 is decided after the SSO trial.
2. A trial of about 20 live SSO pages runs inside the 03:00 to 07:00 SGT window, one request every 8 seconds, and stops if the WAF challenge still answers.
3. No browser.
4. Bills before 1961 and Acts as passed before 1985 get debate links with no original text.
5. Stage 3 links out to SSO and the eGazette and hosts no legislation text.
6. Not taken up here. Royce ruled on 2 November 2026 not to ask Parliament for permission and to act on a takedown request if one comes (`docs/vision.md`), and that ruling stands.
7. The report is committed to master.

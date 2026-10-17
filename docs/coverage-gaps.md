# Coverage gaps

What SPRS lists and the database does not hold, for the whole corpus up to the cutoff of 15 April 2025, the end of Parliament 14. Checked on 17 October 2026 against `hansard_replica`, which equalled the remote by table hashes after round 8. The third audit ([north-star-audit-2026-10-17.md](report/north-star-audit-2026-10-17.md)) crawled every month; the windows below were crawled again with `gateway/hansard_search.py`, and every record was requested again from `getHansardTopic`.

## Hits SPRS lists that are not stored: 37

All 37 are older-system hits whose sittings are stored. A dry run fetched each one and parsed it with the current parser: all 37 return text and give 816 speech rows, 45 of them with no speaker. They are not written yet; the write waits for Royce's go.

| Sitting date | Hits | Report types |
|---|---|---|
| 22 Nov 2010 | 1 | oral answer |
| 17, 20 and 21 Oct 2011 | 3 | motion, oral answer, debate on the President's Address |
| 21 Nov 2011 | 23 | 12 written answers, 5 `written-answer-na`, 2 oral answers, 2 bill introductions, a bill and a clarification |
| 22 Nov 2011 | 10 | 5 oral answers, 2 bills, 2 written answers and 1 `written-answer-na` |

The third audit counted 24 hits on 21 November and 9 on 22 November; the crawl of 17 October 2026 at 22:40 gives 23 and 10.

## Hits the search counts but never returns: 6

The engine's total for a window is higher than the distinct hits it returns, after 25 passes over every page. Checked again on 17 October 2026 with the same result.

| Window | Engine total | Returned | Short by |
|---|---|---|---|
| April 1963 | 101 | 100 | 1 |
| October 2003 | 47 | 43 | 4 |
| September 2013 | 108 | 107 | 1 |

## Stored records SPRS no longer lists: 9

The database keeps them. `bill-intro-1318#` and `ministerial-statement-1902#` are stored again under the new ids `budget-1318#` and `clarification-1902#`. The other seven are `oral-answer-1730#`, five `written-statement-` ids from 2022 to 2025, and one 1970 budget id.

## Records with no text at the source: 18

Every record except an atbp report should have text. These 18 do not, because SPRS returns none: the newer system answers with no `resultHTML`, and the older system with an empty `htmlContent`. Each was requested again on 17 October 2026. The 106 newer-system atbp records have no text by design and are not listed.

| Report | Id | Type | Sitting date |
|---|---|---|---|
| 203 | `written-statement-2644#` | written statement | 6 Mar 2025 |
| 1337 | `written-statement-2498#` | written statement | 15 Oct 2024 |
| 3943 | `written-statement-2244#` | written statement | 3 Aug 2023 |
| 3945 | `written-statement-2243#` | written statement | 3 Aug 2023 |
| 6640 | `written-statement-1963#` | written statement | 12 Sep 2022 |
| 7423 | `ministerial-statement-1902#` | ministerial statement, stored with text as `clarification-1902#` | 10 Mar 2022 |
| 11663 | `bill-intro-1318#` | bill introduction, stored with text as `budget-1318#` | 3 Mar 2020 |
| 15040 | `oral-answer-1730#` | oral answer | 3 Jul 2017 |
| 22165 | `00075639-WA.00073202-ZZ_1##` | oral answer | 19 Jan 2009 |
| 23534 | `00004830-WA.00001562-WA_1##` | budget | 9 Mar 2006 |
| 24080 | `00075527-WA.00070504-ZZ_1##` | bill | 16 Nov 2004 |
| 24165 | `00075539-WA.00070689-ZZ_1##` | budget | 28 Feb 2005 |
| 24298 | `00075528-WA.00070522-ZZ_1##` | oral answer | 17 Nov 2004 |
| 24300 | `00004674-WA.00000676-WA_1##` | bill | 16 Nov 2004 |
| 24678 | `00004662-WA.00000928-WA_1##` | budget | 16 Mar 2004 |
| 24679 | `00004662-WA.00000930-WA_1##` | budget | 16 Mar 2004 |
| 24681 | `00004662-WA.00000931-WA_1##` | budget | 16 Mar 2004 |
| 24905 | `#011_10031016_S0006_T0005.html-#` | motion | 16 Oct 2003 |

## Stored without text, but SPRS has it now: 1

Report 20612 (`00076464-WA.00076461-WA_11#motion#`, a motion of 16 January 2012) is stored with an empty `htmlContent`. SPRS now returns 48,228 characters for it. The refill waits for Royce's go, with the 37 hits above.

## The end date

`settings.search_to_date` stopped at 8 April 2025, 7 days short of the cutoff. SPRS lists no hit from 9 to 15 April 2025, so no record is missing from that week.

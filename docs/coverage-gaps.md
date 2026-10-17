# Coverage gaps

What SPRS lists and the database does not hold, for the whole corpus up to the cutoff of 15 April 2025, the end of Parliament 14. Checked on 17 October 2026 against `hansard_replica`, which equalled the remote by table hashes after round 8. The third audit ([north-star-audit-2026-10-17.md](report/north-star-audit-2026-10-17.md)) crawled every month; the windows below were crawled again with `gateway/hansard_search.py`, and every record was requested again from `getHansardTopic`.

## Hits SPRS listed that were not stored: 37, stored on 18 October 2026

All 37 are older-system hits whose sittings are stored. `scripts/apply_coverage_refill.py` fetched each one, parsed it with the current parser and stored it on the remote and the replica on 18 October 2026: 37 reports and 816 speech rows, 45 of them with no speaker. Stage 8 linked all 771 others. The two databases hash equal after the write.

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

## Records with no text

18 stored reports other than atbp have no text, and all 18 are source failures. A 19th, report 20612, was refetched with the 37 hits above: 48,228 characters and 75 speech rows. The named list is Appendix A of the [data loss register](data-loss-register.md).

## The end date

`settings.search_to_date` stopped at 8 April 2025, 7 days short of the cutoff. SPRS lists no hit from 9 to 15 April 2025, so no record is missing from that week.

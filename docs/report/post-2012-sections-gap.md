# Sections against stored reports, 14 October 2026

This report measures how many SPRS sitting sections have a stored topic report after the newer-system inserts. It is read-only. It reads `sitting.sections` (the API's `takesSectionVOList`, one list per sitting) on the 386 sittings with `html_full_content` null, dated 10 September 2012 to 8 April 2025. It also reads `report` (`report_id`, `report_type`, `title`, `original_title`, `sitting_date`) for the same dates. For each date, sections pair with reports by normalised title (lower case, punctuation and spaces collapsed, either report title). The rest pair with the closest remaining title of the same type, at a difflib ratio of at least 0.6. Written answers, bills and the like only pair within their own type. Atbp reports have no section and stay out of the pairing. Nothing was written to the database.

## Headline

Step c's 3,769 inserts closed 3,750 of the 3,756 sections that had no report. Six remain, on six dates. No date has more than 2 unpaired sections, so no follow-up crawl is needed on this evidence.

| Measure | Before step c (earlier measurement) | Now |
|---|---|---|
| Sections | 19,877 | 19,880 |
| Reports in range | 16,221 | 19,990 |
| Sections with no report | 3,756 | 6 |
| of which written answers | 2,762 | 4 |

The section count moved by 3 because the source changed: the sitting of 7 March 2025 now lists 27 sections where the earlier fetch got 24. Reports rose by 3,769, which matches the inserts.

## Pairing

| Step | Sections |
|---|---|
| Sections in all | 19,880 |
| Paired by normalised title | 19,580 |
| Paired by closest title (ratio 0.6 or more) | 294 |
| Unpaired | 6 |

## Unpaired sections

By section type, with the earlier figure beside it:

| Section type | Before step c | Now |
|---|---|---|
| WA (written answer) | 1,484 | 2 |
| WANA (written answer, not answered) | 1,278 | 2 |
| OA (oral answer) | 520 | 0 |
| OS (other) | 291 | 2 |
| BP (bill) | 96 | 0 |
| BI (bill introduction) | 79 | 0 |
| WS (written statement) | 8 | 0 |

By parliament:

| Parliament | Sections | Unpaired |
|---|---|---|
| 12 | 3,059 | 1 |
| 13 | 5,564 | 4 |
| 14 | 11,257 | 1 |

Parliament comes from `sitting.parlement_no`. Where it is null, the date decides (12 before 15 January 2016, 13 before 24 August 2020, otherwise 14).

The six sections:

| Date | Type | Section title |
|---|---|---|
| 2018-07-09 | WA | Fresh Graduates of Institutes of Higher Learning Hired by Public Servi... |
| 2018-08-06 | WA | Fines on SMRT for Fatal Accident in March 2016 and Tunnel Flooding in ... |
| 2019-01-14 | WANA | LUP, HIP and EASE Programmes for HDB Rental Blocks in Boon Lay |
| 2019-02-12 | WANA | Admission of Special Needs Students into Institutes of Higher Learning |
| 2023-07-03 | OS | Rearrangement of Business |
| 2013-09-16 | OS | (blank title) |

Four of the six have a stored report under a much longer or reworded title that fell below the 0.6 cut, so they are title mismatches and not missing reports. The report ids are written-answer-38, written-answer-205, written-answer-na-4466 and written-answer-na-4610. "Rearrangement of Business" most likely matches motion-2201, "Revised Order of Second Readings". That leaves the blank-titled section on 16 September 2013 as the only likely real gap.

## Reports with no section

| Report type | Reports with no section |
|---|---|
| atbp | 105 |
| written-statement | 5 |
| written-answer | 2 |
| written-answer-na | 2 |
| motion | 1 |
| oral-answer | 1 |
| Total | 116 |

By parliament: 12 has 19, 13 has 45 and 14 has 52. The 105 atbp reports are expected, since atbp has no section. The 11 others are the four reworded written answers and the motion above, plus the six stored ids the crawl no longer serves: oral-answer-1730 (3 July 2017) and written-statement-1963, 2243, 2244, 2498 and 2644. The five written statements are clarifications by a minister. The stored rows stay, as risk 12 recommends.

## The September 2013 hit

The search crawl reached the engine total in 159 of 160 months. In September 2013 the engine reports 108 hits and 25 passes returned 107 distinct ones. No source names the missing hit's id. The only stored date that month is 16 September 2013, with 107 sections and 107 stored reports, one of them atbp. The blank-titled OS section on that date is the likely counterpart of the hit that never came back. This is an inference, not a confirmed match.

## Dates with more than 2 unpaired sections

None. Six dates have one unpaired section each (listed above), and no date has more.

## Follow-up

1. Leave the six stored ids the crawl no longer serves in place.
2. Look at the 16 September 2013 blank-titled section by hand, to find out which report it should carry and whether the missing hit is its text.
3. Check that "Rearrangement of Business" (3 July 2023) and motion-2201 are the same item.
4. Decide whether to pair on `reportType` and section order as well as title, so the four truncated written-answer titles pair without a manual look.

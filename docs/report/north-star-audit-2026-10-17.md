# North star audit, third pass, 17 October 2026

This audit tests the project against the done tests in `plans/north-star-done-brief.md` (local, gitignored). Those tests cover the whole corpus up to 15 April 2025, the end of Parliament 14, and count the hansard app as part of the goal. An Opus auditor measured the database and both repos. It wrote its verdict at 17:15 +08, before it read `docs/vision.md` "Measuring progress" or the 13 October audit, and then reconciled. Sonnet readers did the hand checks. The orchestrating session ran the SPRS crawl and checked the readers' work.

Figures come from `hansard_replica` on 17 October 2026 between 16:46 and 17:19 +08, after write #7. The 750 sitting-level Deputy Speaker links landed on the replica between about 16:48 and 17:13, so every figure that depends on links was rerun from 17:16 to 17:19. Scripts and raw output are in the session scratchpad and are not kept.

## Verdict

Not done. Of the ten tests, two pass, one is unmeasured and seven fail. The speech table is close to its gates, and the hand checks pass well. The work left is delivery and upkeep: the app is not served anywhere, its common-word search runs past the API's 30-second timeout, 2,511 reports need a re-parse, 37 records SPRS lists are not stored, and the per-type tracking script does not exist.

| Done test | Status | Measured | Gap |
|---|---|---|---|
| O1 Coverage | Fail | The crawl of 1955 to 15 Apr 2025 found 41,839 distinct hits, against 41,811 stored. 37 crawl hits are not stored. 9 stored ids are not in the crawl. 19 reports other than atbp have no text. | 37 records to fetch. 6 hits the engine counted but never returned. 17 textless reports to name. `settings.search_to_date` stops 7 days short of the cutoff. |
| O2 Parliaments 0 to 11 | Fail, gate stale | Round 4 strata: Tier A 0.049% (bound 0.095%), Tier B 0.760% (bound 1.099%). Detectors 6.99 and 3.31 per million tokens, against source rates of 79.7 and 7.98. | Writes #5 and #7 changed 46 of the 363 pooled reports inside their read window. They need a second read. |
| O2 Parliaments 12 to 14 | Fail, no full round | Pilot of 36 reports and 399 rows: Tier A 0.039% (bound 0.090%), Tier B 0 found, Tier C 0.385%. Round 4 pooled 309 reports from these Parliaments: Tier A bound 0.107%, Tier B bound 1.214%, with 10 touched since. Detectors 0.23 and 0 per million tokens. | One full round under the stopping rule. Every figure so far is inside the gates. |
| O3 Sitting metadata | Pass | All 1,719 sittings have attendance. Every list the newer format provides is filled, or is empty because the source list is empty. The older format provides no sections, annexures, vernaculars or a2b list. | None. Older-format PTBA is stored as `[]` on 1,333 sittings, which looks like a day with no PTBA and is not marked absent. |
| O4 Speaker linking | Pass | 404 of 406 linked rows right: 99.5%, Wilson 98.2% to 99.9%; weighted by stratum 99.7%. No link to the wrong person. | None. |
| O5 Markdown | Fail | The stopping rule half is stale, as in O2. 19 reports lose more than 5% of their HTML word tokens, not counting the registered marker removals. Report 22103 loses 97.7% and is listed. | 46 re-reads, shared with O2. 18 reports above 5% to list or explain. 14 are Assembly-era titles kept in `report.title`, 2 are tokenizer artefacts and 2 are header repeats. |
| O6 Tracking | Fail | `scripts/attribution_text_share.py` prints the three numbers per Parliament group. | Per-type output, zero-row count, collapse share, a run after every write, and output kept in git. |
| Stored rows equal a fresh parse | Fail | 2,511 of 41,801 reports differ. 125 held reports differ in content (3,566 rows). 2,386 differ only in ordinal numbering (30,471 rows). | 2,511 reports to re-parse. In 53 held reports a fresh parse loses 1,630 words the stored rows hold, so the parser needs fixes first. |
| Vision text | Fail | 6 claims in "Strategies" are false and 4 are partly true. | 10 claims to correct. |
| App | Fail | No deployment config. CORS allows only `http://localhost:5173`. All 7 required indexes exist. "government" under relevance sort ran past 30 s in 3 of 3 runs. | Hosting, a production API URL and CORS, and common-word relevance search under 30 s. |

## O1: the crawl

The crawl ran `gateway/hansard_search.py::get_window_hansard_search_results` month by month from January 1955 to 15 April 2025. Requests were sequential, and it took about 75 minutes.

- **37 hits are not stored.** Matching by id, by id prefix and by title plus date finds none of them. One is from 22 Nov 2010, 3 are from 17, 20 and 21 Oct 2011, 24 are from 21 Nov 2011 and 9 are from 22 Nov 2011. They are older-system Parliament 12 ids, mostly written and oral answers, plus 3 bills, 2 bill introductions, a motion, a clarification and a President's Address debate. The sittings themselves are stored, with 63 and 21 distinct records on 21 and 22 Nov 2011.
- **6 hits were never seen.** In three windows the engine's total was higher than the distinct hits returned after 25 passes: April 1963 (1), October 2003 (4) and September 2013 (1).
- **9 stored ids are not in the crawl.** `bill-intro-1318#` and `ministerial-statement-1902#` are already known: they are stored under new ids. The other seven are `oral-answer-1730#`, five `written-statement-` ids from 2022 to 2025, and one 1970 budget id. SPRS no longer lists them, and the database keeps them.
- **19 reports other than atbp have no text.** 8 are newer-system reports with NULL content: 15040, 11663, 7423, 6640, 3943, 3945, 1337 and 203. 11 are older-system reports with an empty string: 24905, 24681, 24679, 24678, 24080, 24300, 24298, 24165, 23534, 22165 and 20612. `docs/data-loss-register.md` gives counts only, and `docs/vision.md` names 2 ids.

## O2 and O5: why the gate is stale

Round 4's own `cycle4/r4prep/build_r4.py verify --db hansard_replica` finds 56 of the 672 pooled reports changed inside their read window: 46 in Parliaments 0 to 11 and 10 in Parliaments 12 to 14. Write #5 changed 41 of them and write #7 changed 24, with 9 changed by both. Every change is explained by a write plan. The touched reports held 1 Tier A row and 41 Tier B rows when they were read. Re-running `aggregate_r4.py` unchanged reproduces the published figures, so the margin is wide. The stopping rule still asks for the 56 to be read again.

## O4: the hand check

406 linked rows, 58 from each of seven strata (Parliament 0, 1 to 3, 4 to 8, 9 to 11, 12, 13 and 14), with whole-row checks against the source. The two wrong rows are text that no member spoke:

- 922416 (Lim Kim San, report 37818): a line of the printed schedule of departmental titles annexed to his motion.
- 343409 (Intan Azura Mokhtar, report 20377): the section heading "Building Capacity of the Malay Community".

Two chair rows whose source names no presiding officer were counted as right from the dates. 1198294 is Mr Speaker on 12 Sep 2022, and Tan Chuan-Jin was Speaker then. 1157290 is "Mr Deputy Speaker" on 5 Jul 2023, where "Mr" excludes Jessica Tan and leaves Christopher de Souza. Two readers saw a party label of PAP on members who sat for Barisan Sosialis: Lee Siew Choh in June 1962 and Teo Hock Guan in 1961. That is a party error on the Speaker row, not a wrong link.

One reader first judged 98 rows without opening the source, and it was sent back to check every row. Three of the four readers used the derived markdown, and opened the HTML only to settle doubt.

## Stored rows against a fresh parse

`fresh_parse.py` runs `build_report`, `get_start_of_speech_line`, `get_speeches` and `apply_unattributed_speech_range` on the first raw row of each id, as `populate/reports.py` and `populate/speeches.py` do. It compares ordinal, speaker, transcript and kind for all 41,801 reports. The parser raised no error.

| Group | Reports | Content differs, all held | Ordinal numbering only | Markdown differs |
|---|---|---|---|---|
| Parliaments 0 to 11 | 20,911 | 112 reports, 3,410 rows | 1,286 reports, 19,373 rows | 57 |
| Parliaments 12 to 14 | 20,890 | 13 reports, 156 rows | 1,100 reports, 11,098 rows | 11 |

Ordinal-only differences come from deletes that never renumbered: 2,421 reports have gaps in their ordinals, 6,395 values in all. Order and text are equal. Write #7 holds 126 reports. 38147 now equals its fresh parse. Kind is NULL on 2,275 rows, all in reports no write has rebuilt.

## Vision text

False:

1. "Entity tables ... no fields dropped, no values changed". Titles are rewritten, sitting numbers are filled from the header table, and empty strings become NULL (register rows 36, 37 and 83).
2. "Re-parsing is cheap: drop the derived rows, rerun the populate step". Stages skip by existence (`populate/speeches.py:25-27`), dropping rows loses ids and links, and real re-parses run through `plans/speech-fidelity-loop/bin`.
3. "fetch → parse → enrich". `script.py:9-15` calls none of stages 2 to 4.
4. "Parsing statistics are exported after every run". Nothing exports them.
5. "Each cycle is reviewed before merging". There is no merge, because commits go to master.
6. "~22,000-document corpus". It holds 41,801 reports.

Partly true: the three document eras (the code branches on two systems), "targeted rather than global" (most steps in `utils/markdown_parser.py` are global), the attribution hierarchy (step 2 covers the President's Address only, and the atbp, mover and presenter branches are missing), and "idempotent" (stages skip by existence, so a parser change never re-runs).

## App

- **Hosting.** No Dockerfile, CI, host config or domain. CORS allows only `http://localhost:5173` (`api/main.py:20-25`), and `VITE_API_URL` defaults to localhost (`app/src/api/client.ts:1`).
- **Coverage.** The API and the frontend carry all 23 report types and set no limit on Parliament or date. Nothing assumes text ends in 2012.
- **Indexes.** All 7 required indexes exist, plus `ix_speech_transcript_tsv`, which the code now queries (`api/crud/speech.py:53,147`). `docs/required-indexes.md` still names the expression index.
- **Search.** The speech search in `api/crud/speech.py:134-165` was run under a 30 s timeout, with only the crawl as other load:

| Query | Time |
|---|---|
| "government", relevance sort | Over 30 s in 3 of 3 runs, also with a 2000 to 2010 date filter |
| "government", date sort | 12.9 s and 26.8 s |
| "minister" | 26.3 s |
| "singapore" | 18.5 s |
| "housing" | 11.3 s to over 30 s |
| A rare word, a phrase, or a person filter | 0.01 s to 11.1 s |

## The three numbers, rerun 17:16 to 17:19

| Group | ADR 0001 rate | All-rows rate | Text share |
|---|---|---|---|
| Parliaments 0 to 11 | 513,489 / 523,415 = 98.10% | 513,489 / 609,701 = 84.22% | 180,792,748 / 186,092,963 = 97.15% |
| Parliaments 12 to 14 | 421,853 / 426,238 = 98.97% | 421,853 / 441,011 = 95.66% | 130,232,894 / 131,765,166 = 98.84% |

## Where the project's own docs disagree

1. **The speech fidelity loop.** `docs/vision.md` calls the loop done. Writes #5 and #7 have since changed 56 pooled reports inside their windows, so under the stopping rule the gate is stale.
2. **Scope of round 4.** `docs/vision.md` files round 4 under records before 10 September 2012, but 309 of its 672 pooled reports, 46%, are from Parliaments 12 to 14.
3. **Coverage.** No doc mentions the 37 unstored hits from 2010 and 2011, or that `settings.search_to_date` stops 7 days short of the end of Parliament 14.
4. **Sitting metadata.** `docs/vision.md` rates O3 "Partly" because the older format's lists are empty. Under the done test, lists the source does not provide are not gaps.
5. **Markdown loss.** `docs/vision.md` still quotes "120 reports lose more than 5%" and "0.41% of tokens" from 13 October. Counting the registered marker removals it is now 498 reports and 0.46%. Without them it is 19 reports and 0.009%.
6. **Stored rows.** `docs/vision.md` says stored rows match the parser except in the held reports. That holds for content. It omits the 2,386 reports whose ordinals have gaps, and the 53 held reports where a re-parse would lose words.
7. **Kinds.** HEADING is 12,365 and SPEECH 950,495, against 12,358 and 950,502 after write #5, although writes #6 and #7 report no kind change.
8. **Strategies.** "Parsing statistics are exported after every run", flagged on 13 October, is still in "Strategies", and "~22,000" contradicts the 41,811 records stated in the same file.

## Distance to done, in order of size

1. **Launch the app.** It needs hosting, a production API URL and CORS, and relevance search on common words under 30 s.
2. **Pre-launch re-parse.** First fix the parser for the 53 held reports where a re-parse loses 1,630 words. Then rebuild all 2,511 differing reports and renumber the ordinals.
3. **O6 script.** Build it, run it after each write, and commit its output.
4. **A full round on Parliaments 12 to 14,** plus a second read of the 56 touched pooled reports.
5. **Fetch the 37 missing records.** Re-request the three short windows, move `settings.search_to_date` to 15 April 2025, and name the 17 textless reports.
6. **Correct the 10 claims in "Strategies",** and list the 18 reports above 5% token loss.

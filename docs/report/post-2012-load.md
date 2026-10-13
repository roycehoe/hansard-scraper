# Post-2012 load: decisions and run record

On 14 October 2026 the production database received the text, speeches, sitting details and attendance for sittings from 10 September 2012 to 8 April 2025 (Parliaments 12 to 14). This file records what was decided, how the writes were made safe, what each step wrote, and which judgement calls the owner approved. The evidence it cites is in [post-2012-load/](post-2012-load/).

The load ran in steps b, c, e, f, g and h against the database, then steps i and k for the documents. Step a (gateways and the newer-system fetch), step d (parser change) and step j (ADRs) were code and docs commits before the first write. The plan and brief that drove the load sit in the gitignored `plans/` folder, so the decisions are repeated here. Timestamps in [RUN_LOG.txt](post-2012-load/RUN_LOG.txt) are UTC; the local date was 14 October.

Related records: [ADR 0001](../adr/0001-attribution-denominator.md), [ADR 0002](../adr/0002-role-holder-attribution.md), [ADR 0003](../adr/0003-newer-system-raw-mapping.md), [post-2012-text.md](post-2012-text.md), [post-2012-sections-gap.md](post-2012-sections-gap.md), [vision.md](../vision.md) and the "Post-2012 load, 2026-10-14" section of [speech-speaker/progress.txt](../speech-speaker/progress.txt).

## Scope and decisions

The brief fixed twelve decisions.

1. Parliament 12 (from 10 September 2012), 13 and 14 are in scope. Parliament 15 is out. The fetch takes its end date from `settings`, so adding Parliament 15 later is a date change.
2. Topic text (report, speech, stage 8) and sitting data (attendance, permission to be absent, sections, vernacular speeches, annexures) are both in scope.
3. No new tables and no new columns.
4. Newer-system topic text is stored in `hansardwebsiteresponse.content`, although the API returns it as `resultHTML.content`. This bends the raw-first rule and is recorded in ADR 0003.
5. Existing rows are filled in place and keep their ids. A rerun of a fill changes nothing.
6. Search hits the paging bug skipped in Parliaments 12 to 14 are added with the month-by-month crawl.
7. The headline stays Parliaments 0 to 11. A post-2012 rate with the same filter is reported beside it.
8. New-format attendance comes from the structured `attendanceList`, with the existing title stripping applied before name resolution.
9. Speech rows come only from topic text, one report row per topic. Sections are stored raw and used as a check.
10. Research started at once and was read-only. The plan was written after the style-guide refactor landed.
11. Agents dry-ran the parser in memory on about 30 reports per type per parliament. An independent agent vetted the plan against the north star before implementation.
12. A full database backup precedes any production write.

The vet returned "cogent with changes". The plan applied all ten of its items.

1. Deputy Speaker start dates corrected to 25 January 2016 (Parliament 13) and 31 August 2020 (Parliament 14). End dates unchanged.
2. Lee Li Lian gets no speaker row. Her 6 attendance rows stay unlinked and are named in the stats. Step g adds exactly 3 rows.
3. Step c split corrected to 594, 1,037 and 2,249 hits by parliament, over 276 sitting dates.
4. The dry run restores the backup taken before step b.
5. Step f stores the canonical speaker name in `attendance.speaker_name`, as pre-2012 rows do.
6. Every topic and sitting is fetched once into a cache, and the rehearsal and production both run from it.
7. `Mr DeputySpeaker` joins the date-dependent roles. `BARE_DEPUTY_RE` misses the glued form, which is now noted.
8. Step b's selection is bounded by the end date in `settings`.
9. The golden harness is copied somewhere durable before production depends on it.
10. Step g cites Hansard sittings and Wikipedia, not the parliament.gov.sg page that returns 404.

## Safety method

Every production step followed the same sequence.

- **Rehearsal.** The step ran first on a local Postgres restored from the pre-load backup, from the same fetch cache production used. Rehearsals repeated as the code changed. "Rehearsal 3" is the copy the verdicts compare against.
- **Verdict.** An independent review read the code, the rehearsal counts and the live production state (read-only transactions) and returned APPROVE with conditions before the step ran. Step b was the exception: its verdict was written afterwards, as a retroactive review, and the gap is recorded in [b_verdict.md](post-2012-load/b_verdict.md).
- **One transaction per step.** The driver swapped each commit for a flush and made one real commit at the end, so a failure left production unchanged. Step b committed twice (raw contents, then report contents), which the plan allowed.
- **Ids saved before commit.** The driver wrote the ids of every inserted row to a file before the real commit. The ids files for steps b, c, e, f, g and h are in the evidence folder, except step e's (see the table).
- **Rollback by saved ids.** The rollback script deletes the inserted rows by those ids, restores any filled columns from a snapshot, and nulls links absent from the pre-step snapshot. Dry runs passed on rehearsal copies for step f (38,572 deleted, 386 and 386 restored) and step h (416,858 and 38,566 nulled, 0 snapshot links differing). No production rollback was needed.
- **Link snapshot and diff.** Before each step the driver saved every `(id, speaker_id)` pair for speech and attendance. Afterwards it counted links changed (an existing link that differs) and links added. Before step h the snapshot held 580,410 speech and 96,350 attendance links.
- **Production against rehearsal.** After each step the same rows were compared with rehearsal 3 by natural key and hash. Steps b to h all matched.
- **Hand check.** Thirty rows per step were read against the source.
- **Backup.** The database `defaultdb_backup_20261014` sits on the same cluster. It was taken before step b, so it predates the whole load. It is the last resort, not a substitute for the saved ids.

Stop rules applied after every step: the headline for Parliaments 0 to 11 must stay at 564,509 of 578,359, no existing link may change, no pre-2012 report row may change, and no pre-2012 report may gain or lose speech rows. None fired.

The driver, the rollback script and the golden harness lived in the session scratchpad and are not kept. This file and the evidence folder replace them as the record.

## Steps and results

All steps ran at commit c218743.

| Step | What it wrote | Rows | Ids inserted | Hand check | Links changed |
|---|---|---|---|---|---|
| b | Topic text filled in place on newer-system raw and report rows | 16,123 report rows filled (Parliament 12: 2,576; 13: 4,533; 14: 9,014); 19,850 raw rows hold text; 98 stay null (87 atbp, 11 failed fetches) | none | 30 of 30 | 0 |
| c | Skipped search hits inserted into `hansardwebsiteresponse` and `report` | 3,880 rows in each table: 3,769 newer-system, 111 older-system Parliament 12 hits before 10 September 2012; 594, 1,037 and 2,249 by parliament; 18 atbp without text | 43,521 to 47,400, 3,880 per table | 28 of 30 | 0 |
| e | Speech rows for every report filled by b or inserted by c | 427,891 rows in 19,892 reports; 93 reports parse to zero rows | 1,098,900 to 1,526,790, 427,891 ids (file not copied, 3.7 MB) | 30 of 30 | 0 |
| f | Sitting details filled in place, then attendance | 386 raw and 386 sitting rows filled; 4 `ptba_to` overwrites; 38,572 attendance rows (35,829 present, 2,743 absent) | 96,502 to 135,073, 38,572 attendance ids | 30 of 30 attendance, 5 of 5 sittings | 0 |
| g | Resolver constants (in code) and head-of-state speaker rows | 3 speaker rows: Tan Keng Yam, Tony for Parliaments 12 and 13, Halimah Yacob for 14; 0 existing rows marked non-member | 1,436 to 1,438, 3 ids | 3 rows equal rehearsal 3, column for column | 0 |
| h | Stage 8 links, then the person stage | Speech links added 416,858; attendance links added 38,566; 5 "Mdm Speaker" rows nulled by name; 3 speaker rows joined to persons 113 and 257 | none | 30 of 30 | 0 |
| i | Sitting sections measured against stored reports | document only | none | n/a | n/a |
| k | Coverage figures and docs refreshed (commits eb6339c, c74801a, 4fd36b9) | document only | none | n/a | n/a |

Notes on the table:

- Step b filled 3,753 ids that have more than one raw row. None of those rows differ in content. The step is bounded by `settings.search_to_date`, and no row falls after 8 April 2025.
- Step c's ids are contiguous. The 3,880 hits are the crawl's 3,882 minus the 2 duplicates in `data/excluded_report_ids.json`.
- Step e's id range holds exactly 427,891 ids (1,526,790 minus 1,098,900, plus 1). Its count came in 9.1% above the plan's sample projection for Parliament 12 and 9.5% above for 14, because rows per report are heavy-tailed and 30-report samples give a loose mean.
- Step f's id range holds exactly 38,572 ids. By parliament: 12 has 8,802 rows, 13 has 13,457 and 14 has 16,313.
- Step h's speech additions outside step e's rows are 28 "The President (Dr Tony Tan Keng Yam)" rows from the Address of 10 October 2011 (ids 999,177 to 999,205). The plan predicted them.
- Step h phase counts were attendance 38,566 of 38,722; speech 414,129 of 488,210; role-context 873 of 873; deputy 1,861 of 3,130. Rehearsal 3 gave the same counts.

## Result figures

| Measure | Value |
|---|---|
| Headline, Parliaments 0 to 11 (ADR 0001 rate) | 564,509 of 578,359 (97.61%), unchanged by every step |
| All-rows rate, Parliaments 0 to 11 | 564,509 of 624,332 (90.42%), unchanged |
| Text share, Parliaments 0 to 11 | 96.81%, as in [vision.md](../vision.md) |
| Parliament 12 (whole) | 89,536 of 90,511 (98.92%); all rows 89,536 of 91,953 (97.37%); text share 98.81% |
| Parliament 12 from 10 September 2012 | 72,013 of 72,778 (98.95%) |
| Parliament 13 | 134,660 of 137,182 (98.16%); all rows 134,660 of 139,279 (96.68%); text share 99.14% |
| Parliament 14 | 208,563 of 210,646 (99.01%); all rows 208,563 of 213,056 (97.89%); text share 99.22% |
| Whole speech table | 1,068,620 rows; 1,019,991 with a speaker string; 997,268 linked (97.8%) |
| Attendance | 38,572 new rows, 38,566 linked; whole table 134,916 of 135,072 linked (99.88%) |
| Trace | `trace_speaker_links.py` over Parliaments 0 to 14: 8,915 keys, 997,268 rows, 0 stale ([trace_p14.log](post-2012-load/trace_p14.log)). Over Parliaments 0 to 11 only, before and after step h: 6,662 keys, 564,509 rows, 0 stale ([before](post-2012-load/h_trace_before.log), [after](post-2012-load/h_trace_after.log)). |

The plan projected 99.1 to 99.3 for Parliament 12 from the cutoff, 98.1 to 99.1 for Parliament 13 and 98.6 for Parliament 14. Parliament 12 from the cutoff is about 110 rows short. "The Chairman" leaves 566 rows unlinked there, and 61 "[Deputy Speaker" parse-noise rows stay in the denominator.

Where sources disagree:

- [trace_p14.log](post-2012-load/trace_p14.log) shows 8,915 keys and 997,268 rows. The two step h trace logs cover Parliaments 0 to 11 only and show 6,662 keys and 564,509 rows. The 997,268 rows equal the linked speech count in the table above, so the logs agree with each other once the scope is read.
- The brief, [post-2012-text.md](post-2012-text.md) and [vision.md](../vision.md) say 11 newer-system ids are "no longer served". [b_verdict.md](post-2012-load/b_verdict.md) splits them: 8 ids the engine no longer serves and 3 (written-statement 2628, 2645 and 2646) that return HTTP 400.
- The plan calls Lee Li Lian's 6 January 2016 entries "present". The API and the stored rows say `is_present` false. This file follows the data.
- The research crawl found 3,882 hits (Parliament 12: 594, 13: 1,038, 14: 2,250). The load inserted 3,880 (594, 1,037, 2,249) because 2 hits duplicate stored reports.

## Judgement calls

The owner approved each of these on 14 October 2026.

**a. Four stored `ptba_to` values overwritten with the API value.** Two dates, each with a raw row and a sitting row: 10 November 2016 ("2016" to "2016/2017", rows 4007 and 6336) and 3 October 2023 ("2023" to "2023/2024", rows 3730 and 6057). The fill stage normally keeps a stored value that differs from the API. Here the API value is the raw record and the stored value was truncated, so the step overwrote them. The ids are in [f_ptba_to_overwrites.json](post-2012-load/f_ptba_to_overwrites.json). The two warnings were the only fill warnings in any rehearsal.

**b. Five "Mdm Speaker" rows left unlinked.** Speech ids 1201718, 1183545, 1215656, 1215654 and 1221834, in reports 6866, 7597 (twice), 7962 and 5185, between January 2022 and February 2023. Each is a Hansard misprint for "Mdm Deputy Speaker": Jessica Tan Soon Neo held the chair, and the neighbouring chair rows say so. Linking them to her would read "Speaker" as "Deputy Speaker", a substitution ADR 0002 does not license. They stay null until a written misprint rule exists. A named exception in stage 8 enforces this. See [h_mdm_speaker_nulled.json](post-2012-load/h_mdm_speaker_nulled.json).

**c. "Mr Speaker" printed while a Deputy Speaker held the chair links to the Speaker.** [h_verdict.md](post-2012-load/h_verdict.md) lists 8 likely new rows among roughly 19,400 Speaker-label links (0.05%). The proxies used to find them miss rows where nobody addresses the chair, so the true count is likely in the tens. ADR 0002 as written allows the link, and the same code path produced the pre-2012 links in the headline. Deferred to one sweep across all parliaments, with an ADR 0002 note.

**d. 343 plain-text procedural lines credited to the previous speaker.** Lines such as "Hon Members indicated assent." are plain text in the markdown, not bold, so the parser keeps the last speaker. The rate is 343 of 427,891 new rows (0.08%), against 368 of 640,729 existing rows (0.06%). This is a shared parser trait, so it is deferred to one parser fix across all parliaments.

**e. Reports still without text.**
- 105 newer-system atbp reports (87 filled by step b, 18 inserted by step c). The API returns no topic text for them.
- 1 older-system atbp report, stored before this load.
- 11 newer-system reports: 8 written-statement (1963, 2243, 2244, 2498, 2628, 2644, 2645, 2646), 1 bill-intro (1318), 1 ministerial-statement (1902) and 1 oral-answer (1730). The fetch failed or the engine no longer serves them. A retry is being looked into by another worker.

**f. Two hits excluded as duplicates.** `budget-1318#` and `clarification-1902#` are the stored `bill-intro-1318#` (3 March 2020) and `ministerial-statement-1902#` (10 March 2022) returned again under new type prefixes. Both are listed in `data/excluded_report_ids.json` and never inserted.

**g. No speaker row for Lee Li Lian.** She declined the Parliament 13 seat, so no row is added. Her 6 attendance rows (15 and 25 to 29 January 2016, "Non-Constituency Member", `is_present` false) stay unlinked. Adding a row would be a wrong link.

**h. ADR 0002 aligned to the code.** The ADR said a label names the person "unless the report shows the woman taking part". The code counts her as taking part only when the report text names her as a Deputy Speaker (in a chair annotation, a labelled "Mdm Deputy Speaker (Name)" row, or the "MPs Speaking" header). Newer-system reports have no such header, so the check rarely bites there. In Parliament 14, 143 rows link to Christopher de Souza in reports where Jessica Tan also appears, and all are correct by the "Mr" label. The ADR now says what the code does.

## Known follow-ups

From the verdicts and hand checks. None blocked a step.

- Leave a "Mr Speaker" or "Mdm Speaker" row unlinked when the last chair annotation before it names a Deputy Speaker, or when the next speaker opens by addressing the Deputy Speaker. Needs an ADR 0002 note and a sweep over all parliaments (h).
- Decide whether to link the 5 "Mdm Speaker" rows to Jessica Tan under a written misprint rule. The two pre-2012 honorific contradictions ("Mdm Speaker" linked to Abdullah Bin Tarmugi, "Mr Chairman" linked to Indranee Rajah) belong to the same review (h).
- Stage lines after a Committee of Supply suspension ("Debate in Committee of Supply resumed.", "Head T (cont) -") are credited to "Mr Speaker" (reports 5003 and 46018). A parser fix (h).
- Report "[Deputy Speaker" as 77 rows (61 in Parliament 12, 16 in 13), not the 16 the plan expected (h).
- Plain-text procedural lines credited to the previous speaker: 343 new rows (e).
- 65 oral-answer first rows have a lone dash as the transcript, from "The following question stood in the name of X" followed by a dash (e).
- 7 adjournment motions with a bold mover give a row with transcript "]" or "].", and one has a trailing full stop in the speaker, which stage 8 may not link (e).
- About 20 speaker strings of the form "Minister for X (Mr Y);" come from multi-bill introductions (e).
- 8 of the 14 procedural records that parse to zero rows name a mover after a dash, in square brackets. The mover pattern only runs for the motion type, so they get no row (e).
- Record that the plan's row estimates were sample projections: +9.1% for Parliament 12 and +9.5% for 14 (e).
- Name written-statement 2628, 2645 and 2646 as failures beyond the plan's named list. Done in judgement call e (b).
- Hand check 5 to 10 production reports with empty emphasis tags, since 7978bed came after the last hand check of that kind (b).
- The driver's pre-2012 comparison zips rows by position. It is correct only because new ids sort last. A by-id comparison is safer for later loads (c).
- `compare_pair.py` for step c covers report columns only. Raw-row equality needs a content hash per report id (c).
- The plan's wording of Lee Li Lian's entries as "present" and of "two `ptba_to` values" (two dates, four rows) needs correcting where it is reused (f).
- Name the Wikipedia pages behind the Tony Tan and Halimah Yacob terms in the resolver constants. The Speaker page source line still names the parliament.gov.sg page that now returns 404 (g).
- Converter defects found in hand checks (c, b):
  - `<sup>` footnote digits glue to the figure before them: "248<sup>4</sup>" becomes "2484". 134 newer-system and 4 older-system reports have the pattern.
  - Adjacent bold runs lose a space and render as `**A****B**`. 18,576 pre-2012 and 175 newer-system reports have the pattern.
  - Italic runs split mid-word render as "_h_ _alal_", and italic link fragments inside bracketed cross-reference notes leave stray underscores.
  - Changing the converter would change pre-2012 markdown, so it waits for a deliberate parser change.

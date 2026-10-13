VERDICT: APPROVE

Retroactive review of step b (fill topic text in place) on production, run at commit c218743 from 02:49 to 03:17 on 14 October. I ran read-only queries on production (`BEGIN READ ONLY`) and on the local rehearsal3 database. The query files and their output are in v_*.sql, (session scratchpad) v_*.out (session scratchpad) and v_analyse.py. (session scratchpad)

## 1. Counts and content

- The snapshot selected 19,974 raw rows for 16,221 ids. All are sprs3, and no other row shares those report_ids, so the update by report_id reached no row outside the snapshot.
- The fill selected 16,134 non-atbp ids, after removing 87 atbp ids. All 11 ids in b_failed_ids.json are among them.
- Raw ids with text by parliament: P12 has 2,576 of 2,594, P13 has 4,533 of 4,568 and P14 has 9,014 of 9,059. In each parliament the set equals the selected ids minus atbp minus the failure file exactly. That makes 16,123 ids and 19,850 rows with text. The 98 null ids are exactly the 87 atbp ids plus the 11 failed ids.
- 3,753 ids have more than one raw row, and none of them has rows that differ in content.
- 16,123 report rows were filled: 2,576, 4,533 and 9,014 by parliament. On every filled row, `report.content` equals the raw content, with 0 differences.
- `markdown_content` is null on 0 rows where `content` is not null, across all 17,010 sprs3 or post-2012 report rows.
- 98 report rows in the snapshot are still null, all atbp or failed. The 16,222nd snapshot row is the 2004 older-system row with no raw text, and it is unchanged.
- I checked the stored content independently against the cache. I ran the stage's own extraction on each cached response and compared it with production. All 16,123 ids match and 0 differ.
- The failures are 11 ids, about 0.07%, against the plan's expected 0.2%. Eight of them are ids the engine no longer serves. The other three (written-statement 2628, 2645 and 2646) return HTTP 400, per CACHE_RESULT.txt. The run log has 11 WARNING lines, one per failed id, and no ERROR or traceback lines.

## 2. Stop rules

- The headline is unchanged at 564,509 of 578,359 (97.61%), with 624,332 rows in all. I recomputed it on production after the run.
- The speech table hash (id, speaker_id and transcript md5 over 640,729 rows) is a11b92a207ef9db25f5b0e2a20b6bb7d. That is identical to the hash taken before any write in compare_before.txt, so no speech row or speech link changed.
- The 96,350 attendance links equal the b_links_before.json snapshot pair for pair.
- Pre-2012 report rows: all 21,708 have the same ids and the same per-row md5 of content and markdown as the snapshot. 0 changed.
- No rows were inserted or deleted. The current counts equal the counts before the write in every table: hwr 43,520, report 37,929, speech 640,729, attendance 96,500, speaker 1,434, person 573, sitting 1,719 and hsdr 1,719. The maximum ids also match b_maxima_before.json, and b_inserted_ids.json is empty.

## 3. End date and Parliament 15

- No report row is dated after 8 April 2025, and no report or raw row belongs to Parliament 15. The latest filled raw row is dated 8 April 2025. The check passes, though trivially, because no such rows exist yet. The stage code also bounds the raw selection by `settings.search_to_date`.

## 4. Production against rehearsal3

- On the 16,221 shared sprs3 ids, the report content md5, markdown md5 and raw rows md5 differ on 0 ids (b_subset.txt (session scratchpad)). Both databases hold 98 null-content reports.
- I re-queried the local rehearsal3 database read-only. It holds 19,990 sprs3 report ids. The 3,769 ids that exist only in rehearsal3 are exactly the sprs3 rows among the 3,880 report ids in rehearsal3's c_inserted_ids.json. No id exists only in production.
- The rehearsal3 and production files agree. b_check.json is identical, and so are b_failed_ids.json and b_pre2012_report_hashes.json. The two b_touch_ids.json files hold the same sets, with the report list in a different order.
- Rehearsal3's step b started at 02:33:42, before c218743 was committed at 02:35. The code it ran was therefore 7978bed. c218743 changes only services/speech.py, which step b does not use, and the 0-difference result above confirms this.

## 5. Process gaps

- **Verdict.** No go verdict for production step b is saved in the work dir. The rehearsal report (b_REPORT.md (session scratchpad)) mentions a first verdict's blocker, but I found no saved verdict for the final rehearsal. This is a paperwork gap.
- **Production hand check.** There is no 30-row production file. The plan's check compares production with the rehearsal output, and b_subset.txt does this for all 16,221 ids, so it covers more than 30 rows would. The 30-report check against source HTML was done on rehearsal attempt 2 at 72f2771: 28 of 30 were right, and the 2 others had markdown rendering nits. That was before 7978bed changed one line of markdown conversion, and no hand check was repeated on rehearsal3 or production output. This is a paperwork gap with a small quality gap. Nothing is at risk.
- **One transaction.** Step b committed twice, raw contents at 03:06:59 and then report contents at 03:17:27. This is not the plan's single commit per stage. RUN_LOG.txt and the rehearsal report both declare it, which plan risk 7 allows. Both commits landed, and the final state is checked above, so no partial state remains. This is a paperwork gap only.
- **Rollback.** The cluster backup defaultdb_backup_20261014 matches the state before the write on counts and on the speech and report hashes (compare_before.txt).

None of these gaps leaves production at risk.

## Follow-ups

1. Save the go verdict for the final step b rehearsal next to b_REPORT.md, or record in RUN_LOG.txt that it was given in-session.
2. Add a line to RUN_LOG.txt that b_subset.txt (all 16,221 ids identical) stands in for the 30-row production comparison.
3. Optionally hand check 5 to 10 production reports that contain empty emphasis tags, since 7978bed came after the last hand check.
4. Carry the 2 markdown nits from the hand check, `**Assoc****Prof` and the italic link fragments, to the parser follow-up list.
5. Name written-statement 2628, 2645 and 2646 in ADR 0003 or the step i report as failures beyond the plan's named list.
6. Rehearsal4 is restoring into the local defaultdb_r4 database. Rehearsal3's data lives in the local defaultdb database, so keep it intact until step c's comparison is done.

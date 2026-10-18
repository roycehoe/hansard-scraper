VERDICT: APPROVE

Review of step c (insert the skipped search hits) before it runs on production, at commit bb94505 with the one-transaction driver (drive.py as of 03:42 on 14 October). All database access was read-only: `BEGIN READ ONLY` on the rehearsal3 database and through a read-only query script on production. Query files and scripts are in cv_*. (session scratchpad)

## 1. Counts against the plan (rehearsal3)

Source: cv_r3_counts.sql (session scratchpad) on rehearsal3, rows with ids 43,521 to 47,400 (the range in c_inserted_ids.json (session scratchpad)).

- 3,880 rows in `hansardwebsiteresponse` and 3,880 in `report`, each with 3,880 distinct report_ids. No row in either table has an id above 47,400.
- By system: 3,769 newer-system (sprs3) and 111 older-system (sprs2).
- By parliament: 594, 1,037 and 2,249. All 111 rows dated before 10 September 2012 are Parliament 12, and they are exactly the 111 sprs2 rows.
- By type: written-answer 1,511, written-answer-na 1,312, oral-answer 542, motion 132, bill 99, bill-intro 85, budget 67, then matter-adj 28, president-address 23, atbp 20, ministerial-statement 17, clarification 12, speaker 11, written-statement 7, Miscellaneous 4, admin-oaths 3, personal-explanation 3, and one each of point-of-order, petition, tribute and misc. The first seven match the plan's list exactly.
- Rows with no text: 18, all newer-system atbp, with both `content` and `markdown_content` null. Every other inserted row has both. The 2 older-system atbp rows carry text.
- `budget-1318#` and `clarification-1902#` are in neither table.
- The new rows fall on 276 sitting dates, and none is missing from `sitting`. I matched on `to_date(sitting.sitting_date, 'DD-MM-YYYY')` because `sitting.sitting_date` is an unpadded string.
- `report.report_id` is unique: 41,809 rows and 41,809 distinct values. The `report_report_id_key` UNIQUE constraint also enforces it on production.
- The latest `report.sitting_date` is 2025-04-08. No report is in Parliament 15, and no raw row has `parliament_number` 15.
- Each inserted report's content equals its raw row's content, and report type, parliament and version agree. 0 differences.
- c_run.log (session scratchpad) has 18 WARNING lines, one for each atbp id with no text, and 0 ERROR or Traceback lines.

## 2. Stop rules (rehearsal3)

- Headline before and after step c: 564,509 of 578,359 (97.61%), with 624,332 rows in all (c_check.json (session scratchpad)).
- Links: 0 speech and 0 attendance links changed, and 0 added.
- Pre-2012 reports: I compared by id, not by position (cv_r3_pre2012.py (session scratchpad)). All 21,708 snapshot rows are still present, and 0 changed content or markdown md5. Today there are 21,819 pre-2012 rows, and the 111 extra rows are all in c_inserted_ids.json (ids 43,521 to 43,633). The driver's own check compares by position. That works here only because the new ids sort after the old ones, so this by-id comparison backs it up.
- Pre-2012 speech: 0 reports outside the inserted set changed speech count or hash. This holds even now, after rehearsal3 has also run steps e to h.

## 3. Production readiness

- Preflight, recomputed read-only on production. The cache has 20,707 distinct crawl hits and production stores 37,929 distinct report_ids. Removing the stored ids and the 2 excluded ids leaves 3,880. That set equals c_expected_report_ids.json (session scratchpad) and rehearsal3's copy, with a symmetric difference of 0. Both excluded ids are among the crawl hits, neither is stored, and their stored twins `bill-intro-1318#` and `ministerial-statement-1902#` are present.
- Production raw and report ids pair up: 0 raw report_ids lack a report row and 0 report rows lack a raw row. So `populate_reports` will build exactly the 3,880 new reports and nothing older.
- All 276 sitting dates of the 3,880 ids exist in production `sitting`, which has 1,719 rows.
- Maximum ids on production: `hansardwebsiteresponse` 43,520 (43,520 rows) and `report` 43,520 (37,929 rows). Both sequences stand at 43,520 with is_called true, so new ids start at 43,521. These maxima equal rehearsal3's c_maxima_before.json and production's b_maxima_after.json. Speech is 1,098,899, attendance 96,501, speaker 1,435 and person 573, also the same as rehearsal3 before c.
- Rollback by saved ids is sound. The driver records every id above the saved maximum, inside the step's own transaction. rollback.py deletes those report rows first and then the raw rows. The only foreign key into either table is `speech.report_id`, so step c can be undone this way only while no step e speech rows point at the new reports.
- No report is dated after 8 April 2025 and none is in Parliament 15.

## 4. The one-transaction driver change

- Code paths: `populate/hansard_responses.py` and `populate/reports.py` use only the session passed in, through `CRUDHansardWebsiteResponse` and `CRUDReport`. Neither CRUD class opens a session, an engine or a nested transaction. The only `commit` calls in crud/ are `self.session.commit()` on the passed session. services/report.py, services/hansard_website.py and utils/markdown_parser.py do no database access. The search and topic gateways are patched to read the cache. With `session.commit` replaced by `session.flush`, both `create_many` calls become add plus flush.
- What changes is object state, not what gets written. Under a real commit, `populate_reports` gets the raw rows from `get_all()` reloaded from the database. Under flush only, it gets the same in-memory objects, which are not expired. To test whether that matters, I built all 3,880 raw and report objects in memory at HEAD from the cache, with no database round trip (cv_inmemory.py (session scratchpad)). I then compared every column with what rehearsal3 stored through real commits: 12 raw columns and 14 report columns, content and markdown included. There were 0 differences on all 3,880 rows. The flush-only path therefore feeds `build_report` the same values, and the same check confirms that HEAD reproduces rehearsal3 exactly.
- On a failure before the final commit, nothing persists. Every stage write sits in one open transaction. The preflight `SystemExit` fires before any write. Any exception before `real_commit()` exits the `with Session(...)` block, whose close rolls back. A killed process or a dropped connection leaves the transaction uncommitted, and the server discards it. If the commit itself fails after the ids files are saved, the files list ids that do not exist, and a rollback by those ids deletes nothing.
- The step c path of the new driver has not been rehearsed. rehearsal4's c ran at 03:40, before drive.py changed at 03:42, and its log has no "step committed once" line. The in-memory equivalence check above covers this gap.
- Production settings: `statement_timeout` is 0 and `idle_in_transaction_session_timeout` is 1 day, so a single longer transaction will not be cut off. Two other sessions are running long read-only queries, active for 4.5 and 5.5 hours. They take only share locks, so they do not block the inserts, and the inserts do not block them.

## 5. The 30-row sample

I read all 30 rows in c_sample30.json (session scratchpad): 4 older-system (Parliament 12, written-answer-na, written-answer, oral-answer, bill-intro) and 26 newer-system across Parliaments 12, 13 and 14 and 13 types. For each I compared the cached source HTML head with the stored markdown head.

- `stored_content_equals_cache` is true on 30 of 30.
- 30 of 30 markdown heads match the source text. Speaker names are bold and attributed, question numbers are kept, time headings and section headings come through, "Page: N" markers are dropped, "(proc text)" brackets are removed and their text is kept, `&nbsp;` becomes a space, and non-ASCII text (Chinese characters, curly quotes, dashes) is intact.
- Where a source page marker splits a paragraph, the markdown keeps the two halves on separate lines with no text lost: written-answer-na-1644# ("are" / "excluded.") and oral-answer-248# ("traffic" / "updates"). This matches step b's approved output.
- Older-system rows keep the old conversion: the metadata table, the `#` title and inline base64 images in the markdown (00076917-WA.00076933-WA_24#...). Beyond the sample, I ran the 630c4d6 version of `utils/markdown_parser.get_cleaned_report_markdown` on all 111 older-system inserts (cv_sprs2_md.py (session scratchpad)). Its output equals the stored markdown on 111 of 111.

## Conditions

1. Run the production step in this order: `drive.py production snapshot c`, then `run c`, then `check c`, with drive.py unchanged from the version reviewed here. Do not proceed unless the log shows "preflight ok: 3880 ids to insert" and "step committed once".
2. After the run, the check must show inserted ids 43,521 to 47,400 in both tables (3,880 each), an unchanged headline of 564,509 of 578,359, 0 links changed or added, 0 pre-2012 report rows changed, and an empty pre-2012 speech list. Compare production with rehearsal3 using `compare_pair.py c production rehearsal3`. It should print IDENTICAL.
3. If step c needs undoing after step e has run, undo step e first, because `speech.report_id` references `report.id`.

## Follow-ups (not blocking)

- The driver's `pre2012_report_rows_changed` compares by position (zip). It is correct for step c only because the new ids sort last. A by-id comparison, as in cv_r3_pre2012.py, (session scratchpad) would be safer for later steps.
- `compare_pair.py`'s c query covers report columns only. Raw-row equality on production can be confirmed with the c_inserted_ids file and a content md5 per report_id if wanted.

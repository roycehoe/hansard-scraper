VERDICT: APPROVE

Step e (speech rows for every report filled by step b or inserted by step c), reviewed at HEAD bb94505, 14 October 2026. Read-only review: no DB writes, no repo edits. My queries are in ev_r3.sql, (session scratchpad) ev_r3_noise.sql (session scratchpad) and ev_prod_fixed_set.sql, (session scratchpad) with output in ev_r3.out (session scratchpad) and ev_prod_fixed_set.out. (session scratchpad) The sample viewer is ev_view.py. (session scratchpad)

## What I read

- Plan sections "Step d", "Step e", "Production safety" and "Out of scope".
- drive.py stage e. The snapshot saves the fixed set (row ids and natural keys). The production run stops unless the saved natural keys equal rehearsal3's e_fixed_set_report_ids.json. run_speeches parses each report with the repo parser, numbers ordinals from 1, and flushes in batches of 5,000. The ids files are written, then the step commits once. A failure before that commit rolls back the whole step.
- rollback.py (session scratchpad) stage e deletes speech rows by the ids saved in e_inserted_ids.json. No table has a foreign key to speech, so the delete leaves nothing dangling.
- `git diff 630c4d6 bb94505 -- services/speech.py utils/markdown_parser.py`. Every new branch is gated on `report_version == ReportVersion.SPRS3`: the HTML clean-up, the start line of -1 (parse from the top), the motion mover pattern and the bill presenter pattern. The older-system path is unchanged.
- rehearsal3 e_check.json, e_run.log, e_zero_row_reports.json, e_fixed_set.json; rehearsal4 e_run.log, e_check.json, efgh_vs_r3.txt; the earlier rehearsal's e_REPORT.md; e_verify_r3.txt. (session scratchpad)

## Check 1. Plan counts

Rehearsal3 inserted 427,891 speech rows (ids 1,098,900 to 1,526,790) in 19,892 of the 19,985 fixed-set reports.

| Parliament | Reports filled by b: rows | Plan estimate | Difference | Inserted by c: reports | Inserted by c: rows |
|---|---|---|---|---|---|
| 12 | 65,872 (2,555 reports) | 60,400 | +9.1% | 588 | 9,684 |
| 13 | 124,398 (4,505 reports) | 124,300 | +0.1% | 1,028 | 14,881 |
| 14 | 173,873 (8,981 reports) | 158,800 | +9.5% | 2,235 | 39,183 |
| All | 364,143 | 343,500 | +6.0% | 3,851 | 63,748 (plan about 61,500, +3.7%) |

All counts are within 10%, but Parliaments 12 and 14 sit close to the limit. I traced the gap to how the estimate was made. R1 took the mean rows per report from 30 sampled reports per type and multiplied it by the number of reports of that type (R1/weighted.py, analysis_prop.json, pop.csv). Rows per report are heavy-tailed in budget, bill and oral-answer reports, so 30 reports give a loose mean:

- Parliament 12: budget 26,097 against 22,751 projected, oral answers 9,670 against 7,535.
- Parliament 14: oral answers 21,533 against 16,521, bills 37,700 against 32,733, budget 44,725 against 40,181, the Address 7,058 against 4,844. Motions offset some of this at 18,071 against 21,335.

Where R1 sampled every report of a type, actual equals estimate exactly: Parliament 12 president-address (29 of 29) gives 3,128 against 3,128, and matter-adj (12 of 12) gives 710 against 710. That points to sampling error in the estimate, not a parser difference. The two later parser commits moved the total by 20 rows (427,871 at b56c24b to 427,891).

## Check 2. Ordinals, written answers, pre-2012 and zero-row reports

- **Ordinals.** All 19,892 reports that gained rows run from 1 with no gaps or duplicates. No report holds both old and new rows. No new row sits in a report outside the fixed set.
- **Written answers.** 7,088 of 7,088 written-answer and 6,338 of 6,338 written-answer-na fixed-set reports have rows. In every one, the first row's transcript starts with "asked" (plan: at least 97%). None of those first rows has a null speaker. The 44 first-row speakers without the usual honorific are "Asst Prof Tan Kheng Boon Eugene" and "Asst Prof Mahdev Mohan", both real Nominated Members. The second row has an honorific-led speaker in 13,398 of 13,425 reports, which is the minister's reply.
- **Pre-2012.** 106 reports dated before 10 September 2012 gained rows, all among the 111 inserted older-system reports. The other 5 parsed to zero. No other pre-2012 report gained rows. The 576 pre-2012 reports with no rows still have none.
- **After the end date.** No report dated after 8 April 2025, and none from Parliament 15, gained rows.
- **Zero-row reports.** 93 in all:
  - 74 Committee of Supply openers ("Estimates of Expenditure ...", 101 to 131 characters). These are the plan's kind.
  - 14 newer-system procedural records with no speaker label: 4 budget-typed "Proceedings on Estimates" time-limit resolutions, 2 budget-typed adjournments, 5 Speaker announcements (President's concurrence with resolutions, Parliament opening at two locations), and 3 bill or motion records (two "Exempted Business", and bill-337's committee-stage line). I read the markdown of 10 of them. The other 4 (speaker-1559#, budget-699#, budget-432#, budget-203#) share titles and lengths with ones I read. None has a speaker label or a "presented by" line; the only bold text, in two of them, is a chair note. Zero rows is the correct parse. They are not on the plan's list only because the plan did not foresee them.
  - 5 inserted older-system reports (2 atbp, 1 budget, 1 misc, 1 motion). These go through the unchanged older path.
  - Newer-system atbp reports have null markdown, so the fixed set leaves them out, as planned.
  - Appropriation bill introductions did not stay at zero: all 32 Supply bill introductions name a presenter and got one row with that presenter. That is better than the plan expected.

## Check 3. Stop rules in rehearsal3

From e_check.json, matched by rehearsal4's e_check.json at HEAD with the one-transaction driver ("step committed once"):

- Headline before and after: 564,509 of 578,359 (97.61%); all rows 624,332. Unchanged.
- Links changed: speech 0, attendance 0. Links added: speech 0, attendance 0.
- Pre-2012 report rows changed: 0, with the same count before and after. Pre-2012 reports whose speech rows changed, outside the inserted reports: none.
- rehearsal4 against rehearsal3 for step e, keyed on report_id and ordinal: 427,891 rows on each side, same hash (26dd5f23...), IDENTICAL.

## Check 4. Production readiness

I ran the driver's fixed_set query read-only on production, with production's c_inserted_ids.json "report" list (ids 43,521 to 47,400, contiguous, the same range as rehearsal3).

- Production fixed set: 19,985 reports, 19,985 distinct report_id values. It equals rehearsal3's e_fixed_set_report_ids.json exactly (symmetric difference 0), and rehearsal4's too.
- Row ids differ for 17 pairs of step-c reports, because the async fetch inserted them in a different order (for example, written-answer-2359# is row 44,124 in production and another row id in rehearsal3). The preflight compares natural keys, so it passes. Speech rows reference production's own report rows. Any production-to-rehearsal comparison must therefore key on (report_id, ordinal), as compare_pair.py stage e already does, never on speech id.
- Production speech: max id 1,098,899, 640,729 rows. Production report: max id 47,400, 41,809 rows. Both equal rehearsal3's e_maxima_before. The driver records inserted ids as `id > 1,098,899` after the flush and before the commit, and rollback.py deletes exactly those ids. With no other writer on speech during the step, that rollback is sound.
- One other active session was running on the production database during my read. I left it alone. A read does not block the inserts.

## Check 5. The 30-row sample

I read all 30 rows in e_sample30.json. (session scratchpad) For each I pulled the full markdown from rehearsal3 around the picked row (the sample's markdown_head only covers the first 3,000 characters) and compared speaker and split by hand.

**Result: 29 right, 1 wrong.**

- Right: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24, 25, 26, 27, 28, 29. This covers every type stratum in Parliaments 12 to 14: written answers, oral answers, motions, bills, bill-intros, budget, the Address, matter-adj, ministerial statements and a written statement.
  - The bill-intros (5, 15) credit the presenter with the whole body, as step d intended.
  - Procedural lines ("Question put, and agreed to.", "Resolved, ...") get a null speaker (4, 26).
  - Supplementary questions and replies switch speaker correctly (2, 22).
  - Committee of Supply rows keep the minister across a timestamp heading (25).
- Wrong: 23 (motion-1493#, ordinal 3). "Hon Members indicated assent." is plain text in the markdown, not bold, so it was credited to "Mr Speaker", and the next procedural line was too. Sample 3 shows the bold form being handled correctly.
- Seen in sample neighbours, not picked rows:
  - Page-break fragments, a sentence split where the source breaks the paragraph. Examples: "legislation." in 0, and "through the Silver Volunteer Fund ..." in 17. That row (17's picked row) has the right speaker and follows the markdown line.
  - An oral answer whose question stood in an absent member's name. Its first row is that member with transcript "–" (2).

To size these, I compared new rows with rows that existed before step e:

| Class | New rows | Existing rows |
|---|---|---|
| Procedural line credited to a speaker | 343 of 427,891 (0.08%) | 368 of 640,729 (0.06%) |
| Row starting lower-case (page-break fragment) | 6.1% | 5.7% |
| Row with no letters or digits | 104 (0.02%) | 1,158 (0.18%) |

The new rows are as good as the existing record, or better. These are known traits of the shared parser, not regressions from step d.

## Conditions for the production run

1. Run `drive.py production snapshot e`, then `run e`, back to back with no other writer on speech or report. The run uses the fixed set saved at snapshot time and does not recompute it.
2. The preflight must print "preflight ok: 19985 reports, same set as rehearsal3". Any other output is a stop.
3. After the commit, `check e` must show:
   - headline 564,509 of 578,359 and all rows 624,332
   - 0 links changed and 0 added
   - 0 pre-2012 report rows changed, and no pre-2012 speech reports changed
   - e_inserted_ids.json holding 427,891 speech ids starting at 1,098,900
4. `compare_pair.py e rehearsal3 production` must print IDENTICAL (427,891 rows, hash 26dd5f23...). Any difference is a stop and a rollback by saved ids.
5. Hand check 30 production rows as the plan requires.

## Follow-ups (not blocking)

- Plain-text "Hon Members indicated assent." and similar procedural lines are credited to the last speaker: 343 new rows. A shared parser trait, at the same rate as pre-2012.
- 65 oral-answer first rows with transcript "–" come from "The following question stood in the name of **X** –".
- 7 adjournment motions with a bold mover give a row with transcript "]" or "].". One of them has a trailing full stop in the speaker ("Ms Grace Fu Hai Yien."), which stage 8 may not link.
- About 20 speaker strings of the form "Minister for X (Mr Y);" come from multi-bill introductions, for example bill-intro-109#.
- 8 of those 14 procedural records (6 budget-typed, 2 bill-typed) name a mover in "– [Name]" but get zero rows, because the mover pattern only runs for the motion type. If they were credited, they would match how motion-typed adjournments are handled.
- Record in the step i or step k stats that the plan's row estimates were sample projections: actual came in at +9.1% and +9.5% for Parliaments 12 and 14.

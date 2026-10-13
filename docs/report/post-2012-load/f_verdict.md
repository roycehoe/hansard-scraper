VERDICT: APPROVE

# Step f verdict: sitting fill in place, then attendance

Reviewer: independent gate, read-only. Repo at c218743. Rehearsal3 is local `defaultdb` (state after step h). Production was read through a read-only query script in read-only transactions. Query files: `fv_r3_counts.sql (session scratchpad)`, `fv_state.sql (session scratchpad)`, `fv_rows.sql (session scratchpad)`, `fv_speaker.sql (session scratchpad)`. The comparator is `fv_compare_api.py (session scratchpad)`. Outputs are in `fv_r3_rows.jsonl (session scratchpad)`, `fv_prod_rows.jsonl (session scratchpad)` and `fv_prod_state.out (session scratchpad)`.

## Code read

- `populate/sitting_details.py` selects sittings with `html_full_content` and `sections` both null and dated on or before `settings.search_to_date`. It fills null columns on the raw row from the nested builder, then null columns on the sitting row from `build_sitting(raw)`, then the four list columns when they are null. If a stored value differs from the API it logs a warning and keeps the stored value. It writes through the new `update` helpers, which only flush, and commits once at the end.
- `services/attendance.py::get_sitting_attendance_from_list` skips a null `mpName` and the leave-of-absence note. It runs the remaining entries through the same `_parse_entry_line`, `normalize_name` and `resolve_canonical_name` as the markdown path. It stores the canonical name, or the cleaned name when nothing resolves, and puts the constituency in `location_name`. The Masagos override gains Parliaments 13 and 14.
- `populate/attendances.py` uses the markdown path when markdown exists, the list path otherwise, and skips a sitting that has neither.
- The gateway picks the schema by the `metadata` key, as sweep ruling 13 says. The nested builder now serialises `attendanceList` and `ptbaList`.
- `drive.py` stage f: `session.commit` is swapped for `flush`. The ptba_to exception runs after the fill. On production, a preflight compares the overwrites with `f_ptba_to_overwrites.json (session scratchpad)` on (table, date, stored, API) and requires 386 filled sittings. If either check fails it rolls back and exits. One real commit follows the ids files. A failure anywhere before that commit leaves production unchanged.
- `rollback.py (session scratchpad)` stage f deletes attendance rows by their saved ids, then restores every column of the snapshotted raw and sitting rows. The only foreign key into these tables is attendance to sitting, so deleting first is the right order.

## Check 1: plan counts in rehearsal3

- Target rows: 386 raw and 386 sitting rows have null `html_full_content`, dated 10 September 2012 to 8 April 2025. None are before the cutoff.
- On all 386 rows of both tables: `attendance_list`, `ptba_list` and `parlement_no` are set. On sitting, `sections`, `annexures`, `vernaculars` and `a2b` are set on all 386.
- Non-empty lists: sections 386, vernaculars 347, a2b 105, annexures 103. The plan says 346 vernaculars; the extra one is 7 March 2025, which gained its vernacular list at the source after R2 (`cache/CACHE_RESULT.txt`).
- Entry totals: sections 19,880, vernaculars 2,209, a2b 464, annexures 373, attendance 38,584, ptba 8,822. The differences from the plan's 19,877, 2,198 and 8,840 come from the same two source-side changes: 5 August 2019 ptba and 7 March 2025 sections and vernaculars.
- Attendance: 38,572 new rows (ids 96,502 to 135,073), 35,829 present and 2,743 absent. By parliament: 12 has 8,802 (8,041 present, 761 absent), 13 has 13,457 (12,507, 950), 14 has 16,313 (15,281, 1,032). All match the plan.
- Per sitting: 386 of 386 sittings have row count equal to list length minus null `mpName` minus leave notes. Over all sittings that is 38,584 entries, minus 1 null name and 11 notes (all in Parliament 13), giving 38,572. No entry was dropped silently by the parser.
- Every new row has a name and a location. 193 distinct names. Every new row sits on a target sitting, and no pre-existing row does.
- `html_full_content` is null on all 386 raw and sitting rows. `markdown_content` is null on all 386 sitting rows.
- Raw and sitting rows agree on every shared column checked (lists, ptba, numbers, speaker, display date): 0 differences.

## Check 2: metadata against the API, and nothing outside the step changed

- Comparator over all 386 dates and both tables, rehearsal3 after the step, reading the cached bodies directly rather than through the builder: 13,374 values equal, 0 differences. Both list columns and all four sitting lists equal the API structurally and byte for byte.
- The one column set in the API but null on sitting is `online_pdf_file_name`. The API returns `""` for all 386 dates. `build_sitting` turns `""` into null by its existing NOTE, and pre-2012 sitting rows have it null too. This is expected.
- The API also sends `writtenAnswersVOList` and `writtenAnsNAVOList`, which have no column. Both are empty on all 386 dates, so nothing is lost.
- The ptba_to exception changes exactly 4 rows: raw 4007 and sitting 6336 on 10-11-2016 ("2016" to "2016/2017"), and raw 3730 and sitting 6057 on 3-10-2023 ("2023" to "2023/2024"). The plan says "two values"; it means two dates. The earlier rehearsal report explains this. These are the only two fill warnings in the rehearsal3 and rehearsal4 logs. The log has no ERROR lines.
- Untouched rows: the 1,333 non-target sitting rows and 1,333 non-target raw rows hash identically, every column, in rehearsal3 after step h and in production now (`d984edcf...` and `40294c64...`). The 96,500 attendance rows with id up to 96,501 hash identically on both, including `speaker_id`. So the rehearsal changed no pre-2012 sitting or attendance row.

## Check 3: attendance conventions

- Scenario 3: 1-3-2016, "S Iswaran", `is_present` false, `location_name` "West Coast". The API entry reads "Mr S Iswaran (West Coast), Minister for Trade and Industry (Industry).", attendance false. After step h the row links to speaker 1058.
- Masagos: all 386 API entries are stored as "Masagos Zulkifli Bin Masagos Mohamad".
- No new `speaker_name` has parentheses, commas, periods, a title or a role word. `location_name` takes 39 values, all constituencies plus "Nominated Member" and "Non-Constituency Member". None is "Parliament House", the API's seat value.
- Lee Li Lian: her 6 Parliament 13 entries (15 and 25 to 29 January 2016, "Non-Constituency Member") remain as attendance rows. After step h they are the 6 unlinked rows. All 6 have `is_present` false, which matches the API: each entry has `attendance: false`. The plan's risk 5 and step g call these entries "present". That is a wording error in the plan, not a data error (see follow-ups). Her 80 Parliament 12 rows for Punggol East link to speaker 957 after step h.

## Check 4: stop rules in rehearsal3

- `f_check.json (session scratchpad)`: headline 564,509 of 578,359 (97.61%) before and after. Links changed: 0 speech, 0 attendance. Links added: 0 and 0.
- Rehearsal4 reached the same headline and the same 0/0, and its natural keys equal rehearsal3: attendance `c759d7b5...`, sitting `9a315997...`, raw `1ff1643f...` (`efgh_vs_r3.txt (session scratchpad)`).

## Check 5: production readiness (read-only)

- 386 raw and 386 sitting rows have null `html_full_content`. All 386 sitting rows also have null `sections`, so the fill selects all of them. Dates run from 2012-09-10 to 2025-04-08. None fall before the cutoff or after `search_to_date`. Raw and sitting pair one to one by date, and no date appears twice in either table.
- 0 attendance rows on the target sittings.
- No non-target sitting lacks attendance rows, so `populate_attendances` will process only the 386.
- All 386 raw and 386 sitting target rows in production equal `f_sitting_rows_before.json (session scratchpad)` column for column (60 and 65 columns, 0 rows differ). Production starts from exactly the state rehearsal3 started from.
- Stored values against the cached API: 7,465 equal and 4 differ. The 4 are the rehearsal's ptba_to rows, with the same ids (3730, 4007, 6057, 6336) and the same values. Before the fill, metadata is null on 173 rows and `attendance_list` and `ptba_list` on 322; the other 64 equal the API. All three numbers match the plan.
- Speaker rows with id up to 1,435 (1,434 rows) hash identically to rehearsal3, ignoring `person_id`, which step h changed. Name resolution therefore sees the same lookups the rehearsal saw.
- Attendance max id 96,501, 96,500 rows, sequence `last_value` 96,501. The new rows will get ids from 96,502. Rollback deletes by the saved ids file.
- Totals: 1,719 raw and 1,719 sitting rows, sitting max id 7,484, raw max id 5,158, the same as rehearsal3.

## Check 6: the 35 sampled rows (`f_sample_r3.json (session scratchpad)`)

- 30 attendance rows: all 30 right. I read each one against its cached API entry. Name, present flag and constituency agree for every row. Four sampled rows (107869 Lim Wee Kiak, 124343 and 118436 Liang Eng Hwa, 107303 Teo Ho Pin) did not have their own entry in the sample's candidate list, so I checked them against the cache directly; all four agree. Row 107914 stores "Mohd Fahmi Bin Aliman" for "Mr Mohd Fahmi Aliman (Marine Parade).", which is the Parliament 14 speaker row's name (speaker 1192). All 30 rows exist in rehearsal3 with the stored values the sample shows.
- 5 sitting rows (5958, 6608, 6701, 6921, 7040): all 16 metadata fields equal the API on every row. Attendance, ptba, a2b, sections, annexures and vernaculars list lengths in the database equal the API lengths, and each sitting's attendance row count equals its list length (98, 100, 103, 101, 100).

## Conditions

1. Run `drive.py production snapshot f` only after step e's commit and check are complete, then `run f`, then `check f`. The headline and links snapshot must come after e.
2. Do not rerun the fill or attendance outside the driver. The preflight stops the run unless the overwrites equal the rehearsal's 4 and 386 sittings are filled. If it trips, nothing is committed. Stop and report.
3. After the commit, confirm all of the following: 38,572 attendance ids in `f_inserted_ids.json`, from 96,502 to 135,073; headline 564,509 of 578,359; 0 links changed or added; `compare_pair.py f` (attendance, f_sitting, f_raw) IDENTICAL against rehearsal3. Then do the 30-row production hand check against rehearsal3.
4. If any stop rule fires, run `rollback.py (session scratchpad) production f` without `--commit` first, read the counts, then commit.

## Follow-ups (not blocking)

- The plan's risk 5, step g and step h describe Lee Li Lian's six January 2016 entries as "present". The API and the stored rows say absent. Correct the wording in the plan and the stats.
- The plan's verify list says "two ptba_to values". Record that it is two dates and four rows.
- The f rollback (delete by ids, then restore every column) has not been run end to end on a rehearsal copy. The code is simple and its restore loop matches `restore_sitting_rows.py`, which the first rehearsal exercised. Dry-run it on a rehearsal copy if a spare copy exists.
- I did not re-run the golden harness from the plan's verify list for this gate.

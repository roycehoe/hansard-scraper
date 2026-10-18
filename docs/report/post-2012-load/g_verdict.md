VERDICT: APPROVE

# Step g verdict: resolver constants and three Speaker rows

Reviewer: independent gate, read-only. Repo at bb94505, clean. The constants commit is 0b695c6. `git diff 0b695c6 HEAD` is empty for `populate/speaker_resolution_constants.py`, `populate/speaker_links.py`, `services/attendance.py`, `data/heads_of_state.json` and `scripts/load_heads_of_state.py`, so production runs exactly what was rehearsed. Production was read through a read-only query script in read-only transactions. Query files: `gv_g_sim.sql (session scratchpad)`, `gv_g_names.sql (session scratchpad)`, `gv_g_headline.sql (session scratchpad)`, `gv_g_ids.sql (session scratchpad)`. Outputs sit beside them as `.out`.

## Code and data against the plan and the vet

| Item | Plan and vet section 3 | 0b695c6 | Status |
|---|---|---|---|
| Speaker Seah Kian Peng | 2 Aug 2023 to 15 Apr 2025 | same | matches |
| Deputy Speakers P13, Charles Chong and Lim Biow Chuan | 25 Jan 2016 to 23 Jun 2020 (vet item 1) | same | matches |
| Deputy Speakers P14, Jessica Tan Soon Neo and Christopher de Souza | 31 Aug 2020 to 15 Apr 2025 (vet item 1) | same | matches |
| Women Deputy Speakers | add Jessica Tan Soon Neo | added | matches |
| President Tony Tan | 1 Sep 2011 to 31 Aug 2017, name "Tan Keng Yam, Tony" | same | matches |
| President Halimah Yacob | 14 Sep 2017 to 13 Sep 2023 | same | matches |
| `Mr DeputySpeaker` | in the deputy labels and the date-dependent roles (vet item 7) | in both | matches |
| Masagos override | keys for Parliaments 13 and 14 | added | matches |
| `data/heads_of_state.json` | Tony Tan for 12 and 13, Halimah Yacob for 14 only | exactly those 3 records | matches |
| Citations (vet item 10) | Hansard sittings and Wikipedia | Seah: Hansard of 2 Aug 2023 and the Wikipedia Speaker page. Deputies: Hansard of 25 Jan 2016 and 31 Aug 2020, the Wikipedia Deputy Speaker page and the 13th and 14th Parliament pages | present |

The driver's stage g swaps the loader's `Session` for the step's session through a `nullcontext`, so `CRUDSpeaker.create` and `update` call the patched `session.commit`, which is a flush. The one real commit comes after `g_inserted_ids.json` and `g_maxima_after.json` are written. Importing the loader also imports `database/init.py`. That builds an engine but does not connect and does not run migrations, so the import has no side effect.

## Check 1: exactly 3 rows inserted, 0 marked

The loader reads every record in `data/heads_of_state.json`. A record whose `(name, parliament_number)` has no speaker row is inserted with party "Non-partisan", `is_legislative_assembly` false and `is_member` false. A record that matches a member row flips that row to `is_member` false. `gv_g_sim.sql` repeats this read-only against production for all 20 records:

- Records 0 to 16, the Governors and Presidents up to S R Nathan, each match exactly one row (ids 1417 and 1420 to 1435). Each of those rows is already `is_member` false, so the loader does nothing to them.
- Records 17 to 19 match nothing: "Tan Keng Yam, Tony" for 12, "Tan Keng Yam, Tony" for 13 and "Halimah Yacob" for 14. These three get inserted.
- No `(name, parliament_number)` key appears twice in `speaker`, so the loader's dict cannot hide a second row.
- Halimah Yacob is in the file for Parliament 14 only. Her Parliament 13 member row (id 1052) does not match any record and stays a member.

Result on production: 3 inserted, 0 marked non-member. Rehearsal3 and rehearsal4 logged the same line ("Inserted 3 head-of-state speakers, marked 0 existing rows as non-members"). Their inserted rows (ids 1436 to 1438) hold Non-partisan, `is_member` f, `is_legislative_assembly` f, with the record's comment.

Production's speaker table, compared as `(id, name, parliament_number, is_member, person_id)` for all 1,434 rows, matches `g_speakers_before.json` in both rehearsal3 and rehearsal4 exactly. Production starts from the same state the rehearsals did.

## Check 2: names join the existing people

- "Tan Keng Yam, Tony" exists for Parliaments 4 to 10 (ids 259, 333, 402, 490, 579, 678, 785), all person 113. The new rows use the same spelling.
- "Halimah Yacob" exists for Parliaments 10 to 13 (ids 728, 824, 934, 1052), all person 257, and has no row for 14. The new row uses the same spelling.
- In rehearsal3 and rehearsal4, after step h, the person stage gave rows 1436 and 1437 person 113 and row 1438 person 257.

## Check 3: Lee Li Lian and the constant names

- Lee Li Lian has one row, Parliament 12 (id 957). Nothing in the file or the constants adds one for 13.
- Exact `speaker.name` matches on production, for the parliaments their new terms cover:
  - Seah Kian Peng, Speaker in 14: rows for 11 to 15.
  - Charles Chong, Deputy in 13: rows for 7 to 13.
  - Lim Biow Chuan, Deputy in 13: rows for 11 to 14.
  - Jessica Tan Soon Neo, Deputy in 14: rows for 11 to 15.
  - Christopher de Souza, Deputy in 14: rows for 11 to 15.
  - "Masagos Zulkifli Bin Masagos Mohamad", the override target: rows for 11 to 15.
- The fuzzy search turned up no near-miss spelling of these names.

## Check 4: headline unaffected

- Every term added starts on or after 1 September 2011. The earliest is Tony Tan's, on 1 September 2011. The Masagos override only adds keys for 13 and 14.
- No report in Parliaments 0 to 11 is dated on or after 1 September 2011. The latest is 11 April 2011.
- Glued deputy labels (`deputy\s*speaker` without the space), aggregated per report and then joined to report: 3 rows of "Mr DeputySpeaker", all in Parliament 12. None in Parliaments 0 to 11, and no "Mdm DeputySpeaker" anywhere. So the new label cannot touch a headline row.
- Step g itself writes only speaker rows. In both rehearsals the headline stayed at 564,509 of 578,359 (97.61%) through step h as well, which reads the new rows.

## Check 5: stop rules in rehearsal3

`g_check.json (session scratchpad)`: headline 564,509 of 578,359, 97.61%, all-rows 624,332, before and after. Links changed: 0 speech, 0 attendance. Links added: 0 and 0. Rehearsal4 shows the same, and `efgh_vs_r3.txt` shows g IDENTICAL (3 rows, same hash). The golden harness passes at bb94505, and the rehearsal report records that every resolver file stayed unchanged.

## Check 6: ids and references

- Production speaker max id is 1435 (1,434 rows). The sequence (`mp_id_seq`) last value is 1435, so the new rows should get 1436 to 1438, as in both rehearsals. `f_maxima_after.json` also records speaker 1435.
- The only foreign keys into `speaker` are `speech.speaker_id` and `attendance.speaker_id`. Their maxima are 1435 and 1419, and 0 rows point above 1435. Nothing can reference the new rows until step h runs.
- `rollback.py (session scratchpad) production g` deletes exactly the ids in `g_inserted_ids.json`. That works only while nothing references them, which means before step h, or after step h's own rollback.

## Conditions

1. Run `drive.py production snapshot g` before `run g`, so `g_maxima_before.json` (speaker 1435), `g_speakers_before.json` and `g_links_before.json` exist. Confirm that the snapshot's speaker maximum is still 1435.
2. The run log must say "Inserted 3 head-of-state speakers, marked 0 existing rows as non-members" and "step committed once". `g_inserted_ids.json` must hold exactly 3 speaker ids and no other table. Anything else: stop and roll back with `rollback.py production g`.
3. `drive.py production check g` must show the headline at 564,509 of 578,359, and 0 links changed or added.
4. Hand check the 3 new rows against rehearsal3 ids 1436 to 1438: name, parliament, party, `is_member`, `is_legislative_assembly` and comments. `person_id` stays null until step h.
5. Do not start step h until conditions 2 to 4 pass. After step h, roll back h before you roll back g.

## Follow-ups (not blocking)

- The `SPEAKER_TERMS` source line still names the parliament.gov.sg Speaker page, which now returns 404. It is kept for the older terms. `HEAD_OF_STATE_TERMS` cites "Wikipedia day-level dates" in general and names no page for Tony Tan or Halimah Yacob. Both dates match the vet. A later docs pass could name the pages.
- From 14 September 2017 to the end of Parliament 13, "The President" resolves to Halimah Yacob's Parliament 13 member row (id 1052). The plan accepts this (risk 6, the Address of May 2018), and the person stage puts both rows under person 257.
- Production has only 3 glued "Mr DeputySpeaker" rows, all in Parliament 12, where the plan's sample counted 4. As the plan says, `BARE_DEPUTY_RE` does not match them in the two-holder phase, so they stay unlinked. That is safe.

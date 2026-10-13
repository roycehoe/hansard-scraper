VERDICT: APPROVE

# Step h verdict: stage 8 speaker links, then the person stage

Reviewer: independent gate, read-only. Repo at c218743. `git status` shows only `scripts/attribution_text_share.py` modified and one untracked report under `docs/report/`; neither is imported by stage h. Rehearsal3 (local `defaultdb`) was read with `BEGIN READ ONLY`. Production was read through a read-only query script. Query files are in `` as `hv_*.sql`; the context scripts are `hv_ctx.py (session scratchpad)`, `hv_chairnote.py`, `hv_deputy.py` and `hv_chair.py`, all read-only against rehearsal3.

## Code under test

- `populate/speaker_links.py` and `populate/persons.py` are unchanged since e52c020 apart from `Mr DeputySpeaker` joining the deputy labels and the date-dependent roles. `services/role_context.py` is unchanged. The constants (`populate/speaker_resolution_constants.py`) and the Masagos override for Parliaments 13 and 14 are the step g commit d26d37e, approved in `g_verdict.md`.
- Stage 8 selects only rows with `speaker_id IS NULL` in every phase, and `set_speaker_ids_bulk` is a raw `UPDATE ... FROM UNNEST` in the session's transaction. Existing links cannot change by construction.
- One transaction (plan risk 7). The driver turns `session.commit` into `flush`. Each later phase reads the earlier phases' writes through column selects or raw SQL in the same transaction, so it sees what a real commit would have shown. The only ORM objects held across phases are `Speaker` rows (from `get_all`), and nothing in stage 8 writes them, so the person stage reads the same `person_id` values either way. Empirical check: rehearsal3 ran h with per-phase commits (`the earlier driver version`, whose stage h block differs only in the commit lines), rehearsal4 ran it as one transaction with the current `drive.py` (saved at 03:42, run at 03:56). Both logs show the same phase counts, and `efgh_vs_r3.txt` reports h, h_att and h_person IDENTICAL by natural key.

## The named exception for "Mdm Speaker"

In rehearsal3 the exception nulled 5 rows, all linked by date to Tan Chuan-Jin:

| Speech id | Report | Date | Ordinal | Row text |
|---|---|---|---|---|
| 1221834 | 7962, Prisons (Amendment) Bill | 11 Jan 2022 | 245 | "Mr Desmond Choo." |
| 1215654 | 7597, Debate on Annual Budget Statement | 1 Mar 2022 | 922 | "Mr Gerald Giam." |
| 1215656 | 7597, same | 1 Mar 2022 | 924 | "Senior Minister of State Zaqy." |
| 1201718 | 6866, National Dialogue ... National Service | 5 Jul 2022 | 7 | "Please proceed." |
| 1183545 | 5185, Affordable and Accessible Public Housing | 7 Feb 2023 | 423 | "Senior Minister of State Sim Ann." |

Who was in the chair: Jessica Tan Soon Neo, Deputy Speaker. In every case the neighbouring chair rows are "Mdm Deputy Speaker" (linked to her), and the next speaker opens with "Mdm Deputy Speaker" (Desmond Choo, Sim Ann) or the minister just before addressed "Mdm Deputy Speaker" (Ng Eng Hen). None of the dates falls in her Acting Speaker period (17 Jul to 2 Aug 2023); the cache holds no sitting between 6 July and 2 August 2023. These are Hansard misprints of "Mdm Deputy Speaker".

Judgement: nulling is the ADR 0002 result. The printed honorific is evidence, and "Mdm" excludes the only Speaker on those dates, so no holder is left. Linking Jessica Tan would mean reading "Speaker" as "Deputy Speaker", a substitution ADR 0002 does not license, even though the context makes her near certain. "A wrong link is worse than no link" decides it for this step.

More rows needing the same treatment: none in the new rows. A search for any chair label (Speaker, Deputy Speaker, Chairman, President) whose honorific contradicts the linked person's sex found 0 rows from 10 September 2012 after the exception, and 2 pre-2012 rows already linked before the step ("Mdm Speaker" to Abdullah Bin Tarmugi, "Mr Chairman" to Indranee Rajah). Step h cannot touch those, by design. "Mr Speaker" linked to Halimah Yacob: 0 rows. The exception matches the exact string only, and no variant ("Mdm Speaker:" and the like) slipped past it. It excludes every link in the snapshot, so it cannot change an existing link. Production holds the same 5 rows under the same ids, unlinked today.

## Check 1. Stop rules in rehearsal3

- Links changed: speech 0, attendance 0 (`h_check.json (session scratchpad)`; rehearsal4 the same).
- Headline, Parliaments 0 to 11: 564,509 of 578,359, 97.61%, all rows 624,332, before and after. Every parliament from 0 to 11 is unchanged row for row in the per-parliament table.
- Links added: speech 416,858 (414,129 + 873 + 1,861 from the three phases, less the 5 nulled), attendance 38,566. Outside the step e and f rows: exactly 28 speech rows, "The President (Dr Tony Tan Keng Yam)" in the President's Address of 10 October 2011, linked to "Tan Keng Yam, Tony", Parliament 12 (ids 999,177 to 999,205). That is the plan's predicted addition. Attendance outside the step f rows: 0.
- Every new speech link points at a speaker row of the report's own parliament (P12 73,607, P13 134,660, P14 208,563, plus the 28). Every new attendance link points at the member row of the sitting's parliament, and the stored `speaker_name` equals `speaker.name` on all 38,566.
- `trace_speaker_links.py` after h: 6,662 keys, 564,509 rows, 0 stale. The production trace before h is also 0 stale.

## Check 2. Rates against the plan

| Scope | Linked | ADR 0001 denominator | Rate | Plan |
|---|---|---|---|---|
| Parliament 12 whole | 89,536 | 90,511 | 98.92% | about 99.0% |
| Parliament 12 from 10 Sep 2012 | 72,013 | 72,778 | 98.95% | 99.1% to 99.3% |
| Parliament 13 | 134,660 | 137,182 | 98.16% | 98.1% to 99.1% |
| Parliament 14 | 208,563 | 210,646 | 99.01% | 98.6% |

All-rows rates: P12 97.37%, P13 96.68%, P14 97.89%.

Parliament 12 from 10 September 2012 is 110 rows short of the plan's low end (72,123 would be 99.1%). The unlinked rows there are "The Chairman" 566 (0.78 points on its own), bare "Mr Deputy Speaker" on two-man days 103, "[Deputy Speaker" 61 and "Notes" 7. The 61 "[Deputy Speaker" rows are parse noise that ADR 0001 keeps in the denominator. Risk 11 expected 16 such rows in all, but there are 77 (61 in P12, 16 in P13). Without them P12 from the cutoff would be 99.03%. The projection came from a 1,108-report sample that understated both the Chairman share and this noise. Parliament 13 sits at the low end because 937 bare "Mr Deputy Speaker" rows on days with two men in office stay unlinked, as ADR 0002 requires, and 1,526 Chairman rows stay open. Parliament 14 beats the projection. No count is off by more than 10%, so no stop rule fires.

## Check 3. Attendance

- New rows: 38,566 of 38,572 linked. The 6 unlinked rows are all Lee Li Lian (15, 25, 26, 27, 28 and 29 January 2016). They are stored with `is_present` false, although plan risk 5 calls them "present" entries; step k should word the stats from the data.
- Scenario 3: S Iswaran on 1 March 2016 links to his Parliament 13 row.
- Masagos: 386 of 386 attendance rows link to "Masagos Zulkifli Bin Masagos Mohamad". The written answer in the sample (row 16) shows speech resolution uses the same override.

## Check 4. Role rows

Linked role rows in the new rows: Mr Speaker to Tan Chuan-Jin 7,101, Seah Kian Peng 3,586, Michael Palmer 145; Mdm Speaker to Halimah Yacob 3,038; Mdm Deputy Speaker to Jessica Tan Soon Neo 1,035; Mr Deputy Speaker to Christopher de Souza 1,399, Lim Biow Chuan 256, Charles Chong 187, Seah Kian Peng 19; The Chairman 870; The President 303 in six Addresses.

- Speaker changes. On 14 Jan 2013, 11 Sep 2017 and 2 Aug 2023 the resignation notice is read by "The Clerk of Parliament" (unlinked), and every chair row after the election goes to the new Speaker: Halimah Yacob (P12 row) in 2013, Tan Chuan-Jin (P13) in 2017, Seah Kian Peng (P14) in 2023. No sitting falls in the gaps between terms (13 Dec 2012 to 13 Jan 2013, 8 Aug to 10 Sep 2017, 18 Jul to 1 Aug 2023). Halimah's re-election on 15 Jan 2016 and Tan's on 24 Aug 2020 link to the right parliament rows. The cached sittings confirm the deputy election dates of 25 Jan 2016 and 31 Aug 2020.
- Deputy Speaker links against the report's own chair annotations ("[Deputy Speaker (Mr X) in the Chair]"): where an annotation precedes the row, it agrees with the link every time. P12 45, P13 408, P14 de Souza 222, P14 Jessica Tan 248; 0 disagree. The rest have no annotation before them or could not be aligned.
- The Chairman against the same annotations: 848 agree, 0 disagree, 22 unaligned.
- President rows: 2011 and 2014 to Tony Tan's P12 row, 2016 to his P13 row, 2018 to Halimah Yacob's P13 member row (as step g intends), 2020 and 2023 to her P14 row. No bare "The President" row is left unlinked.
- Two-holder days, Parliament 14 (one man, one woman). 143 de Souza rows sit in 24 reports where Jessica Tan also appears: 5 in report 9058 (2 Aug 2021), where she chairs under her own "Mdm Deputy Speaker" label before the 4.11 pm suspension and he chairs after it, and 138 where she speaks as a member. The "Mr" label decides these, and they are right. ADR 0002's clause "unless the report shows the woman taking part" reads more strictly than the code, which only counts her as taking part when the text names her. Older reports name her in their "MPs Speaking" header, so the check bit there; newer-system reports have no such header, so it does not. See follow-up 3.

Wrong-person class found: "Mr Speaker" printed while a Deputy Speaker held the chair. Stage 8 links a Speaker label to the Speaker of the day, so a Hansard misprint of the chair's title becomes a wrong link. Likely cases in the new rows, each with a Deputy in the chair by the report's own annotation or by the next speaker's address ("Mr Deputy Speaker, Sir"):

| Report | Date | Ordinal | Linked to | Evidence |
|---|---|---|---|---|
| 44502 | 3 Oct 2017 | 1 | Tan Chuan-Jin | next speaker addresses Mr Deputy Speaker |
| 14112 | 28 Feb 2018 | 400 | Tan Chuan-Jin | annotation names Lim Biow Chuan; next address Mr Deputy Speaker |
| 14005 | 20 Mar 2018 | 60 | Tan Chuan-Jin | next address Mr Deputy Speaker |
| 13435 | 1 Oct 2018 | 71 | Tan Chuan-Jin | mover and next speaker address Mr Deputy Speaker |
| 11370 | 4 Jun 2020 | 380 | Tan Chuan-Jin | annotation names Charles Chong; next address Mr Deputy Speaker |
| 11279 | 2 Sep 2020 | 283, 312 | Tan Chuan-Jin | annotation names de Souza; next address Mr Deputy Speaker |
| 7598 | 1 Mar 2022 | 33 | Tan Chuan-Jin | previous speaker addresses Mdm Deputy Speaker; next says "Madam" |

That is about 8 rows among roughly 19,400 Speaker-label links (0.05%). The proxies used to find them miss rows where nobody addresses the chair, so the true count is likely in the tens. This is not a new defect of step h. ADR 0002 as written allows it (one Speaker on the date, and the label says Speaker), and the same code path already produced the pre-2012 links in the headline. It does not trip a stop rule. See follow-up 1.

A related minor case: after a Committee of Supply suspension, the parser attributes stage lines such as "Debate in Committee of Supply resumed." and "Head T (cont) −" to "Mr Speaker" (reports 5003, 46018). These are step e parse noise that ADR 0001 keeps in the denominator, and stage 8 links them to the Speaker of the day.

Unlinked role strings in the new rows: The Chairman 4,018, Mr Deputy Speaker 1,119, [Deputy Speaker 77, Mr Chairman 44, Deputy Speaker 14, The Clerk of Parliament 8, Mdm Speaker 5, Mr DeputySpeaker 3. All stay null for ADR 0002 reasons or because the string is noise.

## Check 5. Person stage

The log reads "573 persons for 1437 speaker rows; 0 created, 3 speaker rows updated, 0 refused unions". Speakers 1436 and 1437 ("Tan Keng Yam, Tony", P12 and P13) join person 113 beside his member rows for Parliaments 4 to 10. Speaker 1438 (Halimah Yacob, P14) joins person 257 beside her member rows for Parliaments 10 to 13. The `person_id` sum moves by exactly 483 (113 + 113 + 257), and the person hash is unchanged.

## Check 6. Production readiness

Production today equals rehearsal3 just before h. Rehearsal3's figures come from its `h_links_before.json` and `h_persons_before.json`.

| Measure | Production | Rehearsal3 before h |
|---|---|---|
| speech rows, linked, max id | 1,068,620, 580,410, 1,526,790 | same |
| speech links hash (id:speaker_id) | c2958b853c488e3e1e8bdb31142da989 | same |
| attendance rows, linked, max id | 135,072, 96,350, 135,073 | same |
| attendance links hash | 42315301c17f0e8fab00aabb837915c1 | same |
| speaker rows, with person, max id | 1,437, 1,434, 1,438 | same |
| speaker (id, name, parliament, is_member) hash | ff6ba1943f7fcad9b998fd67bb29b8d0 | same |
| speaker person_id hash | dd1e2380384ddfcbe877672c9b2f2e9b | same |
| person rows, hash | 573, 9970f641208aafdb9ebaaef99ea83d2d | same |
| the 5 "Mdm Speaker" rows and the 28 rows of 10 Oct 2011 | same ids, unlinked | same |

Steps b to g in production each equal rehearsal3 by natural key (`*_compare.txt`), and both servers run PostgreSQL 17.

Rollback. `drive.py snapshot` saves every existing `(id, speaker_id)` pair and every `(speaker.id, person_id)` before the run. `rollback.py production h` nulls every link absent from that snapshot, reports any snapshot link that differs, restores `person_id` from the snapshot and deletes inserted persons (none expected). Because stage 8 only fills nulls, nulling everything outside the snapshot is an exact undo. A failure before `real_commit()` rolls the whole step back with nothing persisted. The cluster backup taken before step b remains the last resort. The h rollback has not yet been run on a rehearsal copy; condition 1 covers that.

## Check 7. The 30-row sample

I read all 30 rows of `h_sample_r3.json (session scratchpad)` with their neighbours, and all 30 are right, person and parliament row both.

- Role rows (10): Mdm Speaker to Halimah Yacob P13 (10 Jan 2017); Mr Speaker to Tan Chuan-Jin P14 (7 Nov 2022); The Chairman to Lim Biow Chuan P13 (11 Apr 2016; the report's last annotation before the row is "[Deputy Speaker (Mr Lim Biow Chuan) in the Chair]"); Mdm Deputy Speaker to Jessica Tan P14; Mr Deputy Speaker to de Souza P14 (10 May 2023; the next speaker says "Sir"). The rest are role-plus-name strings: Edwin Tong (Minister for Culture, Community and Youth, 2022), Heng Swee Keat (Minister for Finance 2018; Deputy Prime Minister 2020, both P13), Grace Fu (Leader of the House 2019), Josephine Teo (Minister for Manpower 2020, P14).
- Written answers (10): askers Don Wee, Faizah Jamal (Nominated Member, P12), Ang Wei Neng, He Ting Ru, Louis Chua; answerers K Shanmugam (Home Affairs 2019), Masagos (Social and Family Development 2023, through the override), Tan Chuan-Jin (Acting Minister for Manpower, 10 Sep 2012, P12), Tan See Leng (Manpower 2023), Lawrence Wong (Education, April 2021). Each matches the ministry the question names.
- Plain names (10): Ng Ling Ling, K Shanmugam, Lim Wee Kiak, Zainal Sapari, Edwin Tong, Zhulkarnain Abdul Rahim (twice), Ganesh Rajaram (Nominated Member, P13), Desmond Lee, Kok Heng Leun (Nominated Member, P13). Each continues the speech of the linked member, in the right parliament.

## Conditions for the production run

1. Before production h, dry-run `rollback.py (session scratchpad) rehearsal3 h` without `--commit`. Rehearsal3 already has h applied. Expect speech nulled 416,858, attendance nulled 38,566, 0 snapshot links differing in each table, the 3 `person_id` values restored, 0 persons deleted, then "dry run: rolling back". This exercises the 580,410-element `<> ALL` array once before it is needed.
2. Run `drive.py production snapshot h` first. `production/h_links_before.json` must hold 580,410 speech and 96,350 attendance pairs with the hashes in the check 6 table, and `h_persons_before.json` must equal rehearsal3's.
3. The run log must show the rehearsal's phase counts exactly: attendance 38,566/38,722; speech 414,129/488,210; role-context 873/873; deputy 1,861/3,130; "0 created, 3 speaker rows updated, 0 refused unions"; "Mdm Speaker rows unlinked" listing exactly speech ids 1201718, 1183545, 1215656, 1215654 and 1221834; and "step committed once". Any other figure means stop and roll back.
4. `drive.py production check h` must show links changed 0 and 0; links added 416,858 and 38,566; a headline of 564,509 of 578,359 with all rows 624,332; and P12 89,536 of 90,511, P13 134,660 of 137,182, P14 208,563 of 210,646. The speech links added outside ids 1,098,900 and up must be exactly ids 999,177 to 999,205.
5. `compare_pair.py h rehearsal3 production` must print IDENTICAL for h, h_att and h_person.
6. `trace_speaker_links.py` on production after h must report 0 stale.

## Follow-ups (not blocking)

1. Speaker-label misprints. Leave a "Mr Speaker" or "Mdm Speaker" row unlinked when the report's last chair annotation before it names a Deputy Speaker with no Speaker annotation since, or when the next speaker opens by addressing the Deputy Speaker. This needs an ADR 0002 note and a sweep over all parliaments, since the same class sits in the pre-2012 headline links. About 8 new rows are listed above.
2. The 5 "Mdm Speaker" rows could link to Jessica Tan Soon Neo if the owner accepts a written ADR 0002 rule for misprinted chair titles: one woman in a chair role that day, surrounded by her own labelled rows. Until then null is right. The 2 pre-2012 honorific contradictions ("Mdm Speaker" to Abdullah Bin Tarmugi, "Mr Chairman" to Indranee Rajah) belong to the same review.
3. Align ADR 0002's "unless the report shows the woman taking part" with the code, or the code with the ADR. Today 143 Parliament 14 rows link to de Souza in reports where Jessica Tan appears, all correct by the "Mr" label.
4. Step k: report "[Deputy Speaker" as 77 rows, not 16 (risk 11). Explain the P12 shortfall from 99.1% by the Chairman and that noise, and describe Lee Li Lian's 6 rows as listed in the attendance list with `is_present` false.
5. Parser: stage lines after a Committee of Supply suspension are attributed to "Mr Speaker". This is a step e behaviour shared with older reports, and it stays in the denominator under ADR 0001.

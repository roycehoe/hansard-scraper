# Data Dictionary

Covers every parliamentary record published by SPRS, from the colonial Legislative Assembly through the present Parliament, including pre-independence proceedings when Singapore was part of Malaya.

Each record is one parliamentary item — a question, a debate topic, a bill reading, a ministerial statement — identified by parliament number, sitting date, and a report ID. Records are parsed into individual speeches attributed to named speakers.

For HTML artifact details and parsing edge cases, see [parsing.md](parsing.md).

---

## Data model

```
Sitting (one day's session)
  └── Attendance  (one row per person listed in PRESENT/ABSENT)

Report (one parliamentary item within a sitting)
  └── Speech      (one utterance by one speaker)

Person (one row per individual)
  └── Speaker    (one row per person per parliament)
```

`Report` and `Sitting` share `sitting_date`, `parliament_number`, and `volume_number` as natural join keys. `Speech.speaker_id` links to `Speaker.id` where the match has been resolved.

The sitting API also returns nested list data (PTBA, debate sections, annexures, vernacular files, absence-to-brief records). This data is stored as serialised JSON columns directly on `Sitting` (`ptba_list`, `sections`, `annexures`, `vernaculars`, `a2b`) for record purposes and is not normalised into separate tables.

---

## Tables

### Report

One row per parliamentary item. A report is the smallest unit of parliamentary business — a single oral question, a single bill reading, a single ministerial statement. Multiple reports belong to the same sitting.

| Field | Type | Meaning |
|---|---|---|
| `parliament_number` | int | Parliament session number. 0 = colonial era (1955–1963). |
| `volume_number` | int | Hansard volume number. Volumes span multiple sessions. |
| `sitting_number` | int | Which sitting within the session. From the search hit, or, where the hit has none (older system, 2003 to 2011), from the `Sitting No` line of the report's header table. |
| `sitting_date` | datetime | Date of the sitting. |
| `speech_number` | int | Sequential number of this item within the sitting (the `sno` field from the API). The 1,691 rows added on 13 October 2026 (refetch) store `sno` as the position within their monthly search window, not the global position, so `sno` is not comparable across those rows and the earlier ones. |
| `report_id` | str | The SPRS identifier for this report. Unique in `Report`; the raw `HansardWebsiteResponse` table keeps every search hit, so it can hold the same id twice. |
| `report_type` | str | Category of parliamentary business. See [Report types](#report-types) below. |
| `title` | str | Cleaned title. Mojibake corrected; HTML entity artifacts and tags stripped; trimmed; a title repeated around commas keeps one copy. |
| `original_title` | str | Title exactly as received from the API. |
| `subtitle` | str | Parenthetical subtitle if present, e.g. `(in Malay)` or `(Continued)`. |
| `markdown_content` | str | HTML content converted to clean markdown. `NULL` if the API returned no HTML. |
| `content` | str | Raw HTML from the API, stored exactly as received. For the older system (sittings before 10 September 2012, `report_version` sprs2) it is the API's `htmlContent`; for the newer system (sprs3) it is `resultHTML.content`. Newer-system `atbp` records have no text and keep it `NULL`; see [ADR 0003](adr/0003-newer-system-raw-mapping.md). |
| `report_version` | str | `sprs2` for the older SPRS system, `sprs3` for the newer one. The parser branches on it. |

### Speech

One row per individual utterance within a report. Speeches are extracted from `markdown_content` by detecting bold speaker names (`**Name:**`).

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Position of this speech within the report, starting from 0. |
| `speaker` | str | Speaker name as it appears in the transcript, with title prefix stripped. `NULL` if attribution failed. |
| `transcript` | str | Text of the speech in markdown. |
| `report_id` | int | FK → `Report.id`. |
| `speaker_id` | int | FK → `Speaker.id`. `NULL` where the match has not been resolved. |

### Sitting

One row per sitting date. A sitting is a full day of parliamentary proceedings, encompassing multiple reports. Fields are `NULL` for formats that do not carry them (old vs new API format; see [parsing.md](parsing.md)).

| Field | Type | Meaning |
|---|---|---|
| `parlement_no` | int | Parliament number. Intentional typo from the API (`parlimentNO`). |
| `session_no` | int | Session number within the parliament. For an older-format sitting, read from the header table of its HTML, because the response leaves it out. |
| `volume_no` | int | Hansard volume number. |
| `sitting_no` | int | Sitting number within the session. Read from the header table of the HTML where the older-format response leaves it out. |
| `sitting_date` | str | Date string as returned by the API. |
| `online_pdf_file_name` | str | Filename of the online PDF for this sitting. |
| `html_full_content` | str | Raw HTML of the full sitting proceedings. `NULL` from 10 September 2012: the newer system serves none. |
| `ptba_from` | str | PTBA date range start (old format). |
| `ptba_to` | str | PTBA date range end (old format). |
| `part_session_str` | str | Part/session label string (new format only). |
| `start_time_str` | str | Start time of the sitting (new format only). |
| `speaker` | str | Speaker of the House for that sitting (new format only). |
| `attendance_preview_text` | str | Preview text for the attendance section (new format only). |
| `ptba_preview_text` | str | Preview text for the PTBA section (new format only). |
| `atb_preview_text` | str | Preview text for the ATB section (new format only). |
| `date_to_display` | str | Display-formatted date string (new format only). |
| `pdf_notes` | str | PDF notes (new format only). |
| `wa_text` | str | Written answers text (new format only). |
| `location_text` | str | Location of the sitting, e.g. `"in contemporaneous communication"` (new format only). |
| `att_start_pg_no` | int | Attendance start page number (new format only). |
| `ptba_start_pg_no` | int | PTBA start page number (new format only). |
| `atbp_start_pg_no` | int | ATBP start page number (new format only). |
| `member_id` | str | Member ID (old format only). |
| `report_type` | str | Report type string (old format only). |
| `portfolio` | str | Portfolio (old format only). |
| `member_name` | str | Member name (old format only). |
| `report_version` | str | Report version (old format only). |
| `report_start_col` | str | Report start column (old format only). |
| `report_end_col` | str | Report end column (old format only). |
| `title` | str | Title (old format only). |
| `column_start` | str | Column start (old format only). |
| `report_content` | str | Report content (old format only). |
| `column_end` | str | Column end (old format only). |
| `report_id` | str | Report ID (old format only). |
| `score` | str | Search score (old format only). |
| `max_result` | str | Max result (old format only). |
| `sno` | str | Sequential number (old format only). |
| `full_content_flag` | str | Full content flag (old format only). |
| `from_month` | str | From month (old format only). |
| `from_day` | str | From day (old format only). |
| `from_year` | str | From year (old format only). |
| `html_content` | str | HTML content fragment (old format only). |
| `subtitle` | str | Subtitle (old format only). |
| `content` | str | Content (old format only). |
| `mp_names` | str | MP names string (old format only). |
| `html_file_name` | str | HTML filename (old format only). |
| `ver_pdf` | str | Verified PDF flag (old format only). |
| `foot_notes` | str | Footnotes (old format only). |
| `foot_note_question` | str | Footnote question (old format only). |
| `foot_note_questions` | str | Footnote questions (old format only). |
| `foot_note` | str (JSON) | Footnote list, serialised (old format only). |
| `atbp_list` | str (JSON) | Absence-to-brief-permitted records, serialised (old format only). |
| `ptba_list` | str (JSON) | Permissions to be absent, serialised from `ptbaList` in the API response. |
| `attendance_list` | str (JSON) | Attendance list, serialised from `attendanceList` in the API response. The source of `Attendance` rows from 10 September 2012. |
| `pdf_nodes` | str | PDF nodes (old format only). |
| `clarification_text` | str | Clarification text (old format only). |
| `clarification_title` | str | Clarification title (old format only). |
| `clarification_sub_title` | str | Clarification subtitle (old format only). |
| `question_count` | str | Question count (old format only). |
| `markdown_content` | str | Full sitting HTML converted to markdown. Used to parse attendance before 10 September 2012; `NULL` after. |
| `sections` | str (JSON) | Debate sections from `takesSectionVOList`, serialised. New format only. |
| `annexures` | str (JSON) | Annexure file references from `annexureList`, serialised. New format only. |
| `vernaculars` | str (JSON) | Vernacular speech files from `vernacularList`, serialised. New format only. |
| `a2b` | str (JSON) | Absence-to-brief records from `a2bList`, serialised. New format only. |

### Attendance

One row per person per sitting, parsed from the PRESENT/ABSENT sections of `Sitting.markdown_content` before 10 September 2012 and from the structured `Sitting.attendance_list` from that date.

| Field | Type | Meaning |
|---|---|---|
| `speaker_name` | str | The registry name where the attendance name resolves to a `Speaker` row at build time, otherwise the name as listed after title stripping. |
| `is_present` | bool | `True` = present, `False` = absent. |
| `location_name` | str | The constituency in parentheses after the name, in every era, spelled as the Elections Department spells it: `data/constituency_names.json` replaces typos and variant spellings, and seat types ("Nominated Member", "ex-officio") and any other bracket text stay as printed. The newer API's `locationName`, which marks where a member sat during a hybrid sitting, stays inside `Sitting.attendance_list`. |
| `speaker_id` | int | FK → `Speaker.id`. `NULL` where the match has not been resolved. |

### Speaker

Identities scraped from parliament.gov.sg, plus the colonial Legislative Assembly list (`data/colonial_la_members.json`) and the heads of state (`data/heads_of_state.json`). One row per person per parliament — the same person appears multiple times across parliaments, and `person_id` groups those rows. The name "Speaker" is used because the table includes colonial Legislative Assembly members who were not MPs, and Governors, the Yang di-Pertuan Negara and Presidents, who are not members at all.

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Name without title prefix. |
| `party` | str | Political party, one value per Membership. It is the party on the ballot at the last election, general or by-election, that seated the member in it. On the 1955 to 1965 Assembly rows, Speakers and nominated members hold `Non-partisan` and ex-officio officials hold `Colonial Government`; scraped nominated members keep the source value (`Nominated Member of Parliament` on 125 rows, `NA` on 2). The apostrophe is always straight. parliament.gov.sg gives one party per person, so `data/speaker_overrides.json` (`party_overrides`) and `data/colonial_la_members.json` correct it per row. The switch history of a hand-typed row is in the `comments` field of `data/colonial_la_members.json`; the apply script does not write `speaker.comments`. |
| `parliament_number` | int | Parliament they served in. |
| `is_legislative_assembly` | bool | `True` on a row that holds a Legislative Assembly membership (1955 to 1965). parliament.gov.sg flags a person, not a row, so `data/speaker_overrides.json` corrects it per row. |
| `comments` | str | Footnote annotations from the source page, e.g. appointment dates or name changes. |
| `is_member` | bool | `False` for heads of state, who speak in the House (the Address) but are not members. |
| `person_id` | int | FK → `Person.id`. Set for every row by `populate_persons`. |

### Person

One row per individual, grouping the per-parliament `Speaker` rows. Derived and rebuildable: rows join on identical names, then on names equal after title and inversion normalisation, subject to the hand decisions in `data/person_decisions.json` (`merge`, `distinct` and `name` entries with a cited source). A person holds at most one speaker row per parliament.

| Field | Type | Meaning |
|---|---|---|
| `canonical_name` | str | Display name in "Given Surname" order. Stage 9 takes the most common spelling among the person's speaker rows, inverts a comma form ("Rajaratnam, S" becomes "S Rajaratnam"), and drops honorifics and the decorations BPM and BBM. A `merge` or `name` decision gives the name instead. `speaker.name` keeps the source form. A rerun of stage 9 renames existing persons. |
| `basis` | str | Which rule formed the group: `auto:exact`, `auto:normalised`, `review:merge` or `single`. |
| `notes` | str | Free text; unused so far. |

---

## Report types

| `report_type` | What it contains |
|---|---|
| `oral-answer` | A question asked in the chamber and answered verbally by a minister. The most common type. |
| `written-answer` | A question submitted in writing with a written ministerial reply. |
| `written-answer-na` | A question for which no written answer was available. |
| `clarification` | A follow-up clarification to an oral or written answer. |
| `motion` | A formal motion debated in the chamber, including adjournment motions. |
| `matter-adj` | An adjournment matter raised at the end of a sitting. |
| `bill` | A bill reading (first, second, or third). Procedural readings are often single-line entries with no speeches. |
| `bill-intro` | A bill introduction notice. No speeches. |
| `ministerial-statement` | A statement delivered by a minister, not in response to a question. |
| `written-statement` | A written ministerial statement tabled in the chamber. |
| `budget` | Budget debates and Committee of Supply proceedings. Also covers procedural budget orders, which have no speeches. |
| `speaker` | Statements or rulings from the Speaker of the House. |
| `deputy-speaker` | Statements from the Deputy Speaker. |
| `personal-explanation` | A personal explanation by an MP. |
| `point-of-order` | A point of order raised during proceedings. |
| `tribute` | A tribute paid to a member or public figure. |
| `president-address` | The President's address to Parliament, and addenda from ministers. |
| `petition` | A petition presented to Parliament. |
| `admin-oaths` | Administration of oaths of office. |
| `obituary-speech` | Obituary speeches for deceased members or public figures. |
| `yang-di-message` | A message from the Yang di-Pertuan Negara (head of state in the colonial/early independence period). |
| `misc` | Miscellaneous parliamentary records that do not fit other categories. |
| `atbp` | Assent to Bills Passed — the formal record of presidential assent. No speeches. |

---

## Key identifiers

**Parliament number** — identifies the parliament session. Parliament 0 is the colonial Legislative Assembly (1955–1963). Numbers increment from 1 at independence.

**Volume number** — Hansard volumes span multiple sessions and are the primary archival unit. They do not reset at each parliament.

**Sitting date** — the natural key for joining `Report` to `Sitting`. A sitting date maps to exactly one `Sitting` row and many `Report` rows.

**Report ID** — the SPRS identifier for an individual item. Stable across pipeline re-runs.

---

## Known limitations

- Records from 1955–1965 cover the colonial Legislative Assembly and the State of Singapore, not the Republic of Singapore Parliament. `Speaker.is_legislative_assembly = True` marks these members.
- 654 records with full text have no speech rows as of 14 October 2026 (552 in Parliaments 0 to 11): mostly budget procedural orders with no named author, annex and appendix documents whose body is a list of PDF links, Committee of Supply openers, and procedural records that name no speaker.
- 131 of 41,809 records have no text (`content` is `NULL`): 106 `atbp` records, whose newer-system bill list is in `sitting.a2b`, and 25 others, 11 of them newer-system ids that SPRS no longer serves.
- Some `Report.title` values contain Windows-1252 mojibake (e.g. `â€™` instead of `'`). `Report.markdown_content` has correct Unicode. Affects ~382 `president-address` titles and ~2,153 `budget` titles. `Report.original_title` is the unmodified raw value.
- Colonial-era records from 1955–1961 (Parliament 0) have no `MPs Speaking` field, so single-speaker attribution fallback cannot apply.
- `Speech.speaker_id` is incomplete for colonial-era and early-parliament records.
- ~3% of modern-era sitting documents have a missing space before the time (e.g. `"The House met at3.00 pm"`). This is a defect in the raw HTML.

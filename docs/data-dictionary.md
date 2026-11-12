# Data Dictionary

Covers every parliamentary record published by SPRS, from the colonial Legislative Assembly through the present Parliament, including the proceedings before independence, when Singapore was a British colony and then part of Malaysia.

Each record is one parliamentary item — a question, a debate topic, a bill reading, a ministerial statement — identified by parliament number, sitting date, and a report ID. Records are parsed into individual speeches attributed to named speakers.

For HTML artifact details and parsing edge cases, see [parsing.md](parsing.md).

---

## Data model

```
Sitting (one day's session)
  └── Attendance  (one row per person listed in PRESENT/ABSENT)

Sitting date
  └── Minutes     (the Votes and Proceedings file of that date)
        └── MinutesDivision (one division the file prints)

Report (one parliamentary item within a sitting)
  ├── Speech      (one utterance by one speaker)
  └── Division    (one recorded vote)
        ├── DivisionVote       (one printed name and the side it stood on)
        └── DivisionPartyCount (members per party and side)

Person (one row per individual)
  └── Speaker    (one row per person per parliament)
```

`Sitting` also has `AttachedFile` rows, one per file it lists. `Report` has `AttachedFilePointer` rows, one per download link in its raw HTML, and a pointer can name its `AttachedFile`.

`Report` and `Sitting` share `sitting_date`, `parliament_number`, and `volume_number` as natural join keys. `Speech.speaker_id` links to `Speaker.id` where the match has been resolved.

The sitting API also returns nested list data (PTBA, debate sections, annexures, vernacular files, absence-to-brief records). This data is stored as serialised JSON columns directly on `Sitting` (`ptba_list`, `sections`, `annexures`, `vernaculars`, `a2b`) for record purposes. Only the annexure and vernacular lists are also stored row by row, in `AttachedFile`.

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
| `sitting_date` | datetime | The report's `sitting_date`, set by the writer that builds the row (see [ADR 0010](adr/0010-speech-sitting-date-set-by-each-writer.md)). Never `NULL`. |
| `report_type` | str | The report's `report_type`, set by the writer that builds the row (see [ADR 0014](adr/0014-speech-report-type-set-by-each-writer.md)). Never `NULL`. |
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
| `speaker_name` | str | The registry name where the attendance name resolves to a `Speaker` row at build time, otherwise the name as listed after title stripping. A list line that names no member (a heading, a table row, procedural text, a wrapped office title) gets no row, and a member listed twice in a sitting has one row, the present one. |
| `is_present` | bool | `True` = present, `False` = absent. |
| `location_name` | str | The constituency in parentheses after the name, in every era, spelled as the Elections Department spells it: `data/constituency_names.json` replaces typos and variant spellings, and seat types printed in place of a constituency ("Nominated Member", "ex-officio") and any other bracket text stay as printed. A "GRC" suffix is dropped, since the Elections Department leaves it out of the division's name. The newer API's `locationName`, which marks where a member sat during a hybrid sitting, stays inside `Sitting.attendance_list`. |
| `speaker_id` | int | FK → `Speaker.id`. `NULL` where the match has not been resolved. |

### Speaker

Identities scraped from parliament.gov.sg, plus the colonial Legislative Assembly list (`data/colonial_la_members.json`) the heads of state (`data/heads_of_state.json`) and the members the scrape omits (`data/unscraped_members.json`). One row per person per parliament — the same person appears multiple times across parliaments, and `person_id` groups those rows. The name "Speaker" is used because the table includes colonial Legislative Assembly members who were not MPs, and Governors, the Yang di-Pertuan Negara and Presidents, who are not members at all.

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Name without title prefix. |
| `party` | str | Political party, one value per Membership. It is the party on the ballot at the last election, general or by-election, that seated the member in it. On the 1955 to 1965 Assembly rows, Speakers and nominated members hold `Non-partisan` and ex-officio officials hold `Colonial Government`; scraped nominated members keep the source value (`Nominated Member of Parliament` on 125 rows, `NA` on 2). The apostrophe is always straight. parliament.gov.sg gives one party per person, so `data/speaker_overrides.json` (`party_overrides`) and `data/colonial_la_members.json` correct it per row. The switch history of a hand-typed row is in the `comments` field of `data/colonial_la_members.json`; the apply script does not write `speaker.comments`. |
| `parliament_number` | int | Parliament they served in. Parliament 0 is the Legislative Assembly (1955 to 1965): a member who sat only in the Assembly, and the Governors before 1959, have a Parliament 0 row. A member who sat in both the Assembly and Parliament 1 has one row, in Parliament 1. |
| `is_legislative_assembly` | bool | `True` on a row that holds a Legislative Assembly membership (1955 to 1965). parliament.gov.sg flags a person, not a row, so `data/speaker_overrides.json` corrects it per row. |
| `comments` | str | Footnote annotations from the source page, e.g. appointment dates or name changes. |
| `is_member` | bool | `False` for heads of state, who speak in the House (the Address) but are not members. |
| `person_id` | int | FK → `Person.id`. Set for every row by `populate_persons`. |

### Person

One row per individual, grouping the per-parliament `Speaker` rows. Derived and rebuildable: rows join on identical names, then on names equal after title and inversion normalisation, subject to the hand decisions in `data/person_decisions.json` (`merge`, `distinct` and `name` entries with a cited source). A person holds at most one speaker row per parliament.

| Field | Type | Meaning |
|---|---|---|
| `canonical_name` | str | Display name in "Given Surname" order. Stage 9 takes the most common spelling among the person's speaker rows, inverts a comma form ("Rajaratnam, S" becomes "S Rajaratnam"), and drops honorifics and the decorations BPM and BBM. A `merge` or `name` decision gives the name instead. `speaker.name` keeps the source form. A rerun of stage 9 renames existing persons. |
| `basis` | str | Which rule formed the group: `auto:exact`, `auto:normalised`, `review:merge` or `single`. Stage 9 recomputes it on every run. |
| `notes` | str | Free text; unused so far. |

### PersonNameSpelling

One row per person and spelling in a spelling note. Stage 9 loads it from `data/person_name_spellings.json`, and the table holds what the file holds. See [ADR 0017](adr/0017-elected-members-take-the-elections-departments-spelling.md).

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Order within the person. Unique with `person_id`. |
| `spelling` | str | The spelling as its source prints it. Unique with `person_id`. |
| `kind` | PersonNameSpellingKind | `CANONICAL` for the row that equals `person.canonical_name`, `OTHER_SPELLING`, `TRANSLITERATION`, or `OTHER_NAME` for a printed name that is not a spelling of it. |
| `note` | str | The sentence the person page shows. Each source is a `[name](link)` link to an https address or a `/reports/` page. |
| `person_id` | int | FK → `Person.id`. |

### AttachedFile

One row per file a sitting lists, read from `sitting.annexures` and `sitting.vernaculars`. A list entry with the same kind, title and printed path as an earlier one is stored once, keeping the lowest SPRS file id. See [ADR 0020](adr/0020-attached-file-pointers.md).

| Field | Type | Meaning |
|---|---|---|
| `kind` | AttachedFileKind | `ANNEX` for an annexure entry, `VERNACULAR` for a vernacular entry. Unique with `sitting_id` and `sprs_file_id`. |
| `sprs_file_id` | int | The entry's `annexureID` or `vernacularID`. |
| `printed_title` | str | The title as the list prints it. |
| `printed_file_path` | str | The path as the list prints it, under `solr_files/`. |
| `file_name` | str | The file name as the list prints it. |
| `section_type` | str | The annexure entry's `sectionType`. `NULL` on a vernacular entry and where the entry has none. |
| `download_value` | str | The part of the path after `solr_files/`, which is the `value` of the file's download address. `NULL` for the placeholder `vernacular-null`, which is the source's word for no file. |
| `sitting_id` | int | FK → `Sitting.id`. |

### AttachedFilePointer

One row per download link in a report's raw HTML, numbered in reading order. The link text and address are stored as printed. The speech row and the listed file are optional ties, set by `scripts/apply_attached_files.py` and by the daily refresh. See [ADR 0020](adr/0020-attached-file-pointers.md).

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | The link's position in the report, from 1. Unique with `sprs_report_id`. |
| `printed_text` | str | The link text as printed. |
| `href` | str | The link's `href` as printed. |
| `shape` | AttachedFilePointerShape | The form of the address: `DATED` (a dated folder and an `annex-` or `vernacular-` name), `PDFS` (under `PDFs/`) or `SECTION_FILE` (a numbered section file). |
| `download_value` | str | The address after `download?value=`. `NULL` for the placeholder `vernacular-null`. |
| `speech_ordinal` | int | The `speech.ordinal` of the row that holds the link's words, in the same report. `NULL` where the words cannot be matched to exactly as many rows as the report's text has occurrences. It is a position, not a foreign key, so a write that renumbers speech rows has to run `scripts/apply_attached_files.py` again. |
| `paragraph_tie_rule` | ParagraphTieRule | How sure the paragraph tie is: `ONLY_OCCURRENCE`, `EVERY_OCCURRENCE_A_LINK` or `OCCURRENCE_BESIDE_PLAIN_TEXT`. `NULL` when `speech_ordinal` is. |
| `sprs_report_id` | str | FK → `Report.report_id`. |
| `attached_file_id` | int | FK → `AttachedFile.id`. Set when exactly one stored file has the pointer's `download_value`, otherwise `NULL`. |

### LeavePeriod

One row per leave period. The permission list prints a leave again at every sitting it covers, so a period holds many printings. A printing with a name and a start date joins the period with the same name (spacing and case folded), start date and end date. A printing with no name or no start date is a period of its own.

| Field | Type | Meaning |
|---|---|---|
| `period_key` | str | Unique. The folded name, the start date and the end date, or `entry|sitting id|ordinal` for a printing with no name or no start date. |
| `name` | str | The name of the first printing of the period: the printed name, or the name carried from the row above. NULL when the printing has none. |
| `start_date` | date | The first day of the leave. NULL when the entry's dates were not read. |
| `end_date` | date | The last day of the leave. NULL for an entry that gives no end ("Till further notice" and a start date with no end) and when the dates were not read. |
| `end_text` | str | The words the structured list prints in place of an end date ("Till further notice"). Never read as a date. NULL in the older sections. |

### LeavePeriodPrinting

One row per date a permission entry prints at a sitting. A line that prints three dates makes three rows. Sittings from 10 September 2012 take their rows from the structured permission list (`Sitting.ptba_list`). Earlier sittings take them from the permission section of `Sitting.markdown_content`, read by `services/leave_section.py`.

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Order of the printing in its sitting, counted by printing and not by line. Unique with `sitting_id`. |
| `sitting_date` | date | The date of the sitting that printed the entry. |
| `printed_name` | str | The name as printed, with its title, up to the constituency bracket. NULL for a printed blank and for a line whose name cannot be trusted. |
| `carried_name` | str | The printed name of the nearest named row above, for a row with a blank name. Never set beside `printed_name`. |
| `printed_from` | str | The words the date reader read for the start, after the misprint list of `data/leave_date_misprints.json`. In the older sections it is NULL where the misprint list changed those words, and for an `UNREAD` entry. For a single day or a day list it holds the matched day item and `printed_to` is NULL, and for a duration or an entry with a start only it holds the start date's words. |
| `printed_to` | str | The words the date reader read for the end, on the same terms as `printed_from`. A dash in the To column of a table is kept as printed. |
| `printed_line` | str | The whole line of an older section as printed, with wrapped lines joined by one space. NULL for the structured list. |
| `printed_heading_from` | str | The heading printed over the From column: the structured list's heading, or the first year group of a table heading in the older sections. NULL elsewhere. |
| `printed_heading_to` | str | The heading over the To column, on the same terms. |
| `office_printed` | str | The office as printed. See `office_source`. It is the office at the sitting that printed the list, which may differ from the office held during the leave. |
| `entry_format` | LeaveEntryFormat | `STRUCTURED_LIST`, `PROSE_RANGE`, `PROSE_SINGLE_DAY`, `PROSE_DAY_LIST`, `PROSE_DURATION`, `PROSE_MIXED`, `TABLE_ROW`, or `UNREAD` for an entry no rule reads. |
| `name_source` | LeaveNameSource | `PRINTED`, `CARRIED_FROM_ROW_ABOVE` or `NONE`. |
| `year_source` | LeaveYearSource | `NEAREST_TO_SITTING` for a printed day and month placed in the year nearest the sitting, `PRINTED_IN_ENTRY` for a year the entry prints, `PRINTED_COLUMN_HEADING` for a table row placed in a year of its heading. NULL when no dates were read. |
| `speaker_link_source` | LeaveSpeakerLinkSource | `ROSTER_NAME` for a name that equals a roster name of the sitting's Parliament once the title is dropped, or `SITTING_ATTENDANCE_ENTRY` for a name the sitting's attendance entries give to one Member. NULL when no link was made. |
| `office_source` | LeaveOfficeSource | `PRINTED_ON_ENTRY` for an office the entry's own line prints, `ATTENDANCE_LIST` for the office the sitting's attendance entry prints for the linked Member. NULL when none. |
| `is_covering_sitting` | bool | Whether the printing's dates cover its own sitting date. NULL when no start date was read. |
| `sitting_id` | int | FK → `Sitting.id`. |
| `leave_period_id` | int | FK → `LeavePeriod.id`. |
| `speaker_id` | int | FK → `Speaker.id`. NULL when no link was made. |

### SeatHolding

One row per Member and division, built from the attendance rows that have a `speaker_id` and a constituency label. The labels `Nominated Member`, `Nominated`, `Non-Constituency Member`, `ex-officio` and `Acting` are seat types and make no row. The dates bound the Member's sittings in the division. They do not show an unbroken term, and `sitting_count` counts the sittings in between.

| Field | Type | Meaning |
|---|---|---|
| `division_key` | str | The label folded: separators to one space, a trailing GRC or SMC dropped, lower case. Unique with `speaker_id`. |
| `location_name` | str | The label as printed at the Member's first sitting in the division. |
| `first_sitting_date` | date | The Member's first sitting with this division. |
| `last_sitting_date` | date | The Member's last sitting with this division. |
| `sitting_count` | int | The number of distinct sittings with this division. |
| `speaker_id` | int | FK → `Speaker.id`. |

### SittingSpan

One row per Member and Parliament (one `Speaker` row), built from the attendance rows that have a `speaker_id`. The dates are the first and last sitting whose attendance list names the Member, present or absent. They are the sittings listed in the record and not a term of office: a Member can sit before or after the sittings the lists name, and `sitting_count` counts only the sittings listed in between. A Member with no attendance row has no span.

| Field | Type | Meaning |
|---|---|---|
| `first_sitting_date` | date | The first sitting whose attendance list names the Member. |
| `last_sitting_date` | date | The last sitting whose attendance list names the Member. |
| `sitting_count` | int | The number of distinct sittings whose attendance list names the Member. |
| `speaker_id` | int | FK → `Speaker.id`. Unique. |

### Division

One row per recorded vote. The counts come from the line the Hansard prints ("The House divided: Ayes, 10; Noes, 3") or from a spoken total ("There are 11 Ayes and 3 Noes"), or from a minutes file for a division only the minutes show. `printed_counts` keeps the text the counts were read from. A division with `count_source` MINUTES has no report, no speech row and no `report_division_number`. A division whose record prints no name list has `list_status` NOT_PRINTED.

| Field | Type | Meaning |
|---|---|---|
| `sitting_date` | date | The sitting the vote took place in. |
| `parliament_number` | int | The Parliament of that sitting. |
| `report_division_number` | int | The division's number within its report, in speech order. Unique with `sprs_report_id`. NULL for a minutes-only division. |
| `speech_ordinal` | int | The `speech.ordinal` of the row that prints the counts. NULL for a minutes-only division. |
| `count_source` | DivisionCountSource | `PRINTED_LINE` for a printed counts line, `SPOKEN_TOTAL` for a total spoken in a speech row, `MINUTES` for a division only the minutes show. |
| `printed_counts` | str | The counts as the source prints them. |
| `ayes`, `noes`, `abstentions`, `absent`, `paired` | int | The counts the source gives. NULL where it gives none. |
| `list_status` | DivisionListStatus | `NOT_PRINTED` when the record prints no list, `STORED` when the names were read and add up to the printed count on every side the line prints a count for (Ayes, Noes and Abstentions with no printed count must hold no names; Absent and Paired names under a side with no printed count are stored without a count to check them), `COUNTS_DISAGREE` when they do not (counts and `printed_list` are kept, no vote rows), `LAYOUT_UNREADABLE` when the list's shape is not one the reader handles. |
| `printed_list` | str | The list as printed. NULL when the record prints none. |
| `sprs_report_id` | str | FK → `Report.report_id`. NULL for a minutes-only division. |

### Minutes

One row per sitting date: the Votes and Proceedings file that records what the House did at the sitting, divisions included. The text is kept as the extractor returned it. The daily step also keeps the bytes of each file it fetches, because a new file may later exist only at its live address; the backfill stores none, and its files stay on the build host and in the Internet Archive. `status` is one of `NOT_YET_LISTED` (a sitting with no file listed yet), `LISTED` (the index lists a file and its text is not stored yet), `TEXT_STORED`, `FILE_NOT_FOUND` and `NEEDS_REVIEW` (the file could not be read, or is a Word file; `status_note` says why). Each row comes from the live index page, an Internet Archive capture of the index (`MinutesIndexCapture`, kept as received) or an archived file listing, and `index_source` says which.

| Field | Type | Meaning |
|---|---|---|
| `sitting_date` | date | The sitting. Unique. |
| `printed_label` | str | The index's label for the file, as printed. |
| `printed_parliament` | str | The Parliament the index prints for it, as printed. |
| `file_url` | str | The address of the file. |
| `archive_timestamp` | str | The Internet Archive timestamp of the copy read, where there is one. |
| `file_format` | MinutesFileFormat | `PDF` or `WORD`. |
| `sha256` | str | The SHA-256 of the file's bytes. |
| `size_bytes` | int | The file's size. |
| `file_bytes` | bytes | The file as fetched. Set by the daily step only; `NULL` on a backfill row. |
| `extracted_text` | str | The text the extractor returned, uncleaned. |
| `status_note` | str | Why a file needs review, or another note on the status. |
| `fetched_at` | datetime | When the file was fetched. |
| `status` | MinutesStatus | See above. |
| `index_source` | MinutesIndexSource | `LIVE_PAGE`, `ARCHIVE_INDEX_CAPTURE` or `ARCHIVE_FILE_LISTING`. |
| `index_capture_id` | int | FK → `MinutesIndexCapture.id`, for a row read from a capture. |

### MinutesDivision

One row per division a minutes file prints, from 1 October 2008. Each is paired with the Hansard divisions of its date that have the same Ayes and Noes. `pairing` is one of `PAIRED` (the group has as many Hansard divisions as minutes divisions, and they pair in order), `NO_MATCHING_DIVISION` (no Hansard division has those counts on that date; the row keeps its own minutes-only division), `UNEQUAL_NUMBER` (the two sources hold a different number of divisions with those counts), `TIED` (two reports of the date share a speech number, so the order cannot be trusted) and `ABSTENTIONS_DIFFER` (both print abstentions and they differ). A list whose sides disagree with the printed counts stores no vote rows, and `list_status` says so.

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Order within the file. Unique with `minutes_id`. |
| `printed_counts` | str | The counts as the file prints them. |
| `ayes`, `noes`, `abstentions` | int | The counts. `abstentions` is NULL where none are printed. |
| `printed_list` | str | The list as printed. |
| `list_status` | DivisionListStatus | As on `Division`. |
| `pairing` | MinutesDivisionPairing | See above. |
| `minutes_id` | int | FK → `Minutes.id`. |
| `division_id` | int | FK → `Division.id`: the paired Hansard division, or the minutes-only division the row owns. |

### DivisionVote

One row per printed name in a division's list, from the Hansard (`list_source` HANSARD) or the minutes (`MINUTES`). Rows with `vote_choice` ABSENT or PAIRED are stored because the record prints them, and they are not votes. The party breakdown counts only AYE, NO and ABSTAIN. A printed name links to a `Speaker` only by `name_rule` EXACT, INVERTED, BIN_FREE, SAME_WORDS or HAND_LIST, never by subset, prefix or surname; a name that matches no single Member stays with no link. `party` is the Member's party on the sitting date, and `is_party_uncertain` is true when the party history does not settle it. Spoken corrections to a list are not applied.

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Position in the list. Unique with `division_id` and `list_source`. |
| `printed_name` | str | The name as printed. |
| `vote_choice` | DivisionVoteChoice | `AYE`, `NO`, `ABSTAIN`, `ABSENT` or `PAIRED`. |
| `list_source` | DivisionVoteListSource | `MINUTES` or `HANSARD`. |
| `name_rule` | DivisionVoteNameRule | The rule that linked the name. NULL when there is no link. |
| `party` | str | The party on the sitting date. NULL when there is no link. |
| `is_party_uncertain` | bool | Whether the party on that date is a best reading. |
| `division_id` | int | FK → `Division.id`. |
| `speaker_id` | int | FK → `Speaker.id`. NULL when the name links to no one. |

### DivisionPartyCount

One row per division, side and party: how many Members of the party stood on that side. It is rebuilt from `DivisionVote` rows and counts only AYE, NO and ABSTAIN. A division is counted from its minutes list when that is stored, and from its Hansard list otherwise; `list_source` says which. `party` is NULL for the Members whose party is not known.

| Field | Type | Meaning |
|---|---|---|
| `member_count` | int | Members of the party on that side. |
| `uncertain_member_count` | int | How many of them have `is_party_uncertain` set. |
| `party` | str | The party. NULL when none is known. |
| `list_source` | DivisionVoteListSource | The list the rows came from. |
| `vote_choice` | DivisionVoteChoice | `AYE`, `NO` or `ABSTAIN`. A check constraint refuses any other. |
| `division_id` | int | FK → `Division.id`. Unique with `vote_choice` and `party`. |

---

## Report types

| `report_type` | What it contains |
|---|---|
| `oral-answer` | A question asked in the chamber and answered verbally by a minister. The most common type. |
| `written-answer` | A question filed for written answer, with the written reply. SPRS calls the section "Written Answers to Questions". Before 22 December 1981 it also holds 21 oral questions of 1957 to 1969 that were answered in writing, because Question Time ran out or the minister or the member was absent. 19 of them open "The following Question for Oral Answer stood on the Order Paper"; the other two sit under such an opening in another report of 7 June 1963. |
| `written-answer-na` | A question filed for oral answer that Question Time did not reach, so the minister's reply is printed in writing. SPRS calls the section "Written Answers to Questions for Oral Answer not Answered by End of Question Time". Older-system headers print "Oral Answers to Questions Not Reached" from December 1981 to February 2011 and "... for Oral Answer not Answered by 3.00 pm" (5.00 pm on 14 May 2012) from October 2011. The type starts on 22 December 1981. |
| `clarification` | A clarification spoken in the chamber. Most are an office holder correcting or adding to something said earlier, by them or by a member, in the same sitting or a later one. Of the 54 stored, 4 are members clarifying their own words, 2 are points of order and 1 is the Government Whip on the speaking order. The type starts on 21 November 2011. |
| `motion` | A formal motion debated in the chamber, including adjournment motions. |
| `matter-adj` | An adjournment matter raised at the end of a sitting. |
| `bill` | A bill reading (first, second, or third). Procedural readings are often single-line entries with no speeches. |
| `bill-intro` | A bill introduction notice. No speeches. |
| `ministerial-statement` | A statement delivered by a minister, not in response to a question. |
| `written-statement` | A written correction of an office holder's earlier words, circulated with the leave of the Speaker or Deputy Speaker under Standing Order 29(5). SPRS calls the section "Corrections by Written Statements". Every title reads "Clarification by ...", the same form most `clarification` titles take, so only the type tells a written correction from a spoken one. The type starts on 7 October 2019. |
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

SPRS types 39 reports `oral-answer` that hold no spoken exchange, only a numbered question and its written reply: 29 of 1 June 1998 and 5 of 16 October and 10 November 2003 whose header reads "Oral Answers to Questions Not Reached", and 5 of 16 October 2003 headed "Written Answers to Questions". On 10 November 2003 the question "Internet Chatrooms" is stored twice, and the types are swapped: the written reply (24876) is `oral-answer` and the spoken exchange (24867) is `written-answer-na`. We keep SPRS's types, so the data loss register has no row for them. A change that reclassifies them adds one.

---

## Key identifiers

**Parliament number** — identifies the parliament session. Parliament 0 is the colonial Legislative Assembly (1955–1963). Numbers increment from 1 at independence.

**Volume number** — Hansard volumes span multiple sessions and are the primary archival unit. They do not reset at each parliament.

**Sitting date** — the natural key for joining `Report` to `Sitting`. A sitting date maps to exactly one `Sitting` row and many `Report` rows.

**Report ID** — the SPRS identifier for an individual item. Stable across pipeline re-runs.

---

## Known limitations

- Records from 1955–1965 cover the colonial Legislative Assembly and the State of Singapore, not the Republic of Singapore Parliament. `Speaker.is_legislative_assembly = True` marks these members.
- As of 19 October 2026 every record with text has speech rows. On 14 October 2026, 654 did not.
- 132 of 46,649 records have no text, counted 19 October 2026: 122 with `content` `NULL`, 114 of them `atbp` records whose newer-system bill list is in `sitting.a2b`, and 10 with an empty `content`. 121 of the 132 are newer-system records.
- Some raw titles hold Windows-1252 mojibake (e.g. `â€™` instead of `’`). `Report.title` and `Report.subtitle` are fixed: since 19 October 2026 none holds it. 11 `Report.original_title` values keep it, the 7 `budget` and 4 `president-address` titles rewritten that day. The raw title is in `hansardwebsiteresponse.title`.
- Colonial-era records from 1955–1961 (Parliament 0) have no `MPs Speaking` field, so single-speaker attribution fallback cannot apply.
- `Speech.speaker_id` is incomplete for colonial-era and early-parliament records.
- Hansard name lists are read by position from `report.content`, so lists printed as `<pre>` blocks, as tables and as one name per paragraph are read. A list printed as an image, a bare heading with no names and any other shape stay unread (`LAYOUT_UNREADABLE` or `NOT_PRINTED`). A list whose names do not add up to its printed counts (15 May 1985: 55 names against 56 printed) stores its counts and `printed_list` and no names.
- ~3% of modern-era sitting documents have a missing space before the time (e.g. `"The House met at3.00 pm"`). This is a defect in the raw HTML.

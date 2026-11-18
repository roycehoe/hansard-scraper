# Data dictionary

This dictionary describes the tables, columns, sources, and limits of the parliamentary records published by SPRS, from the colonial Legislative Assembly through the present Parliament, including the proceedings before independence, when Singapore was a British colony and then part of Malaysia.

Each record is one parliamentary item, such as a question, debate topic, bill reading, or ministerial statement, identified by parliament number, sitting date, and report ID. The parser extracts individual speeches and attributes them to named speakers.

For HTML artifacts and parsing edge cases, see [parsing.md](parsing.md).

---

## Data model

The model links sittings to attendance, sitting dates to minutes, reports to speech rows and divisions, and people to their per-parliament rows.

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

The sitting API returns five nested lists: permissions to be absent (PTBA), debate sections, annexures, vernacular files, and absence-to-brief records. `Sitting` keeps them as serialised JSON in `ptba_list`, `sections`, `annexures`, `vernaculars`, and `a2b` for record purposes. The raw `hansardsittingdateresponse` table holds `sections`, `annexures`, `vernaculars`, and `a2b` too, with the same content. Only the annexure and vernacular lists are also stored row by row, in `AttachedFile`.

---

## Tables

The tables below describe parliamentary items, sittings, people, party affiliations, bills, Acts, supplements and listings, parliamentary questions, offices and ministries, report links, attached files, leave, seats, and recorded votes. Every table also has an integer primary key `id`, which the field tables leave out.

### Report

One row per parliamentary item, the smallest unit of parliamentary business: a single oral question, bill reading, or ministerial statement. A sitting holds multiple reports. This entity table extends `HansardWebsiteResponse`, the raw API response table with one row per Hansard entry, and has a one-to-many relationship to `Speech`.

| Field | Type | Meaning |
|---|---|---|
| `parliament_number` | int | Parliament session number. 0 = the Legislative Assembly (1955 to 1965). |
| `volume_number` | int | Hansard volume number. Volumes span multiple sessions. |
| `sitting_number` | int | Sitting number within the session. From the search hit, or, where the hit has none (older system, 2003 to 2011), from the `Sitting No` line of the report's header table. |
| `sitting_date` | datetime | Date of the sitting. |
| `speech_number` | int | Item sequence number within the sitting (the `sno` field from the API). The 1,691 rows added on 13 October 2026 (refetch) store `sno` as the position within their monthly search window, not the global position, so `sno` is not comparable across those rows and the earlier ones. |
| `report_id` | str | The SPRS identifier for this report. Unique in `Report`; the raw `HansardWebsiteResponse` table keeps every search hit, so it can hold the same id twice. |
| `report_type` | str | Category of parliamentary business. See [Report types](#report-types) below. |
| `title` | str | Cleaned title. Mojibake corrected; HTML entity artifacts and tags stripped; trimmed; a title repeated around commas keeps one copy. |
| `title_tsv` | tsvector | The title as a Postgres search vector, `to_tsvector('english', title)`, generated and stored by the database. A generalized inverted index (GIN) serves title search. |
| `original_title` | str | Title exactly as the API returned it. |
| `subtitle` | str | Parenthetical subtitle if present, e.g. `(in Malay)` or `(Continued)`. |
| `markdown_content` | str | HTML content converted to clean markdown. `NULL` if the API returned no HTML. |
| `content` | str | Raw HTML from the API, stored as received except that a NUL byte becomes U+FFFD (`services/hansard_website.py`). For the older system (sittings before 10 September 2012, `report_version` sprs2) it is the API's `htmlContent`; for the newer system (sprs3) it is `resultHTML.content`. Newer-system `atbp` records have no text and keep it `NULL`; see [ADR 0003](adr/0003-newer-system-raw-mapping.md). |
| `report_version` | str | `sprs2` for the older SPRS system, `sprs3` for the newer one. The parser branches on it. |
| `html_file_name` | str | The search hit's `htmlFileName`, SPRS's file name for the report's HTML. NULL where the hit has none. For an older-system report it is the id the topic request sends (`services/hansard_website.py`: `get_topic_id`), with `report_id` as the fallback. |
| `column_start` | int | Start of the printed column range of an older-system report, set by `scripts/apply_column_numbers.py`. |
| `column_end` | int | End of that printed column range, set by `scripts/apply_column_numbers.py`. |

### Speech

One row per utterance within a report. The parser extracts speeches from `markdown_content` by detecting bold speaker names (`**Name:**`).

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Position within the report, starting from 0. |
| `speaker` | str | Speaker name as it appears in the transcript, with title prefix stripped. `NULL` if attribution failed. |
| `transcript` | str | Text of the speech in markdown. |
| `transcript_tsv` | tsvector | The transcript as a Postgres search vector, `to_tsvector('english', transcript)`, generated and stored by the database. A GIN index and two indexes of the Postgres `rum` extension serve word search. |
| `sitting_date` | datetime | The report's `sitting_date`, set by the writer that builds the row (see [ADR 0010](adr/0010-speech-sitting-date-set-by-each-writer.md)). Never `NULL`. This lets a rum index return word matches in date order. |
| `report_type` | str | The report's `report_type`, set by the writer that builds the row (see [ADR 0014](adr/0014-speech-report-type-set-by-each-writer.md)). Never `NULL`. This lets both rum indexes filter word matches by type. |
| `report_id` | int | FK → `Report.id`. |
| `speaker_id` | int | FK → `Speaker.id`. `NULL` where the match has not been resolved. Populated in stage 8. |
| `kind` | SpeechKind | `SpeechKind`, Postgres type `speechkind`: `SPEECH`, `PROCEDURAL`, `CHAMBER_EVENT`, `EDITORIAL_NOTE`, `DOCUMENT_TEXT`, `HEADING`, or `UNCLASSIFIED`, saying what the row's text is. See [ADR 0009](adr/0009-speech-kind-column.md). |
| `column_start` | int | Printed column the row starts in, kept as printed even when it is a likely misprint. |
| `column_note` | ColumnNote | `ColumnNote`, Postgres type `columnnote`. With `column_suggested`, carries the reading of the printed column: a likely misprint and the column the marker sequence suggests, a speaker named in the column before, or a marker printed with the letter l for the digit 1. |
| `column_suggested` | int | The column the marker sequence suggests for a likely misprint; see `column_note`. |

### ReportAsker

One row per asker of a parliamentary question in a report.

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Order of first appearance. Unique with `report_id`. |
| `printed_name` | str | Name as the record prints it. |
| `source` | ReportAskerSource | `ReportAskerSource`, Postgres type `reportaskersource`, saying which rule found the name. |
| `reader_printed_name` | str | Member who read out a question that stood in an absent member's name, otherwise NULL. |
| `report_id` | int | FK → `Report.id`. |
| `speaker_id` | int | FK → `Speaker.id`, NULL when the printed name resolves to no single Membership. |
| `reader_speaker_id` | int | FK → `Speaker.id`, for the reader. |

### ReportParticipant

One row per person and role in a parliamentary question report, so a member who holds two roles has two rows.

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Unique with `report_id`. |
| `role` | ParticipantRole | `ParticipantRole`, Postgres type `participantrole`. |
| `role_source` | ParticipantRoleSource | `ParticipantRoleSource`, Postgres type `participantrolesource`, saying which rule found the role. |
| `first_ordinal` | int | The `speech.ordinal` of the person's first row in that role. |
| `printed_name` | str | Name as the record prints it. |
| `answering_for_printed` | str | The "for the" or "on behalf of the" bracket as printed, otherwise NULL. |
| `office_printed` | str | Office as its source prints it. |
| `office_class` | OfficeClass | `OfficeClass`, Postgres type `officeclass`. |
| `office_source` | OfficeSource | `OfficeSource`, Postgres type `officesource`, saying which source gave the office. |
| `report_id` | int | FK → `Report.id`. |
| `speaker_id` | int | FK → `Speaker.id`, NULL when the printed name resolves to no single Membership. |

### ReportQuestionState

One row per report and state that the record prints for a parliamentary question, unique on `report_id` and `state`.

| Field | Type | Meaning |
|---|---|---|
| `state` | QuestionState | `QuestionState`, Postgres type `questionstate`. |
| `printed_text` | str | Line or title that shows the state. |
| `first_ordinal` | int | The `speech.ordinal` of the row that prints it, NULL when the title does. |
| `report_id` | int | FK → `Report.id`. |

### ReportPutTo

One row per office a parliamentary question report says the question was put to.

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Unique with `sprs_report_id`. |
| `office_printed` | str | Printed office, indexed. |
| `printed_text` | str | Phrase as printed. |
| `source` | ReportPutToSource | `ReportPutToSource`, Postgres type `reportputtosource`: `ASKED_THE`, `TO_ASK_THE`, or `MISPRINTED_OPENING`. |
| `first_ordinal` | int | The `speech.ordinal` of the row that prints it. |
| `sprs_report_id` | str | FK → `Report.report_id`. |

### ReportLink

One row per printed citation of another report, stored on the report that prints it. Unique on source, target, and link type, with a check that source and target differ. A pair printed from both sides is two rows, and the API returns it once. See [ADR 0019](adr/0019-a-report-link-row-is-one-printed-citation.md).

| Field | Type | Meaning |
|---|---|---|
| `link_type` | ReportLinkType | `ReportLinkType`, Postgres type `reportlinktype`: `CORRECTION`, `REPLY`, or `CONTINUATION`. |
| `rule` | ReportLinkRule | `ReportLinkRule`, Postgres type `reportlinkrule`: the rule that found the one target, `PRINTED_TITLE_ON_PRINTED_DATE`, `SAME_TITLE_ON_PRINTED_DATE`, `LAST_PART_ON_PRINTED_DATE`, `TITLE_KEY_ON_PRINTED_DATE`, or `HAND_KEPT_TITLE_ON_PRINTED_DATE`. |
| `printed_citation` | str | Citation as the record prints it. |
| `source_report_id` | str | FK → `Report.report_id`, the report printing the citation. |
| `target_report_id` | str | FK → `Report.report_id`, the cited report. |

### Sitting

One row per sitting date, covering a full day of proceedings and multiple reports. Fields are `NULL` where the older or newer API format omits them; see [parsing.md](parsing.md). This entity table extends `HansardSittingDateResponse`, the raw API response table with one row per sitting date, handling both old and new API formats with all fields `Optional`. It adds `markdown_content`, parsed from `html_full_content`. Its four JSON TEXT columns (`sections`, `annexures`, `vernaculars`, and `a2b`) are copied from the raw row, where they are null for an older-format sitting.

| Field | Type | Meaning |
|---|---|---|
| `parlement_no` | int | Parliament number. Intentional typo from the API (`parlimentNO`). |
| `session_no` | int | Session number within the parliament. For an older-format sitting, read from the header table of its HTML, because the response leaves it out. |
| `volume_no` | int | Hansard volume number. |
| `sitting_no` | int | Sitting number within the session. Read from the header table of the HTML where the older-format response leaves it out. |
| `sitting_date` | str | Date string as returned by the API. |
| `online_pdf_file_name` | str | Filename of the online PDF for this sitting. |
| `html_full_content` | str | Raw HTML of the full sitting proceedings, with any NUL byte removed by the gateway. `NULL` from 10 September 2012: the newer system serves none. |
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
| `speaker_names` | str | MP names string (old format only), from the API's `mpNames`. |
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

One row per person per sitting, parsed from the PRESENT/ABSENT sections of `Sitting.markdown_content` before 10 September 2012 and from the structured `Sitting.attendance_list` from that date. Stage 7 parses the attendance rows.

| Field | Type | Meaning |
|---|---|---|
| `sitting_id` | int | FK → `Sitting.id`. Unique with `speaker_id`, so a linked member has at most one row per sitting. Rows with no `speaker_id` are not limited. |
| `speaker_name` | str | The registry name where the attendance name resolves to a `Speaker` row at build time, otherwise the name as listed after title stripping. A list line that names no member (a heading, a table row, procedural text, a wrapped office title) gets no row, and a member listed twice in a sitting has one row, the present one. |
| `is_present` | bool | `True` = present, `False` = absent. |
| `location_name` | str | The constituency in parentheses after the name, in every era, spelled as the Elections Department spells it: `data/constituency_names.json` replaces typos and variant spellings, and seat types printed in place of a constituency ("Nominated Member", "ex-officio") and any other bracket text stay as printed. A "GRC" suffix is dropped, since the Elections Department leaves it out of the division's name. The newer API's `locationName`, which marks where a member sat during a hybrid sitting, stays inside `Sitting.attendance_list`. |
| `speaker_id` | int | FK → `Speaker.id`. `NULL` where the match has not been resolved. Set in stage 8. |

### AttendanceOffice

One row per attendance entry that prints an office, built from the entry line by stage 7's reader.

| Field | Type | Meaning |
|---|---|---|
| `office_printed` | str | Office as the line prints it, trimmed of commas, periods, and spaces at its ends. |
| `entry_line_printed` | str | Whole entry line. |
| `office_class` | OfficeClass | `OfficeClass`, Postgres type `officeclass`. |
| `source` | AttendanceOfficeSource | `AttendanceOfficeSource`, Postgres type `attendanceofficesource`: `AFTER_CONSTITUENCY_BRACKET`, `AFTER_NAME_COMMA`, `CHAIR_FORM`, or `BEFORE_EX_OFFICIO_BRACKET`. |
| `extracted_at` | datetime | When the office was extracted. |
| `attendance_id` | int | Unique, an FK → `Attendance.id`. |

### OfficePrintedRange

One row per unbroken run of sittings at which one `Speaker` row's attendance entry printed the same office.

| Field | Type | Meaning |
|---|---|---|
| `office_printed` | str | Printed office. |
| `office_class` | OfficeClass | `OfficeClass`, Postgres type `officeclass`. |
| `sitting_count` | int | Number of sittings in the run. |
| `first_sitting_date` | datetime | First printed date, never an appointment or resignation date. See `docs/office-dates.md`. |
| `last_sitting_date` | datetime | Last printed date, never an appointment or resignation date. See `docs/office-dates.md`. |
| `built_at` | datetime | When the range was built. |
| `speaker_id` | int | FK → `Speaker.id`. |
| `first_attendance_office_id` | int | Unique, an FK → `AttendanceOffice.id`. |
| `last_attendance_office_id` | int | FK → `AttendanceOffice.id`. |

### Ministry

One row per name of `data/ministry_names.json`. The API exposes `ministry.id`, so a rerun keeps the id of a kept name.

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Unique ministry name. |

### OfficeTitleMinistry

One row per printed office title and ministry it names, unique on `office_printed` and `ministry_id`. A row claims no ministry of that name existed.

| Field | Type | Meaning |
|---|---|---|
| `office_printed` | str | Printed title, indexed. |
| `ordinal` | int | Order within the title. |
| `source` | OfficeTitleMinistrySource | `OfficeTitleMinistrySource`, Postgres type `officetitleministrysource`: `CLOSED_LIST_RULE` or `HAND_KEPT_TITLE`. |
| `ministry_id` | int | FK → `Ministry.id`. |

### MinistrySeeAlso

One row per sourced link between two ministries, unique on the pair.

| Field | Type | Meaning |
|---|---|---|
| `note` | str | Link note. |
| `source_url` | str | Source address. |
| `ministry_id` | int | FK → `Ministry.id`. |
| `see_also_ministry_id` | int | FK → `Ministry.id`. |

### Speaker

Everyone who appears in the Hansard record. Identities scraped from parliament.gov.sg, plus the colonial Legislative Assembly list (`data/colonial_la_members.json`), the heads of state (`data/heads_of_state.json`) and the members the scrape omits (`data/unscraped_members.json`). One row per person per parliament. `person_id` groups the same person's rows across parliaments. The name "Speaker" is used because the table includes colonial Legislative Assembly members who were not Members of Parliament (MPs), and Governors, the Yang di-Pertuan Negara, and Presidents, who are not members at all. Rows are keyed by name, party, parliament number, and whether they are a Legislative Assembly member.

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Name without title prefix. |
| `party` | str | Political party, one value per Membership (one person in one Parliament). It is the party on the ballot at the last election, general or by-election, that seated the member in it. On the 1955 to 1965 Assembly rows, Speakers and nominated members hold `Non-partisan` and ex-officio officials hold `Colonial Government`; scraped nominated members keep the source value (`Nominated Member of Parliament` on 125 rows, `NA` on 2). The apostrophe is always straight. parliament.gov.sg gives one party per person, so `data/speaker_overrides.json` (`party_overrides`) and `data/colonial_la_members.json` correct it per row. The switch history of a hand-typed row is in the `comments` field of `data/colonial_la_members.json`; the apply script does not write `speaker.comments`. |
| `parliament_number` | int | Parliament they served in. Parliament 0 is the Legislative Assembly (1955 to 1965): a member who sat only in the Assembly, and the Governors before 1959, have a Parliament 0 row. A member who sat in both the Assembly and Parliament 1 has one row, in Parliament 1. |
| `is_legislative_assembly` | bool | `True` on a row that holds a Legislative Assembly membership (1955 to 1965). parliament.gov.sg flags a person, not a row, so `data/speaker_overrides.json` corrects it per row. |
| `comments` | str | Footnote annotations from the source page, e.g. appointment dates or name changes. |
| `is_member` | bool | `False` for heads of state, who speak in the House (the Address) but are not members. |
| `person_id` | int | FK → `Person.id`. Set for every row by `populate_persons`. |

### PartyAffiliation

One row per party a Membership sat for. The `Speaker` row keeps the ballot party, and this table adds the history. A check constraint requires exactly one source: `source_url` or `source_report_id`.

| Field | Type | Meaning |
|---|---|---|
| `party` | str | The party the Member sat for from `started_on`. |
| `started_on` | date | Date the party affiliation began. |
| `started_on_precision` | DatePrecision | `DatePrecision`, Postgres type `dateprecision`: `DAY` or `MONTH`. A `MONTH` date is stored as the first of the month. |
| `is_started_on_upper_bound` | bool | True when `started_on` is the earliest day a source shows the new party, rather than the day of the change. |
| `event` | str | One plain sentence for the footnote. |
| `source_url` | str | Source page outside the corpus. |
| `source_report_id` | int | FK → `Report.id`, for a Hansard report in the corpus. |
| `speaker_id` | int | FK → `Speaker.id`. |

### Person

One row per individual, grouping the per-parliament `Speaker` rows. Derived and rebuildable: rows join on identical names, then on names equal after title and inversion normalisation, subject to the hand decisions in `data/person_decisions.json` (`merge`, `distinct`, and `name` entries with a cited source). A person holds at most one speaker row per parliament.

| Field | Type | Meaning |
|---|---|---|
| `canonical_name` | str | Display name in "Given Surname" order. Stage 9 takes the most common spelling among the person's speaker rows, inverts a comma form ("Rajaratnam, S" becomes "S Rajaratnam"), and drops honorifics and the decorations BPM and BBM. A `merge` or `name` decision gives the name instead. `speaker.name` keeps the source form. A rerun of stage 9 renames existing persons. |
| `basis` | str | Which rule formed the group: `auto:exact`, `auto:normalised`, `review:merge`, or `single`. Stage 9 recomputes it on every run. |
| `notes` | str | Free text; unused so far. |

### PersonNameSpelling

One row per person and spelling in a spelling note, loaded by stage 9 from `data/person_name_spellings.json`. The table holds what the file holds. See [ADR 0017](adr/0017-elected-members-take-the-elections-departments-spelling.md). The site reads this table.

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Order within the person. Unique with `person_id`. |
| `spelling` | str | The spelling as its source prints it. Unique with `person_id`. |
| `kind` | PersonNameSpellingKind | `CANONICAL` for the row that equals `person.canonical_name`, `OTHER_SPELLING`, `TRANSLITERATION`, or `OTHER_NAME` for a printed name that is not a spelling of it. Postgres type `personnamespellingkind`. |
| `note` | str | The sentence the person page shows. Each source is a `[name](link)` link to an https address or a `/reports/` page. |
| `person_id` | int | FK → `Person.id`. |

### Bill

One row per bill, grouped by `services/bill.py` from the `bill` and `bill-intro` reports and reports of another type whose title ends in Bill and which hold a reading line. Two groups become one bill when a head (not passed, with a first reading) and a tail (passed, without one) are 1 to 800 days apart, their title keys are at least 0.85 similar, no other head claims the tail, and no Supplement entry of the tail's title published between them carries another number.

| Field | Type | Meaning |
|---|---|---|
| `title` | str | Title as the group's last report prints it. |
| `title_key` | str | Lower case letters and digits of the title. |
| `first_sitting_date` | datetime | Bill's first sitting date. |
| `last_sitting_date` | datetime | Bill's last sitting date. |
| `is_passed` | bool | The group closes on a third-reading line. |
| `bill_number` | str | `N/YYYY`, indexed. Supplement number of the one entry whose title key equals the bill's (less a leading "the") and whose window holds one of the bill's first readings: the 35, 18, 9, or 4 days before the listing's publication date by era, or a day either side of the eGazette's printed first reading. Set only when one distinct number matches the bill and that number matches one bill, with the listing preferred where both sources agree. |
| `bill_number_source` | BillNumberSource | `BillNumberSource`, Postgres type `billnumbersource`: `BILLS_SUPPLEMENT_LISTING` or `EGAZETTE_BILLS_SUPPLEMENT`. |
| `bill_class` | BillClass | `BillClass`, Postgres type `billclass`: `SUPPLY` for a supply or appropriation title, `REPEAL` for a repeal title that is not an amendment, otherwise NULL. |
| `act_number` | str | `N/YYYY`. Act number of the Acts Supplement entries whose title key equals a passed bill's and whose publication date falls from one day before to 120 days after the bill's last report. Set only when exactly one distinct Act number matches. It claims that the bill became an Act that was published, whose text the project does not hold, and says nothing about whether the Act is in force. |
| `act_number_source` | ActNumberSource | `ActNumberSource`, Postgres type `actnumbersource`: `ACTS_SUPPLEMENT_LISTING`. |
| `repealed_act_url` | str | Singapore Statutes Online (SSO) page of a repealed, spent, expired, or omitted Act. Set for a passed bill when exactly one distinct SSO code of `RepealedActEntry` rows has the bill's loose title key (status words removed) and fits its dates: an amendment bill must be enacted by its first report's year and repealed on or after its last report; any other bill must be enacted in its first or last report's year. It says only that the bill's title matches an Act SSO lists as repealed, spent, expired, or omitted and that the bill's dates fit that Act's enactment year and life. |
| `repealed_act_url_source` | RepealedActUrlSource | `RepealedActUrlSource`, Postgres type `repealedacturlsource`: `REPEALED_ACTS_LISTING`. |

### BillReport

One row per report of a bill, unique on `bill_id` and `report_id`. A report belongs to one bill, because the grouping reads one title key per report.

| Field | Type | Meaning |
|---|---|---|
| `bill_id` | int | FK → `Bill.id`. |
| `report_id` | int | FK → `Report.id`. |
| `role` | BillReportRole | `BillReportRole`, Postgres type `billreportrole`: `READING` for a report grouped as a reading of the bill, `BUDGET_DEBATE` for a `budget` report (the Budget Statement, a Committee of Supply head, the Estimates) attached to the year's Supply Bill, so a reader can tell a head's debate from a reading. |

### BillKey

One row per bill, giving its lasting key because `bill.id` does not survive a rebuild.

| Field | Type | Meaning |
|---|---|---|
| `bill_key` | str | The SPRS `report_id` of the bill's first `READING` report, ordered by sitting date and then by SPRS id in byte order. A `BUDGET_DEBATE` report never gives it. Unique, an FK → `Report.report_id`. |
| `act_count` | int | Number of distinct Acts with a linked Legislative History entry on the bill, 0 meaning none. The daily job inserts a new bill's row with 0, and a bill the daily job joins a report to without a row gets none. |
| `bill_id` | int | Unique, an FK → `Bill.id`. |

### BillReportSpeaker

One row per Member and report of a bill, unique on `sprs_report_id` and `speaker_id`. It holds SPEECH rows with a `speaker_id` in a report joined to a bill through `billreport`, and no bill reference, so a regroup does not touch it.

| Field | Type | Meaning |
|---|---|---|
| `speech_count` | int | Number of speech rows. |
| `first_ordinal` | int | The `speech.ordinal` of the Member's first SPEECH row in the report. |
| `printed_speaker` | str | That row's label. |
| `sprs_report_id` | str | Indexed FK → `Report.report_id`. |
| `speaker_id` | int | Indexed FK → `Speaker.id`. |

### BillStageLine

One row per printed line and stage that proves a stage of a bill's passage, unique on `sprs_report_id`, `ordinal`, and `stage`. Only a PROCEDURAL or UNCLASSIFIED row proves a stage, and committee stage gets no row.

| Field | Type | Meaning |
|---|---|---|
| `stage` | BillStage | `BillStage`, Postgres type `billstage`: `FIRST_READING`, `SECOND_READING_ORDER`, `SECOND_READING_AGREED`, or `THIRD_READING`. |
| `printed_text` | str | The printed line. |
| `ordinal` | int | The `speech.ordinal` of the row that prints the line. |
| `sprs_report_id` | str | Indexed FK → `Report.report_id`. |

### Act

One row per current Act of the SSO harvest. The Act's text is not stored (`docs/data-loss-register.md`).

| Field | Type | Meaning |
|---|---|---|
| `sso_code` | str | Unique SSO code. |
| `title` | str | Title as the SSO browse page prints it. |

### ActHistoryEntry

One row per entry of an Act's Legislative History, unique on `act_id` and `ordinal`.

| Field | Type | Meaning |
|---|---|---|
| `act_id` | int | FK → `Act.id`. |
| `ordinal` | int | Order within the Act. Unique with `act_id`. |
| `printed_text` | str | Entry as printed, with page-break noise removed. |
| `printed_law_number` | str | Printed law number. |
| `printed_title` | str | Printed title. |
| `printed_bill_number` | str | Only an `N/YY` or `N/YYYY` form, as printed. |
| `first_reading_date` | date | First reading date, NULL where the source prints no usable date. |
| `second_reading_date` | date | Second reading date, NULL where the source prints no usable date. |
| `third_reading_date` | date | Third reading date, NULL where the source prints no usable date. |
| `commencement_date` | date | Commencement date, NULL where the source prints no usable date. |
| `kind` | ActHistoryEntryKind | `ActHistoryEntryKind`, Postgres type `acthistoryentrykind`. |
| `bill_id` | int | FK → `Bill.id`, NULL when no bill matches. |
| `bill_link_source` | BillLinkSource | `BillLinkSource`, Postgres type `billlinksource`, saying which reading date, the looser title rule, or a hand-kept link matched. `SIMILAR_TITLE_READING_DATES` stays a value of the type for rows stored before the similarity rule was removed; `scripts/apply_hand_kept_act_links.py` relabels the eight that need it. |

### BillsSupplementCapture

One row per Internet Archive capture of an SSO Bills Supplement listing page, as received.

| Field | Type | Meaning |
|---|---|---|
| `original_url` | str | Original listing address. |
| `archive_timestamp` | str | Internet Archive timestamp. |
| `capture_url` | str | Unique capture address. |
| `content` | str | Page content as received. |

### BillsSupplementEntry

One row per listing row across the captures, unique on `bill_number` and `link`.

| Field | Type | Meaning |
|---|---|---|
| `printed_title` | str | Title as printed. |
| `printed_number` | str | "Bill N of YYYY" as printed. |
| `link` | str | Link as printed. |
| `pdf_link` | str | PDF link as printed. |
| `pdf_size` | str | PDF size as printed. |
| `bill_number` | str | `N/YYYY`. |
| `publication_date` | date | The link's DocDate. |
| `capture_id` | int | FK → `BillsSupplementCapture.id`. |

### ActsSupplementCapture

One row per Internet Archive capture of an SSO Acts Supplement listing page, as received.

| Field | Type | Meaning |
|---|---|---|
| `original_url` | str | Original listing address. |
| `archive_timestamp` | str | Internet Archive timestamp. |
| `capture_url` | str | Unique capture address. |
| `content` | str | Page content as received. |

### ActsSupplementEntry

One row per listing row across the captures, unique on `act_number` and `link`.

| Field | Type | Meaning |
|---|---|---|
| `printed_title` | str | Title as printed. |
| `printed_number` | str | "Act N of YYYY" as printed. |
| `link` | str | Link as printed. |
| `pdf_link` | str | PDF link as printed. |
| `pdf_size` | str | PDF size as printed. |
| `act_number` | str | `N/YYYY`. |
| `publication_date` | date | First eight digits of the link's DocDate, never the `/Published/` segment, which is a revised-edition date. |
| `capture_id` | int | FK → `ActsSupplementCapture.id`. |

### RepealedActsCapture

One row per Internet Archive capture of the SSO Repealed Acts listing page, as received.

| Field | Type | Meaning |
|---|---|---|
| `original_url` | str | Original listing address. |
| `archive_timestamp` | str | Internet Archive timestamp. |
| `capture_url` | str | Unique capture address. |
| `content` | str | Page content as received. |

### RepealedActEntry

One row per Act across the captures, unique on `sso_code`.

| Field | Type | Meaning |
|---|---|---|
| `printed_title` | str | Title with its `(Repealed)`, `(Spent)`, or `(Omitted)` status as printed. |
| `printed_chapter` | str | "Cap. 2" as printed, NULL where the capture prints no chapter. |
| `link` | str | Link to the Act. |
| `sso_code` | str | Code in the link's path. Unique. |
| `enactment_year` | int | Trailing four digits of the code, NULL where it has none. |
| `repeal_date` | date | The 8 digits after `/Repealed/` in the link. |
| `last_version_date` | date | First eight digits of the link's DocDate. |
| `capture_id` | int | FK → `RepealedActsCapture.id`. |

### EgazetteSupplement

One row per eGazette Bills or Acts Supplement PDF fetched by `scripts/fetch_egazette_supplements.py`. The PDF stays a file outside the repository.

| Field | Type | Meaning |
|---|---|---|
| `url` | str | Unique PDF address. |
| `year` | int | Supplement year. |
| `supplement_kind` | EgazetteSupplementKind | `EgazetteSupplementKind`, Postgres type `egazettesupplementkind`: `BILLS` or `ACTS`. |
| `number` | int | File's number in its year. |
| `file_path` | str | Path to the PDF file. |
| `size_bytes` | int | File size in bytes. |
| `sha256` | str | File hash. |
| `fetched_at` | datetime | When the PDF was fetched. |
| `printed_title` | str | Read from the first pages. |
| `printed_bill_number` | str | Read from the first pages. |
| `bill_number` | str | `N/YYYY`, read from the first pages. |
| `first_reading_date` | date | Read from the first pages. |
| `passing_date` | date | For an Acts Supplement, read from the first pages, NULL where the PDF prints none. |
| `printed_act_number` | str | For an Acts Supplement, read from the first pages, NULL where the PDF prints none. |
| `bill_id` | int | For an Acts Supplement, FK → `Bill.id`. Set when exactly one bill carries its bill number and a third-reading report of that bill falls on the printed passing date. |
| `bill_link_source` | BillLinkSource | `BILL_NUMBER_PASSING_DATE` for that Acts Supplement link. |

### AttachedFile

One row per file a sitting lists, read from `sitting.annexures` and `sitting.vernaculars`. A list entry with the same kind, title and printed path as an earlier one is stored once, keeping the lowest SPRS file id. See [ADR 0020](adr/0020-attached-file-pointers.md). `services/attached_file.py` reads the file entries.

| Field | Type | Meaning |
|---|---|---|
| `kind` | AttachedFileKind | `ANNEX` for an annexure entry, `VERNACULAR` for a vernacular entry. Unique with `sitting_id` and `sprs_file_id`. Postgres type `attachedfilekind`. |
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
| `shape` | AttachedFilePointerShape | The form of the address: `DATED` (a dated folder and an `annex-` or `vernacular-` name), `PDFS` (under `PDFs/`) or `SECTION_FILE` (a numbered section file). Postgres type `attachedfilepointershape`. |
| `download_value` | str | The address after `download?value=`. `NULL` for the placeholder `vernacular-null`. |
| `speech_ordinal` | int | The `speech.ordinal` of the row that holds the link's words, in the same report. `NULL` where the words cannot be matched to exactly as many rows as the report's text has occurrences. It is a position, not a foreign key, so a write that renumbers speech rows has to run `scripts/apply_attached_files.py` again. |
| `paragraph_tie_rule` | ParagraphTieRule | How sure the paragraph tie is: `ONLY_OCCURRENCE`, `EVERY_OCCURRENCE_A_LINK`, or `OCCURRENCE_BESIDE_PLAIN_TEXT`. `NULL` when `speech_ordinal` is. Postgres type `paragraphtierule`. |
| `sprs_report_id` | str | FK → `Report.report_id`. |
| `attached_file_id` | int | FK → `AttachedFile.id`. Set when exactly one stored file has the pointer's `download_value`, otherwise `NULL`. |

### LeavePeriod

One row per leave period, grouping the permission list's repeated printings of that leave at each sitting it covers. A printing with a name and a start date joins the period with the same name (spacing and case folded), start date, and end date. A printing with no name or no start date is a period of its own.

| Field | Type | Meaning |
|---|---|---|
| `period_key` | str | Unique. The folded name, the start date, and the end date, or `entry|sitting id|ordinal` for a printing with no name or no start date. |
| `name` | str | The name of the first printing of the period: the printed name, or the name carried from the row above. NULL when the printing has none. |
| `start_date` | date | The first day of the leave. NULL when the entry's dates were not read. Indexed. |
| `end_date` | date | The last day of the leave. NULL for an entry that gives no end ("Till further notice" and a start date with no end) and when the dates were not read. |
| `end_text` | str | The words the structured list prints in place of an end date ("Till further notice"). Never read as a date. NULL in the older sections. |

### LeavePeriodPrinting

One row per date a permission entry prints at a sitting. A line that prints three dates makes three rows. Sittings from 10 September 2012 take their rows from the structured permission list (`Sitting.ptba_list`). Earlier sittings take them from the permission section of `Sitting.markdown_content`, read by `services/leave_section.py`. A section is a list of entries, a table, or one sentence that grants permission to one Member ("I have granted permission to Dr Chew Chin Han (Tampines) to be absent from the sitting of Parliament today, the 2nd November, 1967").

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Order of the printing in its sitting, counted by printing and not by line. Unique with `sitting_id`. |
| `sitting_date` | date | Date of the sitting that printed the entry. |
| `printed_name` | str | The name as printed, with its title, up to the constituency bracket. In a granting sentence it is the name after "granted permission to", or the bracket's text where the sentence prints the office with the name in a bracket (`the Prime Minister ( Mr Lee Kuan Yew)`). NULL for a printed blank and for a line whose name cannot be trusted. |
| `carried_name` | str | The printed name of the nearest named row above, for a row with a blank name. Never set beside `printed_name`. |
| `printed_from` | str | The words the date reader read for the start, after the misprint list of `data/leave_date_misprints.json`. In the older sections it is NULL where the misprint list changed those words, and for an `UNREAD` entry. For a single day or a day list it holds the matched day item and `printed_to` is NULL, and for a duration or an entry with a start only it holds the start date's words. |
| `printed_to` | str | The words the date reader read for the end, on the same terms as `printed_from`. A dash in the To column of a table is kept as printed. |
| `printed_line` | str | The whole line of an older section as printed, with wrapped lines joined by one space. NULL for the structured list. |
| `printed_heading_from` | str | The heading printed over the From column: the structured list's heading, or the first year group of a table heading in the older sections. NULL elsewhere. |
| `printed_heading_to` | str | The heading over the To column, on the same terms. |
| `office_printed` | str | The office as printed. See `office_source`. It is the office at the sitting that printed the list, which may differ from the office held during the leave. |
| `entry_format` | LeaveEntryFormat | `STRUCTURED_LIST`, `PROSE_RANGE`, `PROSE_SINGLE_DAY`, `PROSE_DAY_LIST`, `PROSE_DURATION`, `PROSE_MIXED`, `TABLE_ROW`, or `UNREAD` for an entry no rule reads. Postgres type `leaveentryformat`. |
| `name_source` | LeaveNameSource | `PRINTED`, `CARRIED_FROM_ROW_ABOVE`, or `NONE`. |
| `year_source` | LeaveYearSource | `NEAREST_TO_SITTING` for a printed day and month placed in the year nearest the sitting, `PRINTED_IN_ENTRY` for a year the entry prints, `PRINTED_COLUMN_HEADING` for a table row placed in a year of its heading. NULL when no dates were read. |
| `speaker_link_source` | LeaveSpeakerLinkSource | `ROSTER_NAME` for a name that equals a roster name of the sitting's Parliament once the title is dropped, or `SITTING_ATTENDANCE_ENTRY` for a name the sitting's attendance entries give to one Member. NULL when no link was made. Never a prefix, word-set, or surname match. |
| `office_source` | LeaveOfficeSource | `PRINTED_ON_ENTRY` for an office the entry's own line prints, `ATTENDANCE_LIST` for the office the sitting's attendance entry prints for the linked Member. NULL when none. |
| `is_covering_sitting` | bool | Whether the printing's dates cover its own sitting date. NULL when no start date was read. |
| `sitting_id` | int | FK → `Sitting.id`. |
| `leave_period_id` | int | FK → `LeavePeriod.id`. |
| `speaker_id` | int | FK → `Speaker.id`. NULL when no link was made. |

### SeatHolding

One row per Member and division, built from the attendance rows that have a `speaker_id` and a constituency label. The labels `Nominated Member`, `Nominated`, `Non-Constituency Member`, `ex-officio`, and `Acting` are seat types and make no row. The dates bound the Member's sittings in the division. They do not show an unbroken term, and `sitting_count` counts the sittings in between.

| Field | Type | Meaning |
|---|---|---|
| `division_key` | str | The label folded: separators to one space, a trailing GRC or SMC dropped, lower case. Unique with `speaker_id`. |
| `location_name` | str | The label as printed at the Member's first sitting in the division. |
| `first_sitting_date` | date | Member's first sitting with this division. |
| `last_sitting_date` | date | Member's last sitting with this division. |
| `sitting_count` | int | Number of distinct sittings with this division. |
| `speaker_id` | int | FK → `Speaker.id`. |

### Division

One row per recorded vote. The counts come from the line the Hansard prints ("The House divided: Ayes, 10; Noes, 3") or from a spoken total ("There are 11 Ayes and 3 Noes"), or from a minutes file for a division only the minutes show. `printed_counts` keeps the text the counts were read from. A division with `count_source` MINUTES has no report, no speech row and no `report_division_number`. A division whose record prints no name list has `list_status` NOT_PRINTED.

| Field | Type | Meaning |
|---|---|---|
| `sitting_date` | date | The sitting the vote took place in. |
| `parliament_number` | int | The Parliament of that sitting. |
| `report_division_number` | int | The division's number within its report, in speech order. Unique with `sprs_report_id`. NULL for a minutes-only division. |
| `speech_ordinal` | int | The `speech.ordinal` of the row that prints the counts. NULL for a minutes-only division. |
| `count_source` | DivisionCountSource | `PRINTED_LINE` for a printed counts line, `SPOKEN_TOTAL` for a total spoken in a speech row, `MINUTES` for a division only the minutes show. Postgres type `divisioncountsource`. |
| `printed_counts` | str | Counts as the source prints them. |
| `ayes`, `noes`, `abstentions`, `absent`, `paired` | int | The counts the source gives. NULL where it gives none. |
| `list_status` | DivisionListStatus | `NOT_PRINTED` when the record prints no list, `STORED` when the names were read and add up to the printed count on every side the line prints a count for (Ayes, Noes, and Abstentions with no printed count must hold no names; Absent and Paired names under a side with no printed count are stored without a count to check them), `COUNTS_DISAGREE` when they do not (counts and `printed_list` are kept, no vote rows), `LAYOUT_UNREADABLE` when the list's shape is not one the reader handles. Postgres type `divisionliststatus`. |
| `printed_list` | str | List as printed. NULL when the record prints none. |
| `sprs_report_id` | str | FK → `Report.report_id`. NULL for a minutes-only division. |

### Minutes

One row per sitting date: the Votes and Proceedings file that records what the House did at the sitting, divisions included. The text is kept as the extractor returned it. The daily step also keeps the bytes of each file it fetches, because a new file may later exist only at its live address; the backfill stores none, and its files stay on the build host and in the Internet Archive. `status` is one of `NOT_YET_LISTED` (a sitting with no file listed yet), `LISTED` (the index lists a file and its text is not stored yet), `TEXT_STORED`, `FILE_NOT_FOUND`, and `NEEDS_REVIEW` (the file could not be read, or is a Word file; `status_note` says why). Each row comes from the live index page, an Internet Archive capture of the index (`MinutesIndexCapture`, kept as received), or an archived file listing, and `index_source` says which. `MinutesIndexCapture` has one row per capture of the Votes and Proceedings index page: `original_url`, `archive_timestamp`, a unique `capture_url`, and the page `content`.

| Field | Type | Meaning |
|---|---|---|
| `sitting_date` | date | The sitting. Unique. |
| `printed_label` | str | The index's label for the file, as printed. |
| `printed_parliament` | str | The Parliament the index prints for it, as printed. |
| `file_url` | str | File address. |
| `archive_timestamp` | str | The Internet Archive timestamp of the copy read, where there is one. |
| `file_format` | MinutesFileFormat | `PDF` or `WORD`. Postgres type `minutesfileformat`. |
| `sha256` | str | The SHA-256 of the file's bytes. |
| `size_bytes` | int | File size. |
| `file_bytes` | bytes | The file as fetched. Set by the daily step only; `NULL` on a backfill row. |
| `extracted_text` | str | Uncleaned text returned by the extractor. |
| `status_note` | str | Why a file needs review, or another note on the status. |
| `fetched_at` | datetime | When the file was fetched. |
| `status` | MinutesStatus | See above. Postgres type `minutesstatus`. |
| `index_source` | MinutesIndexSource | `LIVE_PAGE`, `ARCHIVE_INDEX_CAPTURE`, or `ARCHIVE_FILE_LISTING`. Postgres type `minutesindexsource`. |
| `index_capture_id` | int | FK → `MinutesIndexCapture.id`, for a row read from a capture. |

### MinutesDivision

One row per division a minutes file prints, from 1 October 2008. Each is paired with the Hansard divisions of its date that have the same Ayes and Noes. `pairing` is one of `PAIRED` (the group has as many Hansard divisions as minutes divisions, and they pair in order), `NO_MATCHING_DIVISION` (no Hansard division has those counts on that date; the row keeps its own minutes-only division), `UNEQUAL_NUMBER` (the two sources hold a different number of divisions with those counts), `TIED` (two reports of the date share a speech number, so the order cannot be trusted) and `ABSTENTIONS_DIFFER` (both print abstentions and they differ). A list whose sides disagree with the printed counts stores no vote rows, and `list_status` says so.

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Order within the file. Unique with `minutes_id`. |
| `printed_counts` | str | Counts as the file prints them. |
| `ayes`, `noes`, `abstentions` | int | The counts. `abstentions` is NULL where none are printed. |
| `printed_list` | str | List as printed, from its heading row to the last line before the text that follows it, without page-header lines. A line that holds a digit or a quotation mark is not part of it. |
| `list_status` | DivisionListStatus | As on `Division`. |
| `pairing` | MinutesDivisionPairing | See above. Postgres type `minutesdivisionpairing`. Set by `services/division_pairing.py`. |
| `minutes_id` | int | FK → `Minutes.id`. |
| `division_id` | int | FK → `Division.id`: the paired Hansard division, or the minutes-only division the row owns. |

### DivisionVote

One row per printed name in a division's list, from the Hansard (`list_source` HANSARD) or the minutes (`MINUTES`). Rows with `vote_choice` ABSENT or PAIRED are stored because the record prints them, and they are not votes. The party breakdown counts only AYE, NO and ABSTAIN. A printed name links to a `Speaker` only by `name_rule` EXACT, INVERTED, BIN_FREE, SAME_WORDS or HAND_LIST, never by subset, prefix, or surname; a name that matches no single Member stays with no link. `party` is the Member's party on the sitting date, and `is_party_uncertain` is true when the party history does not settle it. Spoken corrections to a list are not applied.

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Position in the list. Unique with `division_id` and `list_source`. |
| `printed_name` | str | Name as printed. |
| `vote_choice` | DivisionVoteChoice | `AYE`, `NO`, `ABSTAIN`, `ABSENT`, or `PAIRED`. Postgres type `divisionvotechoice`. |
| `list_source` | DivisionVoteListSource | `MINUTES` or `HANSARD`. Postgres type `divisionvotelistsource`. |
| `name_rule` | DivisionVoteNameRule | The rule that linked the name. NULL when there is no link. Postgres type `divisionvotenamerule`. |
| `party` | str | Party on the sitting date. NULL when there is no link. |
| `is_party_uncertain` | bool | Whether the party on that date is a best reading. |
| `division_id` | int | FK → `Division.id`. |
| `speaker_id` | int | FK → `Speaker.id`. NULL when the name links to no one. |

### DivisionPartyCount

One row per division, side, and party: how many Members of the party stood on that side. It is rebuilt from `DivisionVote` rows and counts only AYE, NO and ABSTAIN. A division is counted from its minutes list when that is stored, and from its Hansard list otherwise; `list_source` says which. `party` is NULL for the Members whose party is not known.

| Field | Type | Meaning |
|---|---|---|
| `member_count` | int | Members of the party on that side. |
| `uncertain_member_count` | int | How many of them have `is_party_uncertain` set. |
| `party` | str | The party. NULL when none is known. |
| `list_source` | DivisionVoteListSource | The list the rows came from. |
| `vote_choice` | DivisionVoteChoice | `AYE`, `NO`, or `ABSTAIN`. A check constraint refuses any other. |
| `division_id` | int | FK → `Division.id`. Unique with `vote_choice` and `party`. NULLs are not distinct in that uniqueness rule. |

---

## Report types

`Report.report_type` identifies the kind of parliamentary business.

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
| `atbp` | Assent to Bills Passed, the formal record of presidential assent. No speeches. |

SPRS types 39 reports `oral-answer` that hold no spoken exchange, only a numbered question and its written reply: 29 of 1 June 1998 and 5 of 16 October and 10 November 2003 whose header reads "Oral Answers to Questions Not Reached", and 5 of 16 October 2003 headed "Written Answers to Questions". On 10 November 2003 the question "Internet Chatrooms" is stored twice, and the types are swapped: the written reply (24876) is `oral-answer` and the spoken exchange (24867) is `written-answer-na`. The pipeline keeps SPRS's types, so the data loss register has no row for them. A change that reclassifies them adds one.

---

## Key identifiers

Four identifiers locate records and connect them across tables.

**Parliament number** identifies the parliament session. Parliament 0 is the colonial Legislative Assembly (1955 to 1965). Numbers increment from 1 at independence.

**Volume number**: Hansard volumes span multiple sessions and are the primary archival unit. They do not reset at each parliament.

**Sitting date**: the natural key for joining `Report` to `Sitting`. A sitting date maps to exactly one `Sitting` row and many `Report` rows.

**Report ID**: the SPRS identifier for an individual item. Stable across pipeline re-runs.

---

## Known limitations

Seven limits affect coverage, text, speaker links, and vote lists.

- Records from 1955 to 1965 cover the colonial Legislative Assembly and the State of Singapore, not the Republic of Singapore Parliament. `Speaker.is_legislative_assembly = True` marks these members.
- Every record with text has speech rows (counted on 19 October 2026).
- 132 of 46,649 records have no text, counted on 19 October 2026: 122 with `content` `NULL`, 114 of them `atbp` records whose newer-system bill list is in `sitting.a2b`, and 10 with an empty `content`. 121 of the 132 are newer-system records.
- Some raw titles hold Windows-1252 mojibake (e.g. `â€™` instead of `’`). `Report.title` and `Report.subtitle` hold none (counted on 19 October 2026). 11 `Report.original_title` values keep it: the 7 `budget` and 4 `president-address` titles that the title fix rewrote. The raw title is in `hansardwebsiteresponse.title`.
- `Speech.speaker_id` is incomplete for colonial-era and early-parliament records.
- Hansard name lists are read by position from `report.content`, so lists printed as `<pre>` blocks, as tables and as one name per paragraph are read. A list printed as an image, a bare heading with no names and any other shape stay unread (`LAYOUT_UNREADABLE` or `NOT_PRINTED`). A list whose names do not add up to its printed counts (15 May 1985: 55 names against 56 printed) stores its counts and `printed_list` and no names.
- ~3% of modern-era sitting documents have a missing space before the time (e.g. `"The House met at3.00 pm"`). This is a defect in the raw HTML.

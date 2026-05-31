# Data Dictionary

Covers every parliamentary record published by SPRS, from the colonial Legislative Assembly through the present Parliament, including pre-independence proceedings when Singapore was part of Malaya.

Each record is one parliamentary item — a question, a debate topic, a bill reading, a ministerial statement — identified by parliament number, sitting date, and a report ID. Records are parsed into individual speeches attributed to named MPs.

For HTML artifact details and parsing edge cases, see [parsing.md](parsing.md).

---

## Data model

```
Sitting (one day's session)
  ├── SittingAttendance  (one row per MP)
  ├── SittingPtba        (permissions to be absent)
  ├── SittingSection     (debate sections/questions on the agenda)
  ├── SittingAnnexure    (linked annexure files)
  ├── SittingVernacular  (vernacular speech files)
  └── SittingA2b         (absence-to-brief records)

Report (one parliamentary item within a sitting)
  └── Speech             (one utterance by one MP)

Mp (one row per MP per parliament)
```

`Report` and `Sitting` share `sitting_date`, `parliament_number`, and `volume_number` as natural join keys. `Speech.mp_id` links to `Mp.id` where the match has been resolved.

---

## Tables

### Report

One row per parliamentary item. A report is the smallest unit of parliamentary business — a single oral question, a single bill reading, a single ministerial statement. Multiple reports belong to the same sitting.

| Field | Type | Meaning |
|---|---|---|
| `parliament_number` | int | Parliament session number. 0 = colonial era (1955–1963). |
| `volume_number` | int | Hansard volume number. Volumes span multiple sessions. |
| `sitting_number` | int | Which sitting within the session. |
| `sitting_date` | datetime | Date of the sitting. |
| `speech_number` | int | Sequential number of this item within the sitting (the `sno` field from the API). |
| `report_id` | str | The SPRS identifier for this report. |
| `report_type` | str | Category of parliamentary business. See [Report types](#report-types) below. |
| `title` | str | Cleaned title. Mojibake corrected; HTML entity artifacts stripped. |
| `original_title` | str | Title exactly as received from the API. |
| `subtitle` | str | Parenthetical subtitle if present, e.g. `(in Malay)` or `(Continued)`. |
| `markdown_content` | str | HTML content converted to clean markdown. `NULL` if the API returned no HTML. |
| `content` | str | Raw HTML from the API, stored exactly as received. |

### Speech

One row per individual utterance within a report. Speeches are extracted from `markdown_content` by detecting bold speaker names (`**Name:**`).

| Field | Type | Meaning |
|---|---|---|
| `ordinal` | int | Position of this speech within the report, starting from 0. |
| `speaker` | str | Speaker name as it appears in the transcript, with title prefix stripped. `NULL` if attribution failed. |
| `transcript` | str | Text of the speech in markdown. |
| `report_id` | int | FK → `Report.id`. |
| `mp_id` | int | FK → `Mp.id`. `NULL` where the match has not been resolved. |

### Sitting

One row per sitting date. A sitting is a full day of parliamentary proceedings, encompassing multiple reports. Fields are `NULL` for formats that do not carry them (old vs new API format; see [parsing.md](parsing.md)).

| Field | Type | Meaning |
|---|---|---|
| `parlement_no` | int | Parliament number. Intentional typo from the API (`parlimentNO`). |
| `session_no` | int | Session number within the parliament. |
| `volume_no` | int | Hansard volume number. |
| `sitting_no` | int | Sitting number within the session. |
| `sitting_date` | str | Date string as returned by the API. |
| `start_time_str` | str | Start time of the sitting (new format only). |
| `speaker` | str | Speaker of the House for that sitting (new format only). |
| `location_text` | str | Location of the sitting, e.g. `"in contemporaneous communication"` (new format only). |
| `markdown_content` | str | Full sitting HTML converted to markdown. Used to parse attendance. |
| `html_full_content` | str | Raw HTML of the full sitting proceedings. |

### SittingAttendance

One row per MP per sitting. Sourced from the `attendanceList` in the API response (new format only).

| Field | Type | Meaning |
|---|---|---|
| `mp_name` | str | MP name as returned by the API. |
| `attendance` | bool | `True` = present, `False` = absent. |
| `location_name` | str | Location if the sitting was hybrid (e.g. remote attendance). |

### SittingPtba

Permission To Be Absent records. One row per MP per approved absence period.

| Field | Type | Meaning |
|---|---|---|
| `mp_name` | str | MP name. |
| `from_date` | str | Start of the approved absence. |
| `to_date` | str | End of the approved absence. |

### SittingSection

Debate sections and questions listed on the sitting agenda. One row per item in `takesSectionVOList`.

| Field | Type | Meaning |
|---|---|---|
| `title` | str | Title of the section or question. |
| `section_type` | str | Type code, e.g. `OA` (oral answer), `WA` (written answer). |
| `content` | str | HTML content of the section. |

### Mp

MP identities scraped from parliament.gov.sg. One row per MP per parliament — the same person appears multiple times across parliaments.

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Name without title prefix. |
| `party` | str | Political party. |
| `parliament_number` | int | Parliament they served in. |
| `is_legislative_assembly` | bool | `True` for colonial Legislative Assembly members (pre-independence). |
| `comments` | str | Footnote annotations from the source page, e.g. appointment dates or name changes. |

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

- Records from 1955–1965 cover the colonial Legislative Assembly and the State of Singapore, not the Republic of Singapore Parliament. `Mp.is_legislative_assembly = True` marks these members.
- ~490 documents have no speaker attribution: multi-speaker appendix documents (body is a list of PDF links) and colonial-era procedural budget orders with no named author.
- Some `Report.title` values contain Windows-1252 mojibake (e.g. `â€™` instead of `'`). `Report.markdown_content` has correct Unicode. Affects ~382 `president-address` titles and ~2,153 `budget` titles. `Report.original_title` is the unmodified raw value.
- Colonial-era records from 1955–1961 (Parliament 0) have no `MPs Speaking` field, so single-speaker attribution fallback cannot apply.
- `Speech.mp_id` is incomplete for colonial-era and early-parliament records.
- ~3% of modern-era sitting documents have a missing space before the time (e.g. `"The House met at3.00 pm"`). This is a defect in the raw HTML.

# Data Dictionary

This document describes the dataset for researchers. It covers what each entity represents, what the fields mean, and what caveats apply when using the data.

For technical details about HTML artifact handling and parsing edge cases, see [parsing.md](parsing.md).

---

## What the dataset contains

The dataset covers every parliamentary record published by the Singapore Parliament Reports Search System (SPRS), from the colonial Legislative Assembly through the present Parliament. This includes pre-independence proceedings when Singapore was part of Malaya.

Each record is one parliamentary item — a question, a debate topic, a bill reading, a ministerial statement — identified by parliament number, sitting date, and a report ID. Records are parsed into individual speeches attributed to named MPs.

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

Mp (canonical MP identity, one row per MP per parliament)
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
| `speaker` | str | Name of the speaker as it appears in the transcript, with title prefix stripped. `NULL` if attribution failed. |
| `transcript` | str | Text of the speech in markdown. |
| `report_id` | int | FK → `Report.id`. |
| `mp_id` | int | FK → `Mp.id`. `NULL` where MP identity has not yet been resolved. |

### Sitting

One row per sitting date. A sitting is a full day of parliamentary proceedings, encompassing multiple reports. Fields are `NULL` for formats that do not carry them (old vs new API format; see [docs/parsing.md](parsing.md)).

| Field | Type | Meaning |
|---|---|---|
| `parlement_no` | int | Parliament number. Note: intentional typo from the API (`parlimentNO`). |
| `session_no` | int | Session number within the parliament. |
| `volume_no` | int | Hansard volume number. |
| `sitting_no` | int | Sitting number within the session. |
| `sitting_date` | str | Date string as returned by the API. |
| `start_time_str` | str | Start time of the sitting (new format only). |
| `speaker` | str | Name of the Speaker of the House for that sitting (new format only). |
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

Canonical MP identities, scraped from parliament.gov.sg. One row per MP per parliament — the same person appears multiple times if they served across multiple parliaments.

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
| `bill` | A bill reading (first, second, or third). These often contain no speeches — procedural readings are recorded as single-line entries. |
| `bill-intro` | A bill introduction notice. Contains no speeches; these are formal notifications. |
| `ministerial-statement` | A statement delivered by a minister, not in response to a question. |
| `written-statement` | A written ministerial statement tabled in the chamber. |
| `budget` | Budget debates and Committee of Supply proceedings. Also used for procedural budget orders, which contain no speeches. |
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
| `atbp` | Assent to Bills Passed — the formal record of presidential assent. Contains no speeches. |

---

## Key identifiers

**Parliament number** — identifies the parliament session. Parliament 0 corresponds to the colonial Legislative Assembly (1955–1963). Parliament numbers increment from 1 at independence.

**Volume number** — Hansard volumes span multiple sessions and are the primary archival unit. Volumes do not reset at each parliament.

**Sitting date** — the natural key for joining `Report` to `Sitting`. A sitting date maps to exactly one `Sitting` row and many `Report` rows.

**Report ID** — the SPRS identifier for an individual report item. Stable across pipeline re-runs.

---

## Known limitations

**Pre-independence records** — records from Parliament 0 and early parliaments predate Singapore's independence (1965) and cover proceedings of the colonial Legislative Assembly and the Legislative Assembly of Singapore under the State of Singapore. `Mp.is_legislative_assembly = True` marks these members.

**Unattributable documents** — approximately 490 documents have no extractable speaker attribution. These fall into two categories: (1) multi-speaker appendix documents where the body is a list of PDF links and attribution would be fabrication; (2) structurally authorless records such as colonial-era procedural budget orders. These are correct exclusions, not parsing failures.

**Mojibake in title fields** — some `Report.title` values contain Windows-1252 mojibake of UTF-8 characters (e.g. `â€™` instead of `'`). `Report.markdown_content` has the correct Unicode. Affects ~382 `president-address` titles and ~2,153 `budget` titles. `Report.original_title` preserves the raw value exactly as received.

**Missing MPs Speaking field in very early records** — colonial-era records from 1955–1961 (Parliament 0) do not carry an `MPs Speaking` field. Single-speaker attribution fallback cannot apply to these records.

**MP identity linking** — `Speech.mp_id` is populated where the speaker name has been matched to a canonical `Mp` row. Matching is not yet complete for all records, particularly in colonial-era and early-parliament sittings.

**Missing space before time in sitting HTML** — approximately 3% of modern-era sitting documents have a missing space before the time in phrases like `"The House met at3.00 pm"`. This is a source defect in the raw HTML and cannot be corrected without NLP or source correction.

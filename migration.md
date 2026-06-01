# Migration: New Sitting Date API Schema

## Background

The `getHansardReport/` API endpoint returns two distinct response formats depending on the sitting date:

- **Old format** (Parliament 9–12, pre-August 2015): flat dict, all fields at top level
- **New format** (Parliament 13+, August 2015 onwards): nested dict with a `metadata` object and child lists

The existing `HandsardSittingDateResponse` and `Sitting` tables were designed for the old flat format. They do not handle the new format — every mapped field comes in as `None`, causing a `NOT NULL` violation on `volume_no` at insert time.

This migration replaces the old schema with a set of tables that model the new format correctly.

---

## API Response Samples

### Old format (e.g. `sittingDate=12-10-2001`)

```json
{
  "volumeNo": "73",
  "sittingNo": "20",
  "htmlFullContent": "<html>...",
  "footNote": [],
  "atbpList": [],
  "ptbaList": [],
  "attendanceList": [],
  "memberId": null,
  "reportType": null,
  "sessionNo": null,
  "parlNo": null,
  "sittingDate": null,
  "onlinePDFFileName": null,
  "clarificationText": null,
  "clarificationTitle": null,
  "clarificationSubTitle": null,
  "ptbaFrom": null,
  "ptbaTo": null,
  "questionCount": null
}
```

This format is a flat dict whose keys match the aliases on the existing `HandsardSittingDateResponse` model. It is used for Parliament 9–12.

### New format (e.g. `sittingDate=7-5-2026`)

```json
{
  "metadata": {
    "parlimentNO": 15,
    "sessionNO": 1,
    "volumeNO": 96,
    "sittingNO": 31,
    "sittingDate": "07-05-2026",
    "partSessionStr": "FIRST SESSION",
    "startTimeStr": "11:00 AM",
    "speaker": "Mr Speaker",
    "attendancePreviewText": " ",
    "ptbaPreviewText": " ",
    "atbPreviewText": null,
    "dateToDisplay": "Thursday, 7 May 2026",
    "pdfNotes": " ",
    "waText": null,
    "ptbaFrom": "2026",
    "ptbaTo": "2026",
    "locationText": "in contemporaneous communication"
  },
  "attStartPgNo": 0,
  "ptbaStartPgNo": 0,
  "atbpStartPgNo": 0,
  "onlinePDFFileName": "",
  "attendanceList": [
    { "mpName": "...", "attendance": false, "locationName": null }
  ],
  "ptbaList": [
    {
      "mpName": "Mrs Josephine Teo",
      "from": "17 Apr",
      "to": "08 May",
      "startDtText": null,
      "endDtText": null,
      "startDtFlag": false,
      "endDtFlag": false
    }
  ],
  "a2bList": [
    { "date": "15 May 2020", "bill": "...", "atbpPreviewText": "null" }
  ],
  "takesSectionVOList": [
    {
      "startPgNo": 0,
      "endPgNo": 0,
      "title": "Impact of Energy Crisis on Hiring Prospects",
      "subTitle": null,
      "sectionType": "OA",
      "content": "<p>...</p>",
      "clarificationText": null,
      "clarificationTitle": null,
      "clarificationSubTitle": null,
      "reportType": null,
      "questionCount": null,
      "footNotes": null,
      "footNoteQuestions": null,
      "questionNo": null
    }
  ],
  "annexureList": [
    {
      "annexureID": 1388,
      "sittingDate": null,
      "annexureTitle": "Annex 1",
      "filePath": "d:/apps/reports/...",
      "fileName": "Annex 1 - handout for PQ7.pdf",
      "sectionType": "OA",
      "file": null
    }
  ],
  "vernacularList": [
    {
      "vernacularID": 3949,
      "sittingDate": null,
      "vernacularTitle": "Vernacular Speech by Mr Heng Swee Keat",
      "filePath": "d:/apps/reports/...",
      "fileName": "Heng Swee Keat Fortitude Budget 26May2020-Chinese.pdf"
    }
  ],
  "writtenAnswersVOList": [],
  "writtenAnsNAVOList": []
}
```

`writtenAnswersVOList` and `writtenAnsNAVOList` were confirmed empty across all new-format sitting dates sampled — do not create tables for them.

`a2bList`, `annexureList`, and `vernacularList` are sometimes empty but confirmed to have data in certain sittings — tables are required.

---

## Tables to Create

All follow the project convention: raw response tables store API data exactly as received (no transformation beyond serialising lists to JSON strings for storage). Use `Optional` for all nullable fields.

### 1. `HandsardSittingDateResponse` — replace existing

Drop and recreate this table. The existing model (`database/handsard_sitting_date_response.py`) was designed for the old flat format. Replace it entirely to model the new format's `metadata` object plus the scalar top-level fields.

**Source:** `metadata` dict + top-level scalars (`attStartPgNo`, `ptbaStartPgNo`, `atbpStartPgNo`, `onlinePDFFileName`)

| Python field | API key | Type |
|---|---|---|
| `id` | — | `int` (PK, auto) |
| `parlement_no` | `metadata.parlimentNO` | `Optional[int]` |
| `session_no` | `metadata.sessionNO` | `Optional[int]` |
| `volume_no` | `metadata.volumeNO` | `Optional[int]` |
| `sitting_no` | `metadata.sittingNO` | `Optional[int]` |
| `sitting_date` | `metadata.sittingDate` | `Optional[str]` |
| `part_session_str` | `metadata.partSessionStr` | `Optional[str]` |
| `start_time_str` | `metadata.startTimeStr` | `Optional[str]` |
| `speaker` | `metadata.speaker` | `Optional[str]` |
| `attendance_preview_text` | `metadata.attendancePreviewText` | `Optional[str]` |
| `ptba_preview_text` | `metadata.ptbaPreviewText` | `Optional[str]` |
| `atb_preview_text` | `metadata.atbPreviewText` | `Optional[str]` |
| `date_to_display` | `metadata.dateToDisplay` | `Optional[str]` |
| `pdf_notes` | `metadata.pdfNotes` | `Optional[str]` |
| `wa_text` | `metadata.waText` | `Optional[str]` |
| `ptba_from` | `metadata.ptbaFrom` | `Optional[str]` |
| `ptba_to` | `metadata.ptbaTo` | `Optional[str]` |
| `location_text` | `metadata.locationText` | `Optional[str]` |
| `att_start_pg_no` | `attStartPgNo` | `Optional[int]` |
| `ptba_start_pg_no` | `ptbaStartPgNo` | `Optional[int]` |
| `atbp_start_pg_no` | `atbpStartPgNo` | `Optional[int]` |
| `online_pdf_file_name` | `onlinePDFFileName` | `Optional[str]` |

Note: `parlimentNO` is a typo in the API — preserve it faithfully in the field name as `parlement_no` (do not correct it to `parliament`).

### 2. `SittingAttendance`

**Source:** `attendanceList` items. Each item is one person's attendance record for the sitting.

| Python field | API key | Type |
|---|---|---|
| `id` | — | `int` (PK, auto) |
| `sitting_id` | — | `int` (FK → `handsardsittingdateresponse.id`) |
| `speaker_name` | `mpName` | `Optional[str]` |
| `attendance` | `attendance` | `Optional[bool]` |
| `location_name` | `locationName` | `Optional[str]` |

### 3. `SittingPtba`

**Source:** `ptbaList` items. PTBA = Permission To Be Absent.

| Python field | API key | Type |
|---|---|---|
| `id` | — | `int` (PK, auto) |
| `sitting_id` | — | `int` (FK → `handsardsittingdateresponse.id`) |
| `speaker_name` | `mpName` | `Optional[str]` |
| `from_date` | `from` | `Optional[str]` |
| `to_date` | `to` | `Optional[str]` |
| `start_dt_text` | `startDtText` | `Optional[str]` |
| `end_dt_text` | `endDtText` | `Optional[str]` |
| `start_dt_flag` | `startDtFlag` | `Optional[bool]` |
| `end_dt_flag` | `endDtFlag` | `Optional[bool]` |

Note: `from` is a Python reserved word — use `from_date` as the field name.

### 4. `SittingSection`

**Source:** `takesSectionVOList` items. Each item is one debate section or question.

| Python field | API key | Type |
|---|---|---|
| `id` | — | `int` (PK, auto) |
| `sitting_id` | — | `int` (FK → `handsardsittingdateresponse.id`) |
| `start_pg_no` | `startPgNo` | `Optional[int]` |
| `end_pg_no` | `endPgNo` | `Optional[int]` |
| `title` | `title` | `Optional[str]` |
| `sub_title` | `subTitle` | `Optional[str]` |
| `section_type` | `sectionType` | `Optional[str]` |
| `content` | `content` | `Optional[str]` |
| `clarification_text` | `clarificationText` | `Optional[str]` |
| `clarification_title` | `clarificationTitle` | `Optional[str]` |
| `clarification_sub_title` | `clarificationSubTitle` | `Optional[str]` |
| `report_type` | `reportType` | `Optional[str]` |
| `question_count` | `questionCount` | `Optional[str]` |
| `foot_notes` | `footNotes` | `Optional[str]` |
| `foot_note_questions` | `footNoteQuestions` | `Optional[str]` |
| `question_no` | `questionNo` | `Optional[str]` |

### 5. `SittingAnnexure`

**Source:** `annexureList` items.

| Python field | API key | Type |
|---|---|---|
| `id` | — | `int` (PK, auto) |
| `sitting_id` | — | `int` (FK → `handsardsittingdateresponse.id`) |
| `annexure_id` | `annexureID` | `Optional[int]` |
| `sitting_date` | `sittingDate` | `Optional[str]` |
| `annexure_title` | `annexureTitle` | `Optional[str]` |
| `file_path` | `filePath` | `Optional[str]` |
| `file_name` | `fileName` | `Optional[str]` |
| `section_type` | `sectionType` | `Optional[str]` |
| `file` | `file` | `Optional[str]` |

### 6. `SittingVernacular`

**Source:** `vernacularList` items.

| Python field | API key | Type |
|---|---|---|
| `id` | — | `int` (PK, auto) |
| `sitting_id` | — | `int` (FK → `handsardsittingdateresponse.id`) |
| `vernacular_id` | `vernacularID` | `Optional[int]` |
| `sitting_date` | `sittingDate` | `Optional[str]` |
| `vernacular_title` | `vernacularTitle` | `Optional[str]` |
| `file_path` | `filePath` | `Optional[str]` |
| `file_name` | `fileName` | `Optional[str]` |

### 7. `SittingA2b`

**Source:** `a2bList` items.

| Python field | API key | Type |
|---|---|---|
| `id` | — | `int` (PK, auto) |
| `sitting_id` | — | `int` (FK → `handsardsittingdateresponse.id`) |
| `date` | `date` | `Optional[str]` |
| `bill` | `bill` | `Optional[str]` |
| `atbp_preview_text` | `atbpPreviewText` | `Optional[str]` |

---

## Files to Create

Follow the exact patterns in the existing codebase. Look at `database/report.py`, `crud/report.py`, and `populate/reports.py` as reference for how database models, CRUD classes, and populate functions are structured.

### Database models (`database/`)

Create one file per table:

- `database/sitting_attendance.py` → `SittingAttendance`
- `database/sitting_ptba.py` → `SittingPtba`
- `database/sitting_section.py` → `SittingSection`
- `database/sitting_annexure.py` → `SittingAnnexure`
- `database/sitting_vernacular.py` → `SittingVernacular`
- `database/sitting_a2b.py` → `SittingA2b`

Also replace `database/handsard_sitting_date_response.py` entirely with the new schema described above.

Each model inherits from `SQLModel` with `table=True`. Use `Field(default=None, primary_key=True)` for `id`. Use `Field(default=None, foreign_key="handsardsittingdateresponse.id")` for `sitting_id`.

### CRUD classes (`crud/`)

Create one file per new table, following the pattern in `crud/report.py`:

- `crud/sitting_attendance.py` → `CRUDSittingAttendance`
- `crud/sitting_ptba.py` → `CRUDSittingPtba`
- `crud/sitting_section.py` → `CRUDSittingSection`
- `crud/sitting_annexure.py` → `CRUDSittingAnnexure`
- `crud/sitting_vernacular.py` → `CRUDSittingVernacular`
- `crud/sitting_a2b.py` → `CRUDSittingA2b`

Also replace `crud/handsard_sitting_date_response.py` to match the new model. Keep `get_all_sitting_dates()` — it is used by `populate/sittings.py`.

### Service (`services/`)

Replace `services/handsard_sitting_date_response.py` entirely. The new service must:

1. Accept the raw API response dict (the full response from `gateway/handsard_report.py`)
2. Extract `metadata` and top-level scalar fields to build `HandsardSittingDateResponse`
3. Extract each child list to build lists of the child models
4. Return all of them together (e.g. as a dataclass or named tuple)

### Populate script (`populate/`)

Replace `populate/sitting_dates.py` with logic that:

1. Calls `get_handsard_report_response(sitting_date)` for each sitting date not yet in the DB
2. Passes the response to the new service
3. Inserts the parent `HandsardSittingDateResponse` first (to get its `id`)
4. Inserts all child records with `sitting_id` set to the parent's `id`

---

## Files to Modify

### `database/init.py`

Add imports for all new database model files so SQLModel registers them before `create_all` is called:

```python
import database.sitting_attendance  # noqa: F401
import database.sitting_ptba        # noqa: F401
import database.sitting_section     # noqa: F401
import database.sitting_annexure    # noqa: F401
import database.sitting_vernacular  # noqa: F401
import database.sitting_a2b         # noqa: F401
```

### `script.py`

No changes needed — `populate_sitting_dates` is already imported and called. The internal implementation change is self-contained.

---

## Constraints and Conventions

- **Raw response tables store data as received.** Do not transform field values. The only exception is serialising list fields to JSON strings when the column type is `str`.
- **All fields on child tables should be `Optional`** except `id` and `sitting_id`.
- **`volume_no` on `HandsardSittingDateResponse` must be `Optional[int]`** — the old schema had it as non-nullable `str`, which was the root cause of the original crash.
- **Do not touch** `database/report.py`, `database/speech.py`, `database/sitting.py`, `populate/sittings.py`, or any file unrelated to the sitting date pipeline.
- **`populate/sitting_dates.py` already exists** — replace its contents, do not create a new file.
- The `Sitting` entity table (`database/sitting.py`) extends `HandsardSittingDateResponse`. Once the parent model is replaced, check whether `services/sitting.py` and `populate/sittings.py` still work — they may need updating to match the new parent field names.

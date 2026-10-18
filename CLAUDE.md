# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@STYLE.md

## Goal and how progress is measured

The goal is in `docs/vision.md`. Its "Measuring progress" section holds the current verdict per objective, the open gaps, and where more work stops paying. Read it before planning work or reporting results.

- Run `python scripts/attribution_text_share.py` before and after any change to parsing or linking, and quote all three numbers it logs: the ADR 0001 rate, the all-rows rate, and text share. The ADR 0001 rate alone rises when the parser sets rows to NULL, so it can hide a regression.
- Every write to the speech table, and every round of links, ends with `python scripts/attribution_text_share.py --output docs/figures/YYYY-MM-DD-<write>.txt`, run on the replica after the write, and the file is committed. The file holds the same lines with the figures by report type and Parliament, the zero-row count and the single-speaker collapse share.
- A passing `diagnose.py` or `run_sanity_check.py` does not mean speeches are correct; see the table in that section.
- When a figure there moves, update the section in the same change.

## Data loss register

`docs/data-loss-register.md` records everything the pipeline loses between the raw API responses and any derived table. Any change that cleans data adds or updates a row there in the same change, or it is not done. Cleaning means dropping, merging, deduplicating, trimming, normalising, overriding, reclassifying or deleting anything the source holds. It covers parsing and speech rows, and also attendance, persons, memberships, sittings, report titles and the hand overrides in `data/`. The row says what is lost, where in code, why, the cost in counts, whether it can be rebuilt from the raw tables, and who decided.

## Commands

```bash
# Install dependencies
poetry install

# Start local Postgres (matches default DATABASE_URL)
docker-compose up -d

# Run linting
ruff check .
ruff check --fix .

# Run the main scraping/processing pipeline
python script.py

# Database migrations (Alembic)
python -m alembic upgrade head          # apply all pending migrations
python -m alembic check                 # verify DB matches models (no pending changes)
python -m alembic revision --autogenerate -m "describe change"  # generate a new migration
python -m alembic downgrade -1          # roll back one migration

# Scrape speakers by parliament (run separately, not part of script.py)
python scripts/scrape_speakers_by_parliament.py
```

`poetry run pytest` runs the golden fixtures in `tests/`: each is a trimmed source HTML excerpt plus the speech rows the parser must produce. Each parser fix adds a fixture for the defect it closes.

## Architecture

This is a scraper for Singapore Parliament Hansard records (sprs.parl.gov.sg). The pipeline runs in stages — each stage's output feeds the next — and `script.py` is the orchestration file that runs all stages sequentially.

### Layer rules

Each folder has a strict responsibility boundary. `populate/` is the only layer that may combine gateway calls, service transforms, and DB writes.

| Layer | Responsibility | Forbidden |
|---|---|---|
| `schemas/` | Pydantic models for API response shapes | DB access, logic |
| `gateway/` | HTTP calls; return parsed Pydantic models from `schemas/` | Business logic, DB writes, interpreting a missing field |
| `services/` | Pure transforms: input data → output entity | HTTP calls, DB access |
| `database/` | SQLModel table class definitions | Logic of any kind |
| `crud/` | DB read/write helpers | Business logic, HTTP |
| `populate/` | Pipeline stages: orchestrate gateway + services + crud | — |
| `utils/` | Shared pure functions | DB access, HTTP |
| `scripts/` | One-off diagnostics: use Session + crud + services | Raw SQL, direct `select()`/`session.add()` bypassing crud |

### Data flow

1. **Fetch search index** (`gateway/hansard_search.py`): POST to the Hansard search API, paginate through all results, return `list[HansardSearchResult]` (Pydantic model in `schemas/hansard_search_result.py`); a non-list body is an empty page.

2. **Fetch report HTML** (`populate/hansard_responses.py` + `gateway/hansard_topic.py` + `services/hansard_website.py`): for each search result, `populate` calls `gateway` to POST to `getHansardTopic` with a JSON body, which returns a `HansardTopicResponse` (`schemas/hansard_topic_response.py`). The fetch picks the id and the field by system (`services/hansard_website.py::get_topic_id` and `get_topic_html_content`): an older-system hit (`report_version` sprs2, sittings before 10 September 2012) is fetched by `html_file_name` and read from `htmlContent`; a newer-system hit (sprs3) is fetched by `report_id` without its trailing `#` and read from `resultHTML.content`. Both land in `HansardWebsiteResponse.content` through `build_hansard_website_response` (see `docs/adr/0003-newer-system-raw-mapping.md`). Newer-system atbp reports return no text and keep `content` null. Hits listed in `data/excluded_report_ids.json` (a stored report returned again under another id, with the id of the copy kept) are never inserted, and stage 3 builds no report from their raw rows. `populate/hansard_response_contents.py` and `populate/report_contents.py` fill `content` and `markdown_content` in place on rows stored without text.

3. **Parse into Report** (`services/report.py`) — converts `HansardWebsiteResponse` → `Report`. Parses the `title` field to split off a `subtitle` (parenthetical content that is not an acronym). The title is trimmed, loses HTML tags, and a title repeated around commas keeps one copy; `original_title` keeps the source form. Also converts HTML content to cleaned markdown via `utils/markdown_parser.py`. An older-system hit of 2003 to 2011 carries no sitting number, so it is read from the `Sitting No` line of the report's header table (`utils/markdown_header.py`).

4. **Parse into Speeches** (`services/speech.py`) — walks the markdown line-by-line to find where speeches begin (by matching the report title in bold), then splits the transcript into `Speech` records by detecting bold speaker names (`**Name:**`). `build_speeches` numbers the records and gives each its report's sitting date. Newer-system reports (sprs3) start at the top of the body, because their text never repeats the title; `utils/markdown_parser.py` also cleans their HTML differently (empty emphasis tags and `(proc text)` markers go). Every such branch is guarded by `report_version`, so older-system output is unchanged.

5. **Fetch sitting dates** (`gateway/hansard_report.py` + `populate/hansard_sitting_dates.py`) — for each unique sitting date seen in the search results, POST to `getHansardReport/` with a JSON body (`{"sittingDate": "DD-MM-YYYY"}`, zero padded) to retrieve full sitting metadata. The gateway picks the schema by the shape of the body (a `metadata` key means the nested format) and the stage dispatches on the model type. Stores the result in `HansardSittingDateResponse`; the attendance and PTBA lists are stored as raw JSON strings on that table, and the other nested lists have columns only on `Sitting`. `populate/sitting_details.py` fills null columns in place on sittings stored without their details.

6. **Parse into Sittings** (`services/sitting.py` + `populate/sittings.py`) — converts `HansardSittingDateResponse` → `Sitting`, adding a `markdown_content` field parsed from `html_full_content`. Also carries the nested JSON columns (sections, annexures, vernaculars, a2b) from the raw response. An older-system response has no session number and sometimes no sitting number; both are read from the header table of the sitting's HTML.

7. **Extract attendance** (`services/attendance.py` + `populate/attendances.py`) — for each `Sitting`, parses the PRESENT/ABSENT sections from `markdown_content` and writes one `Attendance` row per name found. Sittings with no markdown (every sitting from 10 September 2012) take their rows from the structured `attendance_list` instead, with the same name cleaning and resolution. The constituency in each row's bracket goes through `data/constituency_names.json`, which turns typos and variant spellings into the Elections Department's name and leaves seat types and other text as printed. A list ends at the first line that is not a name entry (a heading, a table row, a line that opens with bold or an asterisk, a date line, or an entry that carries a heading glued to its end). A line in the list with neither a title nor a bracketed constituency is skipped, a name that holds markup is never kept, and a member listed twice in a sitting keeps one row, the present one. Skips sittings already processed.

8. **Wire Speaker foreign keys** (`populate/speaker_links.py`) — resolves speaker/attendee names against the `Speaker` table and sets `speaker_id` on `Attendance` and `Speech` rows. Depends on the `Speaker` table being populated first (see out-of-band step below).

**Out-of-band:** `scripts/scrape_speakers_by_parliament.py` scrapes `parliament.gov.sg` for the full list of speakers per parliament and stores them in the `Speaker` table. This must be run before step 8; it is not part of `script.py`. The source gives one party and one Assembly flag per person, so `data/speaker_overrides.json` corrects the flag and the party per Parliament row, both at scrape time (`services/speaker.py`) and on stored rows (`scripts/apply_speaker_overrides.py`). For colonial-era Legislative Assembly members, run `scripts/load_colonial_la_speakers.py` first. A member who sat only in the Assembly is a Parliament 0 row, and one who sat in both bodies has one row in Parliament 1; `scripts/apply_speaker_parliaments.py` moves stored rows to the Parliament the two colonial data files give them, and runs before the loaders and `apply_speaker_overrides.py` read the changed files. `data/unscraped_members.json` holds the Parliament 13 row of Lee Li Lian, who declined the seat the Hansard still lists her for, so the scrape omits her; `scripts/load_colonial_la_speakers.py` reads it with the colonial file and inserts it after the Parliament moves, and `scripts/clean_attendance.py` needs it to link her six attendance rows. A few members changed party inside one Parliament while a `Speaker` row holds only the ballot party, so `data/party_affiliations.json` records their dated party history; run `python -m scripts.load_party_affiliations` once the `Speaker` table is final (after `apply_speaker_parliaments.py`, the loaders and `apply_speaker_overrides.py`), because it finds each Membership by name and Parliament and refuses unless the stored party is one of the spans' parties.

### Sitting date API — two formats

The `getHansardReport/` endpoint returns two distinct formats depending on the sitting date:

- **Old format** (sittings before 10 September 2012): flat body, all fields at top level, parsed as `HansardReportOldResponse`.
- **New format** (sittings from 10 September 2012): nested body with a `metadata` object plus child lists (`attendanceList`, `ptbaList`, `takesSectionVOList`, `annexureList`, `vernacularList`, `a2bList`), parsed as `HansardReportNewResponse`. It carries no full-sitting HTML.

Both schemas live in `schemas/hansard_report_response.py`; every field is `Optional` because the endpoint also answers with `{errorCode, description}`. `gateway/hansard_report.py` strips NUL bytes and picks the schema by the presence of the `metadata` key, and `services/hansard_sitting_date_response.py` exposes `build_old_hansard_sitting_date_response` and `build_new_hansard_sitting_date_response`, which `populate/hansard_sitting_dates.py` dispatches on the model type. `settings.sitting_date_format_change` (`datetime(2015, 8, 18)`) is read only by `scripts/validate_api_field_mapping.py`.

### Database models

Two-tier design: every data source has a **raw response table** and an **entity table**.

**Raw response tables** store API responses exactly as received. No type casting, no field dropping. The only transformation allowed is what storage requires (e.g. serialising list fields to JSON strings so they fit in a column).

**Entity tables** are pure extensions of their raw counterparts — every field from the raw response is preserved with the same value and structure. They exist to provide a stable, first-class DB schema ready for relationships and future enrichment, not to transform or interpret the source data. The one exception: where the raw response leaves a sitting or session number NULL, `Report` and `Sitting` fill it from the header table of the stored text, so those columns can differ from the raw row (see `docs/data-loss-register.md`).

- `HansardWebsiteResponse` — raw API response, one row per Hansard entry
- `Report` — entity table extending `HansardWebsiteResponse`; has a one-to-many to `Speech`
- `Speech` — individual utterance with `speaker`, `transcript`, and `ordinal` within the report; has a `speaker_id` FK to `Speaker` (populated in stage 8) and a `kind` (`SpeechKind` enum, Postgres type `speechkind`) saying what the row's text is: SPEECH, PROCEDURAL, CHAMBER_EVENT, EDITORIAL_NOTE, DOCUMENT_TEXT, HEADING or UNCLASSIFIED (see `docs/adr/0009-speech-kind-column.md`); `sitting_date` is NOT NULL and copies its report's date, which every writer sets, so a rum index can return word matches in date order (see `docs/adr/0010-speech-sitting-date-set-by-each-writer.md`)
- `HansardSittingDateResponse` — raw API response, one row per sitting date; handles both old and new API formats with all fields `Optional`
- `Sitting` — entity table extending `HansardSittingDateResponse`; adds `markdown_content` parsed from `html_full_content`, plus four JSON TEXT columns (`sections`, `annexures`, `vernaculars`, `a2b`) serialised from the API nested lists
- `Attendance` — one row per name per sitting, parsed from `Sitting.markdown_content` in stage 7; has a `speaker_id` FK to `Speaker` (set in stage 8)
- `Speaker` — everyone who appears in the Hansard record, scraped from parliament.gov.sg; keyed by name, party, parliament number, and whether they are a Legislative Assembly member (not all are MPs)
- `PartyAffiliation` — one row per party a Membership sat for, with the date it began (`started_on`, and `started_on_precision`, a `DatePrecision` of DAY or MONTH, Postgres type `dateprecision`; a MONTH date is stored as the first of the month), `is_started_on_upper_bound` (true when `started_on` is the earliest day a source shows the new party, not the day of the change), one plain sentence for the footnote (`event`), exactly one source (`source_url` for a page outside the corpus, or `source_report_id`, an FK to `Report`, for a Hansard report in it; a check constraint holds this), and a `speaker_id` FK to `Speaker`; the `Speaker` row keeps the ballot party and this table adds the history

### Key parsing logic

`utils/markdown_parser.py` — HTML → clean markdown pipeline: turns `&nbsp;` into a space (an emphasis tag holding only `&nbsp;` becomes one space), strips column/page markers, then merges consecutive bold-only lines that were split across page breaks. This merged form is required for speaker detection to work correctly. Also has `get_cleaned_sitting_markdown` for sitting HTML.

`services/speech.py::get_start_of_speech_line` — locates the line in the markdown that marks where speeches begin (the report's own title appears in bold as the first "heading" before actual speeches). Returns `None` if the title can't be matched.

`services/attendance.py`: extracts and resolves names from sitting markdown. `build_speaker_lookups(speakers: list[Speaker]) -> SpeakerLookups` builds all six in-memory lookup dicts from a pre-loaded Speaker list (no DB access). Callers must load Speakers via `crud/speaker.py` and pass the resulting `SpeakerLookups` to `resolve_canonical_name` and `get_sitting_attendance`. The resolution cascade: manual overrides → inverted-name lookup → direct lookup → bin-free lookup → word-set lookup → prefix lookup → spelling normalisation → Haji-prefix stripping → surname-only fallback. The pure name helpers (`strip_title`, which removes 25+ title prefixes such as Dr, BG, RAdm and Tuan Haji before matching, plus `normalize_name`, `period_normalize`, `strip_bin`, `invert_to_natural`, `strip_middle_haji` and `spelling_normalize`) live in `utils/names.py`, because `services/attendance.py` and `services/person.py` both need them. `infer_parliament(parlement_no, volume_no)` derives the parliament number using `VOLUME_TO_PARLIAMENT`. CRUD projections come back as dataclasses declared beside their method (`SpeechRow`, `SpeechSpeakerRow`, `AttendanceSpeakerRow`), never tuples, and CRUD lookups are named for the columns they filter on (`get_speaker_rows_by_speaker_id_null`, `get_by_markdown_content_not_null`).

### Environment

Requires a `DATABASE_URL` env var (or `.env` file). Falls back to `postgresql://user:password@localhost:5432/postgres`.

All configurable URLs and search date bounds live in `settings.py` (`AppSettings`).

### `scripts/` directory

One-off diagnostic and analysis scripts, not part of the main pipeline:

- `diagnose.py` — inspect parsing failures across the corpus
- `inspect_failures.py` — drill into specific failure cases
- `run_sanity_check.py`, `run_no_speech_validation.py`, `run_single_speaker_check.py` — targeted validation runs
- `run_exclusion_sanity_check.py` — analyses zero-speech (excluded) documents by checking HTML bold tags vs markdown speaker patterns
- `find_unmatched_attendees.py` — finds attendance names with no match in the Speaker table, grouped by frequency; outputs a JSON template for `colonial_la_members.json`
- `attribution_text_share.py` — the three attribution numbers in `docs/vision.md`: ADR 0001 rate, all-rows rate, and share of body text in a linked speech; also per report type within each Parliament group, with the zero-row count and the single-speaker collapse share; `--output PATH` keeps the lines in `docs/figures/`, one file per write
- `speech_speaker_match_rate.py` — samples speeches stratified by report type, applies the full `SpeakerLookups` name-resolution pipeline via `resolve_canonical_name`, reports match rate overall and by type
- `load_colonial_la_speakers.py` — idempotent load of `data/colonial_la_members.json` and `data/unscraped_members.json` into the `Speaker` table; must be run before `populate_speaker_links`
- `load_heads_of_state.py`: idempotent load of `data/heads_of_state.json` (Governors, the Yang di-Pertuan Negara, Presidents) into the `Speaker` table as non-member rows; run after `load_colonial_la_speakers.py` and before `populate_speaker_links`
- `scrape_speakers_by_parliament.py` — populates the `Speaker` table from parliament.gov.sg
- `fill_sitting_numbers.py`: fills empty `report.sitting_number`, `sitting.session_no` and `sitting.sitting_no` from the stored header tables; a dry run unless `--commit`
- `apply_report_titles.py`: rewrites stored titles and subtitles that the current title rule would change; a dry run unless `--commit`
- `apply_speaker_overrides.py`: applies `data/speaker_overrides.json` and the party values of `data/colonial_la_members.json` to stored speaker rows, and straightens the apostrophe in party; a dry run unless `--commit`
- `complete_truncated_attendance.py`: inserts the attendance rows an interrupted stage 7 run never wrote for sittings 5941, 5988 and 6009, parsed from the stored sitting markdown; checks the per-sitting counts before it commits; a dry run unless `--commit`
- `apply_constituency_names.py`: rewrites stored attendance location names that `data/constituency_names.json` would change; a dry run unless `--commit`
- `apply_attendance_names.py`: sets stored attendance names to the names stage 7 builds, on rows where nothing else differs; refuses a sitting whose rows differ in more than a name; a dry run unless `--commit`
- `clean_attendance.py`: deletes the attendance rows of `data/attendance_cleanup.json` that the stage 7 parser no longer builds, renames and links its corrections, and links each `Speaker` role row to the presiding officer of its date or deletes it when he has another row; a dry run unless `--commit`
- `apply_speaker_parliaments.py`: moves the stored Assembly-only speaker rows to the Parliament that `data/colonial_la_members.json` and `data/heads_of_state.json` give them; a dry run unless `--commit`
- `apply_speaker_links.py`: links the stored speech and attendance rows that stage 8 would link; a dry run writes the plan file, and `--commit` locks the planned rows, checks they are still unlinked, builds the plan again and refuses unless it equals the reviewed file
- `apply_coverage_refill.py`: stores the hits SPRS lists that the database lacks and fills reports stored with empty text, with their speech rows; a dry run fetches the text into the plan file, and `--commit` checks the hits are still unstored and the reports still empty, writes the plan's text and checks the speech counts; run `apply_speaker_links.py` after it
- `apply_speech_sitting_date.py`: runs migration `c93f77e499cc`, which copies `speech` with each report's sitting date and swaps the copy in, and `alembic check` in one transaction, run as a module; rolled back unless `--commit`
- `load_party_affiliations.py`: idempotent load of `data/party_affiliations.json` into the `PartyAffiliation` table, run as a module; skips rows already stored and refuses when a stored row for the same speaker differs from the file; a dry run unless `--commit`
- `remove_excluded_reports.py`: deletes the stored reports listed in `data/excluded_report_ids.json` and their speech rows, after checking each against its kept copy; a dry run unless `--commit`
- `find_presiding_officers.py`: tallies the most common Speaker and Deputy Speaker per parliament from the PRESENT sections
- `trace_speaker_links.py`: read-only regression guard for stage 8 speech links: re-runs the resolver per key and compares with stored `speaker_id`
- `expand_sample.py`: expands the stratified speech sample in `docs/speech-speaker/sample.json`
- `validate_api_field_mapping.py`: checks that every non-null field in a live or synthetic API body survives the schema and the ORM mapping

`plans/speech-fidelity-loop/bin/` holds the tools for rewriting stored speech rows: `dryrun_fix.py` and `dryrun_subset.py` compare the parser against a frozen previous copy, `plan_*.py` build the update plan, `apply_fix*.py` and `ship_delta*.py` write it. Run them only for a planned write.

Scripts log through `logs.logger`; the one script whose stdout is data (`find_presiding_officers.py`, a paste-ready dict literal) prints that output under `# noqa: T201`. `find_unmatched_attendees.py` writes its JSON template to the path given by `--json`.

## Module structure

```
hansard-scraper/
│
├── script.py                        # Pipeline orchestrator — runs all populate stages in order
├── settings.py                      # AppSettings (DATABASE_URL, API endpoints, date bounds)
├── enums.py                         # ReportType and ReportVersion (sprs2 older system, sprs3 newer system)
├── exceptions.py                    # HansardError / HansardGatewayError / HansardWriteTargetError / HansardWriteCheckError / HansardPartyAffiliationError
├── logs.py                          # Loguru logger initialisation
│
├── schemas/                         # Pydantic validation models (API shapes, not DB)
│   ├── hansard_search_result.py    # HansardSearchResult — camelCase alias support
│   ├── hansard_topic_response.py   # HansardTopicResponse: the getHansardTopic body (three shapes)
│   ├── hansard_report_response.py  # HansardReportOldResponse / HansardReportNewResponse / HansardReportMetadata / HansardReportAttendanceEntry
│   ├── excluded_report_id.py       # ExcludedReportId: data/excluded_report_ids.json entries
│   ├── attendance_cleanup.py       # AttendanceCleanup: data/attendance_cleanup.json entries
│   ├── party_affiliation.py        # MembershipPartyAffiliations / PartyAffiliationSpan: data/party_affiliations.json entries
│   ├── speaker_override.py         # SpeakerOverrides: data/speaker_overrides.json
│   └── speaker.py                   # SpeakerResult — party and parliament metadata
│
├── gateway/                         # HTTP API clients
│   ├── http.py                      # Async POST with exponential-backoff retry (handles 429)
│   ├── hansard_search.py           # Paginated Hansard full-text search
│   ├── hansard_topic.py            # Fetch report HTML by ID (sync + async)
│   ├── hansard_report.py           # Fetch sitting metadata by date (sync + async)
│   └── speakers_by_parliament.py    # Scrape speaker roster from parliament.gov.sg
│
├── services/                        # Business logic — transforms raw data into entities
│   ├── hansard_website.py          # Pure transform: (HansardSearchResult, html_content) → HansardWebsiteResponse
│   ├── hansard_sitting_date_response.py  # Build old/new-format HansardSittingDateResponse
│   ├── report.py                    # HansardWebsiteResponse → Report (markdown + subtitle)
│   ├── speech.py                    # Report markdown → Speech list (speaker detection)
│   ├── sitting.py                   # HansardSittingDateResponse → Sitting
│   ├── attendance.py                # Sitting markdown → Attendance; build_speaker_lookups(list[Speaker]) → SpeakerLookups
│   ├── attendance_cleanup.py        # Plan for scripts/clean_attendance.py: checks the listed rows, then links or deletes each
│   ├── person.py                    # Speaker rows → person clusters (name normalisation + review decisions)
│   ├── role_context.py              # Chairman, Deputy Speaker and carried-role names per speech row
│   ├── party_affiliation.py         # Party affiliation file + Speaker rows → PartyAffiliation rows; picks the rows not yet stored
│   └── speaker.py                   # SpeakerResult → Speaker DB entity
│
├── database/                        # SQLModel table definitions
│   ├── init.py                      # Engine setup, runs Alembic migrations on startup
│   ├── hansard_website_response.py # Raw API response — one row per Hansard entry
│   ├── hansard_sitting_date_response.py  # Raw sitting metadata (all fields Optional)
│   ├── report.py                    # Entity: extends HansardWebsiteResponse + markdown
│   ├── speech.py                    # Entity: speaker + transcript + ordinal + speaker_id FK
│   ├── sitting.py                   # Entity: extends HansardSittingDateResponse + markdown + JSON columns
│   ├── attendance.py                # One row per name per sitting + speaker_id FK
│   ├── person.py                    # Person: one row per clustered identity
│   ├── party_affiliation.py         # PartyAffiliation: dated party history within a Membership + speaker_id FK
│   └── speaker.py                   # Speaker: name, party, parliament number, LA flag, person_id FK
│
├── crud/                            # DB read/write helpers (one file per table)
│   ├── hansard_website_response.py
│   ├── hansard_sitting_date_response.py
│   ├── report.py
│   ├── speech.py
│   ├── sitting.py
│   ├── attendance.py
│   ├── person.py
│   ├── party_affiliation.py
│   └── speaker.py
│
├── populate/                        # Pipeline stages — fetch + persist each entity type
│   ├── hansard_responses.py        # Stage 2: async fetch + store HansardWebsiteResponse (4 concurrent)
│   ├── hansard_response_contents.py # Fill: fetch text for newer-system raw rows stored without it
│   ├── report_contents.py           # Fill: copy raw text and markdown onto reports stored without it
│   ├── reports.py                   # Stage 3: HansardWebsiteResponse → Report
│   ├── speeches.py                  # Stage 4: Report → Speech (batches of 1000)
│   ├── hansard_sitting_dates.py    # Stage 5: fetch + store HansardSittingDateResponse
│   ├── sitting_details.py           # Fill: metadata and lists for sittings stored without them
│   ├── sittings.py                  # Stage 6: HansardSittingDateResponse → Sitting
│   ├── attendances.py               # Stage 7: Sitting → Attendance
│   ├── speaker_links.py             # Stage 8: resolve names → set speaker_id on Speech + Attendance
│   ├── speaker_resolution_constants.py  # Reference tables for stage 8 (role terms, office holders)
│   ├── persons.py                   # Stage 9: cluster Speaker rows into Person rows
│   └── speakers.py                  # Out-of-band: persist scraped Speaker records
│
├── utils/                           # Shared pure utilities (no DB, no HTTP)
│   ├── markdown_header.py           # Reads a number such as Sitting No from a stored header table
│   ├── markdown_parser.py           # HTML → clean markdown; merges split bold lines
│   ├── names.py                     # Pure name helpers shared by services/attendance.py and services/person.py
│   ├── sitting_dates.py             # Sitting-date parsing and the old/new format cutoff test
│   ├── speaker_terms.py             # SPEAKER_TERMS: who presided as Speaker on which dates (stages 7 and 8)
│   ├── text.py                      # Mojibake fix (cp1252 → UTF-8) and NUL stripping
│   └── write_target.py              # validate_can_write: the guard every write script calls before --commit
│
└── scripts/                         # One-off diagnostics (not part of pipeline)
    ├── diagnose.py
    ├── inspect_failures.py
    ├── find_unmatched_attendees.py
    ├── run_sanity_check.py
    ├── run_no_speech_validation.py
    ├── run_single_speaker_check.py
    ├── run_exclusion_sanity_check.py
    ├── attribution_text_share.py
    ├── speech_speaker_match_rate.py
    ├── find_presiding_officers.py
    ├── trace_speaker_links.py
    ├── expand_sample.py
    ├── validate_api_field_mapping.py
    ├── load_colonial_la_speakers.py
    ├── load_heads_of_state.py
    ├── scrape_speakers_by_parliament.py
    ├── apply_coverage_refill.py
    ├── apply_speech_sitting_date.py
    ├── remove_excluded_reports.py
    ├── fill_sitting_numbers.py
    ├── apply_report_titles.py
    ├── apply_speaker_overrides.py
    ├── complete_truncated_attendance.py
    ├── apply_constituency_names.py
    ├── apply_attendance_names.py
    ├── clean_attendance.py
    ├── apply_speaker_parliaments.py
    ├── apply_speaker_links.py
    └── load_party_affiliations.py
```

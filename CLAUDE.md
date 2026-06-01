# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

# Scrape MPs by parliament (run separately, not part of script.py)
python scripts/scrape_mps_by_parliament.py
```

There are no automated tests in this project.

## Architecture

This is a scraper for Singapore Parliament Hansard records (sprs.parl.gov.sg). The pipeline runs in stages — each stage's output feeds the next — and `script.py` is the orchestration file that runs all stages sequentially.

### Layer rules

Each folder has a strict responsibility boundary. `populate/` is the only layer that may combine gateway calls, service transforms, and DB writes.

| Layer | Responsibility | Forbidden |
|---|---|---|
| `schemas/` | Pydantic models for API response shapes | DB access, logic |
| `gateway/` | HTTP calls; return raw dicts | Business logic, DB writes |
| `services/` | Pure transforms: input data → output entity | HTTP calls, DB access |
| `database/` | SQLModel table class definitions | Logic of any kind |
| `crud/` | DB read/write helpers | Business logic, HTTP |
| `populate/` | Pipeline stages: orchestrate gateway + services + crud | — |
| `utils/` | Shared pure functions | DB access, HTTP |
| `scripts/` | One-off diagnostics: use Session + crud + services | Raw SQL, direct `select()`/`session.add()` bypassing crud |

### Data flow

1. **Fetch search index** (`gateway/handsard_search.py`) — POST to the Hansard search API, paginate through all results, return raw dicts matching `HandsardSearchResult` (Pydantic model in `schemas/handsard_search_result.py`).

2. **Fetch report HTML** (`populate/handsard_responses.py` + `gateway/handsard_topic.py` + `services/handsard_website.py`) — for each search result, `populate` calls `gateway` to POST to `getHansardTopic`, extracts `htmlContent` from the response, then passes it to `services/handsard_website.py::build_handsard_website_response` which constructs the `HandsardWebsiteResponse` entity stored in the DB.

3. **Parse into Report** (`services/report.py`) — converts `HandsardWebsiteResponse` → `Report`. Parses the `title` field to split off a `subtitle` (parenthetical content that is not an acronym). Also converts HTML content to cleaned markdown via `utils/markdown_parser.py`.

4. **Parse into Speeches** (`services/speech.py`) — walks the markdown line-by-line to find where speeches begin (by matching the report title in bold), then splits the transcript into `Speech` records by detecting bold speaker names (`**Name:**`).

5. **Compute statistics** (`populate/statistics.py`) — for each `HandsardWebsiteResponse`, records whether the report has markdown, a detected start line, and parseable speeches. Also exports a `statistics.csv` summary file.

6. **Fetch sitting dates** (`gateway/handsard_report.py` + `populate/sitting_dates.py`) — for each unique sitting date seen in the search results, POST to `getHansardReport/` to retrieve full sitting metadata. Stores the result in `HandsardSittingDateResponse` plus up to six child tables (attendance, PTBA, sections, annexures, vernaculars, A2B lists).

7. **Parse into Sittings** (`services/sitting.py` + `populate/sittings.py`) — converts `HandsardSittingDateResponse` → `Sitting`, adding a `markdown_content` field parsed from `html_full_content`.

8. **Extract sitting attendance** (`services/sitting_attendance.py` + `populate/sitting_attendances.py`) — for each `Sitting`, parses the PRESENT/ABSENT sections from `markdown_content` and writes one `SittingAttendance` row per MP name found. Skips sittings already processed.

9. **Wire MP foreign keys** (`populate/mp_links.py`) — resolves speaker/attendee names against the `Mp` table and sets `mp_id` on `SittingAttendance` and `Speech` rows. Depends on the `Mp` table being populated first (see out-of-band step below).

**Out-of-band:** `scripts/scrape_mps_by_parliament.py` scrapes `parliament.gov.sg` for the full list of MPs per parliament and stores them in the `Mp` table. This must be run before step 9; it is not part of `script.py`.

### Sitting date API — two formats

The `getHansardReport/` endpoint returns two distinct formats depending on the sitting date:

- **Old format** (Parliament 9–12, pre-18 Aug 2015): flat dict, all fields at top level.
- **New format** (Parliament 13+, 18 Aug 2015 onwards): nested dict with a `metadata` object plus child lists (`attendanceList`, `ptbaList`, `takesSectionVOList`, `annexureList`, `vernacularList`, `a2bList`).

`services/handsard_sitting_date_response.py` exposes `build_old_handsard_sitting_date_response` and `build_new_handsard_sitting_date_response`. The cutoff is `settings.sitting_date_format_change` (`datetime(2015, 8, 18)`).

### Database models

Two-tier design: every data source has a **raw response table** and an **entity table**.

**Raw response tables** store API responses exactly as received. No type casting, no field dropping. The only transformation allowed is what storage requires (e.g. serialising list fields to JSON strings so they fit in a column).

**Entity tables** are pure extensions of their raw counterparts — every field from the raw response is preserved with the same value and structure. They exist to provide a stable, first-class DB schema ready for relationships and future enrichment, not to transform or interpret the source data.

- `HandsardWebsiteResponse` — raw API response, one row per Hansard entry
- `Report` — entity table extending `HandsardWebsiteResponse`; has a one-to-many to `Speech`
- `Speech` — individual utterance with `speaker`, `transcript`, and `ordinal` within the report; has an `mp_id` FK to `Mp` (populated in stage 9)
- `ParsingStatistics` — diagnostic table tracking whether each report has markdown, a detected start line, and parseable speeches
- `HandsardSittingDateResponse` — raw API response, one row per sitting date; handles both old and new API formats with all fields `Optional`
- `SittingAttendance` — child of `Sitting`; one row per MP per sitting, parsed from `Sitting.markdown_content` in stage 8; has an `mp_id` FK to `Mp` (set in stage 9)
- `SittingPtba` — child; Permission To Be Absent records per sitting
- `SittingSection` — child; debate sections/questions from `takesSectionVOList`
- `SittingAnnexure` — child; annexure file references
- `SittingVernacular` — child; vernacular speech file references
- `SittingA2b` — child; absence-to-brief records
- `Sitting` — entity table extending `HandsardSittingDateResponse`; adds `markdown_content` parsed from `html_full_content`
- `Mp` — MPs scraped from parliament.gov.sg, keyed by name, party, parliament number, and whether they are a legislative assembly member

### Key parsing logic

`utils/markdown_parser.py` — HTML → clean markdown pipeline: strips `&nbsp;`, column/page markers, then merges consecutive bold-only lines that were split across page breaks. This merged form is required for speaker detection to work correctly. Also has `get_cleaned_sitting_markdown` for sitting HTML.

`services/speech.py::get_start_of_speech_line` — locates the line in the markdown that marks where speeches begin (the report's own title appears in bold as the first "heading" before actual speeches). Returns `None` if the title can't be matched, which is tracked as a parsing failure.

`services/sitting_attendance.py` — extracts and resolves MP names from sitting markdown. `build_mp_lookups(mps: list[Mp]) -> MpLookups` builds all six in-memory lookup dicts from a pre-loaded MP list (no DB access). Callers must load MPs via `crud/mp.py` and pass the resulting `MpLookups` to `resolve_canonical_name` and `get_sitting_attendance`. The resolution cascade: manual overrides → inverted-name lookup → direct lookup → bin-free lookup → word-set lookup → prefix lookup → spelling normalisation → Haji-prefix stripping → surname-only fallback. `strip_title()` removes 25+ title prefixes (Dr, BG, RAdm, Tuan Haji, etc.) before matching. `infer_parliament()` derives parliament number from `volume_no` or `parlement_no` using `VOLUME_TO_PARLIAMENT`.

### Environment

Requires a `DATABASE_URL` env var (or `.env` file). Falls back to `postgresql://user:password@localhost:5432/postgres`.

All configurable URLs and search date bounds live in `settings.py` (`AppSettings`).

### `scripts/` directory

One-off diagnostic and analysis scripts, not part of the main pipeline:

- `diagnose.py` — inspect parsing failures across the corpus
- `inspect_failures.py` — drill into specific failure cases
- `run_sanity_check.py`, `run_no_speech_validation.py`, `run_single_speaker_check.py` — targeted validation runs
- `run_exclusion_sanity_check.py` — analyses zero-speech (excluded) documents by checking HTML bold tags vs markdown speaker patterns
- `speech_speaker_match_rate.py` — samples speeches stratified by report type, applies the full `MpLookups` name-resolution pipeline via `resolve_canonical_name`, reports match rate overall and by type
- `load_colonial_la_members.py` — idempotent load of `data/colonial_la_members.json` into the `Mp` table; must be run before `populate_mp_links`
- `scrape_mps_by_parliament.py` — populates the `Mp` table from parliament.gov.sg

## Module structure

```
handsard-scraper/
│
├── script.py                        # Pipeline orchestrator — runs all populate stages in order
├── sittings.py                      # Parliament sitting dates enum (LA 1955 → Parliament 14)
├── settings.py                      # AppSettings (DATABASE_URL, API endpoints, date bounds)
├── enums.py                         # ReportType enum (oral/written answers, bills, etc.)
├── exceptions.py                    # HansardError / HansardGatewayError / HansardParseError
├── logs.py                          # Loguru logger initialisation
│
├── schemas/                         # Pydantic validation models (API shapes, not DB)
│   ├── handsard_search_result.py    # HandsardSearchResult — camelCase alias support
│   └── mp.py                        # MpResult — party and parliament metadata
│
├── gateway/                         # HTTP API clients
│   ├── http.py                      # Async POST with exponential-backoff retry (handles 429)
│   ├── handsard_search.py           # Paginated Hansard full-text search
│   ├── handsard_topic.py            # Fetch report HTML by ID (sync + async)
│   ├── handsard_report.py           # Fetch sitting metadata by date (sync + async)
│   └── mps_by_parliament.py         # Scrape MP roster from parliament.gov.sg
│
├── services/                        # Business logic — transforms raw data into entities
│   ├── handsard_website.py          # Pure transform: (HandsardSearchResult, html_content) → HandsardWebsiteResponse
│   ├── handsard_sitting_date_response.py  # Build old/new-format HandsardSittingDateResponse
│   ├── report.py                    # HandsardWebsiteResponse → Report (markdown + subtitle)
│   ├── speech.py                    # Report markdown → Speech list (speaker detection)
│   ├── sitting.py                   # HandsardSittingDateResponse → Sitting
│   ├── sitting_attendance.py        # Sitting markdown → SittingAttendance; build_mp_lookups(list[Mp]) → MpLookups
│   └── mp.py                        # MpResult → Mp DB entity
│
├── database/                        # SQLModel table definitions
│   ├── init.py                      # Engine setup, schema creation, column migrations
│   ├── handsard_website_response.py # Raw API response — one row per Hansard entry
│   ├── handsard_sitting_date_response.py  # Raw sitting metadata (all fields Optional)
│   ├── report.py                    # Entity: extends HandsardWebsiteResponse + markdown
│   ├── speech.py                    # Entity: speaker + transcript + ordinal + mp_id FK
│   ├── sitting.py                   # Entity: extends HandsardSittingDateResponse + markdown
│   ├── sitting_attendance.py        # Child of Sitting: one row per MP per sitting + mp_id FK
│   ├── sitting_ptba.py              # Child: Permission To Be Absent records
│   ├── sitting_section.py           # Child: debate sections from takesSectionVOList
│   ├── sitting_annexure.py          # Child: annexure file references
│   ├── sitting_vernacular.py        # Child: vernacular speech file references
│   ├── sitting_a2b.py               # Child: absence-to-brief records
│   ├── parsing_statistics.py        # Diagnostic: markdown/start-line/speech presence flags
│   └── mp.py                        # Mp: name, party, parliament number, LA flag
│
├── crud/                            # DB read/write helpers (one file per table)
│   ├── handsard_website_response.py
│   ├── handsard_sitting_date_response.py
│   ├── report.py
│   ├── speech.py
│   ├── sitting.py
│   ├── sitting_attendance.py
│   ├── sitting_ptba.py
│   ├── sitting_section.py
│   ├── sitting_annexure.py
│   ├── sitting_vernacular.py
│   ├── sitting_a2b.py
│   ├── parsing_statistics.py
│   └── mp.py
│
├── populate/                        # Pipeline stages — fetch + persist each entity type
│   ├── handsard_responses.py        # Stage 2: async fetch + store HandsardWebsiteResponse (20 concurrent)
│   ├── reports.py                   # Stage 3: HandsardWebsiteResponse → Report
│   ├── speeches.py                  # Stage 4: Report → Speech (batches of 1000)
│   ├── statistics.py                # Stage 5: compute ParsingStatistics + export statistics.csv
│   ├── handsard_sitting_dates.py    # Stage 6: fetch + store sitting metadata + child tables
│   ├── sittings.py                  # Stage 7: HandsardSittingDateResponse → Sitting
│   ├── sitting_attendances.py       # Stage 8: Sitting → SittingAttendance
│   ├── mp_links.py                  # Stage 9: resolve names → set mp_id on Speech + SittingAttendance (via CRUDSpeech/CRUDSittingAttendance)
│   └── mps.py                       # Out-of-band: persist scraped Mp records
│
├── utils/                           # Shared pure utilities (no DB, no HTTP)
│   ├── markdown_parser.py           # HTML → clean markdown; merges split bold lines
│   └── text.py                      # Mojibake fix (cp1252 → UTF-8)
│
└── scripts/                         # One-off diagnostics (not part of pipeline)
    ├── diagnose.py
    ├── inspect_failures.py
    ├── load_colonial_la_members.py
    ├── run_sanity_check.py
    ├── run_no_speech_validation.py
    ├── run_single_speaker_check.py
    ├── run_exclusion_sanity_check.py
    ├── speech_speaker_match_rate.py
    └── scrape_mps_by_parliament.py
```

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

# Scrape speakers by parliament (run separately, not part of script.py)
python scripts/scrape_speakers_by_parliament.py
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

5. **Fetch sitting dates** (`gateway/handsard_report.py` + `populate/handsard_sitting_dates.py`) — for each unique sitting date seen in the search results, POST to `getHansardReport/` to retrieve full sitting metadata. Stores the result in `HandsardSittingDateResponse` only; nested list data (attendance, PTBA, sections, etc.) is stored as raw JSON strings on that table.

6. **Parse into Sittings** (`services/sitting.py` + `populate/sittings.py`) — converts `HandsardSittingDateResponse` → `Sitting`, adding a `markdown_content` field parsed from `html_full_content`. Also carries the nested JSON columns (sections, annexures, vernaculars, a2b) from the raw response.

7. **Extract attendance** (`services/attendance.py` + `populate/attendances.py`) — for each `Sitting`, parses the PRESENT/ABSENT sections from `markdown_content` and writes one `Attendance` row per name found. Skips sittings already processed.

8. **Wire Speaker foreign keys** (`populate/speaker_links.py`) — resolves speaker/attendee names against the `Speaker` table and sets `speaker_id` on `Attendance` and `Speech` rows. Depends on the `Speaker` table being populated first (see out-of-band step below).

**Out-of-band:** `scripts/scrape_speakers_by_parliament.py` scrapes `parliament.gov.sg` for the full list of speakers per parliament and stores them in the `Speaker` table. This must be run before step 8; it is not part of `script.py`. For colonial-era Legislative Assembly members, run `scripts/load_colonial_la_speakers.py` first.

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
- `Speech` — individual utterance with `speaker`, `transcript`, and `ordinal` within the report; has a `speaker_id` FK to `Speaker` (populated in stage 8)
- `HandsardSittingDateResponse` — raw API response, one row per sitting date; handles both old and new API formats with all fields `Optional`
- `Sitting` — entity table extending `HandsardSittingDateResponse`; adds `markdown_content` parsed from `html_full_content`, plus four JSON TEXT columns (`sections`, `annexures`, `vernaculars`, `a2b`) serialised from the API nested lists
- `Attendance` — one row per name per sitting, parsed from `Sitting.markdown_content` in stage 7; has a `speaker_id` FK to `Speaker` (set in stage 8)
- `Speaker` — everyone who appears in the Hansard record, scraped from parliament.gov.sg; keyed by name, party, parliament number, and whether they are a Legislative Assembly member (not all are MPs)

### Key parsing logic

`utils/markdown_parser.py` — HTML → clean markdown pipeline: strips `&nbsp;`, column/page markers, then merges consecutive bold-only lines that were split across page breaks. This merged form is required for speaker detection to work correctly. Also has `get_cleaned_sitting_markdown` for sitting HTML.

`services/speech.py::get_start_of_speech_line` — locates the line in the markdown that marks where speeches begin (the report's own title appears in bold as the first "heading" before actual speeches). Returns `None` if the title can't be matched.

`services/attendance.py` — extracts and resolves names from sitting markdown. `build_speaker_lookups(speakers: list[Speaker]) -> SpeakerLookups` builds all six in-memory lookup dicts from a pre-loaded Speaker list (no DB access). Callers must load Speakers via `crud/speaker.py` and pass the resulting `SpeakerLookups` to `resolve_canonical_name` and `get_sitting_attendance`. The resolution cascade: manual overrides → inverted-name lookup → direct lookup → bin-free lookup → word-set lookup → prefix lookup → spelling normalisation → Haji-prefix stripping → surname-only fallback. `strip_title()` removes 25+ title prefixes (Dr, BG, RAdm, Tuan Haji, etc.) before matching. `infer_parliament()` derives parliament number from `volume_no` or `parlement_no` using `VOLUME_TO_PARLIAMENT`.

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
- `speech_speaker_match_rate.py` — samples speeches stratified by report type, applies the full `SpeakerLookups` name-resolution pipeline via `resolve_canonical_name`, reports match rate overall and by type
- `load_colonial_la_speakers.py` — idempotent load of `data/colonial_la_members.json` into the `Speaker` table; must be run before `populate_speaker_links`
- `scrape_speakers_by_parliament.py` — populates the `Speaker` table from parliament.gov.sg

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
│   └── speaker.py                   # SpeakerResult — party and parliament metadata
│
├── gateway/                         # HTTP API clients
│   ├── http.py                      # Async POST with exponential-backoff retry (handles 429)
│   ├── handsard_search.py           # Paginated Hansard full-text search
│   ├── handsard_topic.py            # Fetch report HTML by ID (sync + async)
│   ├── handsard_report.py           # Fetch sitting metadata by date (sync + async)
│   └── speakers_by_parliament.py    # Scrape speaker roster from parliament.gov.sg
│
├── services/                        # Business logic — transforms raw data into entities
│   ├── handsard_website.py          # Pure transform: (HandsardSearchResult, html_content) → HandsardWebsiteResponse
│   ├── handsard_sitting_date_response.py  # Build old/new-format HandsardSittingDateResponse
│   ├── report.py                    # HandsardWebsiteResponse → Report (markdown + subtitle)
│   ├── speech.py                    # Report markdown → Speech list (speaker detection)
│   ├── sitting.py                   # HandsardSittingDateResponse → Sitting
│   ├── attendance.py                # Sitting markdown → Attendance; build_speaker_lookups(list[Speaker]) → SpeakerLookups
│   └── speaker.py                   # SpeakerResult → Speaker DB entity
│
├── database/                        # SQLModel table definitions
│   ├── init.py                      # Engine setup, runs Alembic migrations on startup
│   ├── handsard_website_response.py # Raw API response — one row per Hansard entry
│   ├── handsard_sitting_date_response.py  # Raw sitting metadata (all fields Optional)
│   ├── report.py                    # Entity: extends HandsardWebsiteResponse + markdown
│   ├── speech.py                    # Entity: speaker + transcript + ordinal + speaker_id FK
│   ├── sitting.py                   # Entity: extends HandsardSittingDateResponse + markdown + JSON columns
│   ├── attendance.py                # One row per name per sitting + speaker_id FK
│   └── speaker.py                   # Speaker: name, party, parliament number, LA flag
│
├── crud/                            # DB read/write helpers (one file per table)
│   ├── handsard_website_response.py
│   ├── handsard_sitting_date_response.py
│   ├── report.py
│   ├── speech.py
│   ├── sitting.py
│   ├── attendance.py
│   └── speaker.py
│
├── populate/                        # Pipeline stages — fetch + persist each entity type
│   ├── handsard_responses.py        # Stage 2: async fetch + store HandsardWebsiteResponse (20 concurrent)
│   ├── reports.py                   # Stage 3: HandsardWebsiteResponse → Report
│   ├── speeches.py                  # Stage 4: Report → Speech (batches of 1000)
│   ├── handsard_sitting_dates.py    # Stage 5: fetch + store HandsardSittingDateResponse
│   ├── sittings.py                  # Stage 6: HandsardSittingDateResponse → Sitting
│   ├── attendances.py               # Stage 7: Sitting → Attendance
│   ├── speaker_links.py             # Stage 8: resolve names → set speaker_id on Speech + Attendance
│   └── speakers.py                  # Out-of-band: persist scraped Speaker records
│
├── utils/                           # Shared pure utilities (no DB, no HTTP)
│   ├── markdown_parser.py           # HTML → clean markdown; merges split bold lines
│   └── text.py                      # Mojibake fix (cp1252 → UTF-8)
│
└── scripts/                         # One-off diagnostics (not part of pipeline)
    ├── diagnose.py
    ├── inspect_failures.py
    ├── find_unmatched_attendees.py
    ├── run_sanity_check.py
    ├── run_no_speech_validation.py
    ├── run_single_speaker_check.py
    ├── run_exclusion_sanity_check.py
    ├── speech_speaker_match_rate.py
    ├── load_colonial_la_speakers.py
    └── scrape_speakers_by_parliament.py
```

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

# Scrape MPs by parliament (run separately, not part of script.py)
python scripts/scrape_mps_by_parliament.py
```

There are no automated tests in this project.

## Architecture

This is a scraper for Singapore Parliament Hansard records (sprs.parl.gov.sg). The pipeline runs in stages — each stage's output feeds the next — and `script.py` is the orchestration file that runs all stages sequentially.

### Data flow

1. **Fetch search index** (`gateway/handsard_search.py`) — POST to the Hansard search API, paginate through all results, return raw dicts matching `HandsardSearchResult` (Pydantic model in `schemas/handsard_search_result.py`).

2. **Fetch report HTML** (`gateway/handsard_topic.py` + `services/handsard_website.py`) — for each search result, POST to `getHansardTopic` to retrieve HTML content, stored as `HandsardWebsiteResponse` in the DB.

3. **Parse into Report** (`services/report.py`) — converts `HandsardWebsiteResponse` → `Report`. Parses the `title` field to split off a `subtitle` (parenthetical content that is not an acronym). Also converts HTML content to cleaned markdown via `utils/markdown_parser.py`.

4. **Parse into Speeches** (`services/speech.py`) — walks the markdown line-by-line to find where speeches begin (by matching the report title in bold), then splits the transcript into `Speech` records by detecting bold speaker names (`**Name:**`).

5. **Compute statistics** (`populate/statistics.py`) — for each `HandsardWebsiteResponse`, records whether the report has markdown, a detected start line, and parseable speeches. Also exports a `statistics.csv` summary file.

6. **Fetch sitting dates** (`gateway/handsard_report.py` + `populate/sitting_dates.py`) — for each unique sitting date seen in the search results, POST to `getHansardReport/` to retrieve full sitting metadata. Stores the result in `HandsardSittingDateResponse` plus up to six child tables (attendance, PTBA, sections, annexures, vernaculars, A2B lists).

7. **Parse into Sittings** (`services/sitting.py` + `populate/sittings.py`) — converts `HandsardSittingDateResponse` → `Sitting`, adding a `markdown_content` field parsed from `html_full_content`.

**Out-of-band:** `scripts/scrape_mps_by_parliament.py` scrapes `parliament.gov.sg` for the full list of MPs per parliament and stores them in the `Mp` table. This is run separately and is not part of `script.py`.

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
- `Speech` — individual utterance with `speaker`, `transcript`, and `ordinal` within the report
- `ParsingStatistics` — diagnostic table tracking whether each report has markdown, a detected start line, and parseable speeches
- `HandsardSittingDateResponse` — raw API response, one row per sitting date; handles both old and new API formats with all fields `Optional`
- `SittingAttendance` — child of `HandsardSittingDateResponse`; one row per MP per sitting
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

### Environment

Requires a `DATABASE_URL` env var (or `.env` file). Falls back to `postgresql://user:password@localhost:5432/postgres`.

All configurable URLs and search date bounds live in `settings.py` (`AppSettings`).

### `scripts/` directory

One-off diagnostic and analysis scripts, not part of the main pipeline:

- `diagnose.py` — inspect parsing failures across the corpus
- `inspect_failures.py` — drill into specific failure cases
- `run_sanity_check.py`, `run_no_speech_validation.py`, `run_single_speaker_check.py` — targeted validation runs
- `scrape_mps_by_parliament.py` — populates the `Mp` table from parliament.gov.sg

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
poetry install

# Run linting
ruff check .
ruff check --fix .

# Run the main scraping/processing script
python script.py
```

There are no automated tests in this project.

## Architecture

This is a scraper for Singapore Parliament Hansard records (sprs.parl.gov.sg). The pipeline runs in stages — each stage's output feeds the next — and `script.py` is the orchestration file where pipeline stages are uncommented/run manually.

### Data flow

1. **Fetch search index** (`gateway/handsard_search.py`) — POST to the Hansard search API, paginate through all results, return raw dicts matching `HandsardSearchResult` (Pydantic model in `schemas.py`).

2. **Fetch report HTML** (`gateway/handsard_topic.py` + `services/handsard_website.py`) — for each search result, POST to `getHansardTopic` to retrieve HTML content, stored as `HandsardWebsiteResponse` in the DB.

3. **Parse into Report** (`services/report.py`) — converts `HandsardWebsiteResponse` → `Report`. Parses the `title` field to split off a `subtitle` (parenthetical content that is not an acronym). Also converts HTML content to cleaned markdown via `utils/markdown_parser.py`.

4. **Parse into Speeches** (`services/speech.py`) — walks the markdown line-by-line to find where speeches begin (by matching the report title in bold), then splits the transcript into `Speech` records by detecting bold speaker names (`**Name:**`).

### Database models (`database/report.py`)

- `HandsardWebsiteResponse` — raw API response, one row per Hansard entry
- `Report` — cleaned/typed version with `markdown_content`; has a one-to-many to `Speech`
- `Speech` — individual utterance with `speaker`, `transcript`, and `ordinal` within the report
- `ParsingStatistics` — diagnostic table tracking whether each report has markdown, a detected start line, and parseable speeches

### Key parsing logic

`utils/markdown_parser.py` — HTML → clean markdown pipeline: strips `&nbsp;`, column/page markers, then merges consecutive bold-only lines that were split across page breaks. This merged form is required for speaker detection to work correctly.

`services/speech.py::get_start_of_speech_line` — locates the line in the markdown that marks where speeches begin (the report's own title appears in bold as the first "heading" before actual speeches). Returns `None` if the title can't be matched, which is tracked as a parsing failure.

### Environment

Requires a `DATABASE_URL` env var (or `.env` file). Falls back to `postgresql://user:password@localhost:5432/postgres`.

### `script.py` usage pattern

Most code in `script.py` is commented out. The file is used interactively — uncomment the block for the pipeline stage you want to run, execute, then re-comment. The `ReportType` enum in `enums.py` lists all report categories used for filtering and stratified sampling (`utils/sample.py`).

# Hansard Scraper

A Python-based scraper for extracting and processing Singapore Parliamentary Hansard records from the official [Singapore Parliament Reports Search System (SPRS)](https://sprs.parl.gov.sg).

## Overview

This project scrapes parliamentary debates, questions, and other proceedings from the Singapore Parliament website, parses the HTML content into structured markdown, and extracts individual speeches with speaker attribution. The data is stored in a PostgreSQL database for further analysis.

## Features

- **Data Collection**: Fetches search results and topic content from the SPRS API
- **Sitting Metadata**: Fetches full sitting date records from the SPRS report API, handling two distinct API formats (pre/post August 2015)
- **MP Scraping**: Scrapes the full list of MPs by parliament from parliament.gov.sg
- **HTML to Markdown Conversion**: Converts raw HTML parliamentary records to clean markdown format
- **Speech Extraction**: Parses speeches and identifies speakers from parliamentary transcripts
- **Database Storage**: Stores raw responses, processed reports, and individual speeches in PostgreSQL
- **Parsing Statistics**: Tracks parsing success rates across different report types

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL database
- Poetry (Python package manager)
- Docker (for the local Postgres instance)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/roycehoe/handsard-scraper.git
   cd handsard-scraper
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Start a local Postgres instance:
   ```bash
   docker-compose up -d
   ```

4. Create a `.env` file if you need a non-default database connection:
   ```env
   DATABASE_URL=postgresql://user:password@localhost:5432/postgres
   ```

## Usage

Run the main pipeline (creates tables, fetches reports, parses speeches, fetches sitting metadata):

```bash
python script.py
```

Scrape MPs by parliament from parliament.gov.sg (run separately):

```bash
python scripts/scrape_mps_by_parliament.py
```

Diagnostic and analysis scripts are in `scripts/`.

## Database Models

Database models follow a two-tier design: every data source has a **raw response table** and an **entity table**.

**Raw response tables** store API responses exactly as received — no type casting, no field dropping. The only transformations applied are those required by the storage format (e.g. serialising list fields to JSON strings so they fit in a column).

**Entity tables** are pure extensions of their raw counterparts. Every field from the raw response is preserved with the same value and structure. They exist to provide a stable, first-class schema ready for relationships and future enrichment — not to transform or interpret the source data.

### HandsardWebsiteResponse
Raw data fetched from the SPRS topic endpoint, stored exactly as received.

### Report
Entity table extending `HandsardWebsiteResponse`. Adds a cleaned `title`, `subtitle`, and `markdown_content`.

### Speech
Individual speeches extracted from reports:
- Speaker name
- Transcript content
- Ordinal position within the report

### ParsingStatistics
Tracks parsing success for quality monitoring:
- Has markdown content
- Has identifiable start line
- Can successfully extract speeches

### HandsardSittingDateResponse
Raw sitting date data fetched from `getHansardReport/`, stored exactly as received. Handles two distinct API formats: a flat dict (Parliament 9–12, pre-August 2015) and a nested format with child lists (Parliament 13+).

### SittingAttendance, SittingPtba, SittingSection, SittingAnnexure, SittingVernacular, SittingA2b
Child tables of `HandsardSittingDateResponse`, each corresponding to a list field in the new API format (attendance, Permission To Be Absent, debate sections, annexures, vernacular speeches, and absence-to-brief records).

### Sitting
Entity table extending `HandsardSittingDateResponse`. Adds `markdown_content` parsed from `html_full_content`.

### Mp
MPs scraped from parliament.gov.sg, keyed by name, party, parliament number, and whether they are a legislative assembly member.

## Report Types

The `ReportType` enum in `enums.py` lists all parliamentary record categories handled by the scraper (oral answers, written answers, motions, bills, ministerial statements, budget debates, and more).

## Dependencies

- **requests**: HTTP client for API calls
- **sqlmodel**: SQL database ORM with Pydantic integration
- **psycopg2**: PostgreSQL adapter
- **python-dotenv**: Environment variable management
- **html2text**: HTML to markdown conversion
- **beautifulsoup4**: HTML parsing
- **pydantic**: Data validation

## Development

### Code Quality

This project uses:
- **ruff**: For linting and import sorting

Run linting:
```bash
ruff check .
ruff check --fix .
```

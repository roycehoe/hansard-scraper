# Hansard Scraper

A Python-based scraper for extracting and processing Singapore Parliamentary Hansard records from the official [Singapore Parliament Reports Search System (SPRS)](https://sprs.parl.gov.sg).

## Overview

This project scrapes parliamentary debates, questions, and other proceedings from the Singapore Parliament website, parses the HTML content into structured markdown, and extracts individual speeches with speaker attribution. The data is stored in a PostgreSQL database for further analysis.

## Features

- **Data Collection**: Fetches search results and topic content from the SPRS API
- **HTML to Markdown Conversion**: Converts raw HTML parliamentary records to clean markdown format
- **Speech Extraction**: Parses speeches and identifies speakers from parliamentary transcripts
- **Database Storage**: Stores raw responses, processed reports, and individual speeches in PostgreSQL
- **Parsing Statistics**: Tracks parsing success rates across different report types

## Project Structure

```
handsard-scraper/
├── main.py                 # Main entry point (currently empty)
├── script.py               # Primary execution script with data processing workflows
├── enums.py                # Report type enumerations (oral answers, motions, bills, etc.)
├── schemas.py              # Pydantic models for API responses
├── pyproject.toml          # Poetry configuration and dependencies
├── database/
│   ├── init.py             # Database connection and session management
│   └── report.py           # SQLModel database models (Report, Speech, etc.)
├── gateway/
│   ├── handsard_search.py  # API client for search endpoint
│   └── handsard_topic.py   # API client for topic/content endpoint
├── services/
│   ├── handsard_website.py # Service for fetching and mapping website data
│   ├── report.py           # Report processing and header parsing
│   └── speech.py           # Speech extraction and speaker identification
└── utils/
    ├── markdown_parser.py  # HTML to markdown conversion utilities
    ├── mps.py              # MP (Member of Parliament) data extraction
    └── sample.py           # Stratified sampling utilities for testing
```

## Report Types

The scraper handles various parliamentary record types:

- Oral and Written Answers
- Clarifications
- Motions
- Bills and Bill Introductions
- Ministerial Statements
- Budget debates
- Adjournment Matters
- Personal Explanations
- Points of Order
- And more...

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL database
- Poetry (Python package manager)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/roycehoe/handsard-scraper.git
   cd handsard-scraper
   ```

2. Install dependencies with Poetry:
   ```bash
   poetry install
   ```

3. Create a `.env` file with your database connection:
   ```env
   DATABASE_URL=postgresql://user:password@localhost:5432/postgres
   ```

4. Initialize the database tables:
   ```python
   from database.init import create_db_and_tables
   create_db_and_tables()
   ```


## Database Models

Database models follow a two-tier design: every data source has a **raw response table** and an **entity table**.

**Raw response tables** store API responses exactly as received — no type casting, no field dropping. The only transformations applied are those required by the storage format (e.g. serialising list fields to JSON strings so they fit in a column).

**Entity tables** are pure extensions of their raw counterparts. Every field from the raw response is preserved with the same value and structure. They exist to provide a stable, first-class schema ready for relationships and future enrichment — not to transform or interpret the source data.

### HandsardWebsiteResponse
Raw data fetched from the SPRS website, stored exactly as received.

### Report
Entity table extending `HandsardWebsiteResponse`.

### HandsardSittingDateResponse
Raw sitting date data fetched from the SPRS report API, stored exactly as received.

### Sitting
Entity table extending `HandsardSittingDateResponse`.

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
- **pre-commit**: For automated code checks

Run linting:
```bash
poetry run ruff check .
```

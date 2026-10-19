<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/banner-dark.svg">
  <img alt="Singapore Parliamentary Record" src="docs/images/banner-light.svg">
</picture>

A database of Singapore's parliamentary record, from the colonial Legislative Assembly of 1955 to the present Parliament. The pipeline fetches every report from SPRS, Parliament's search system, splits each report into speeches and links each speech to the member who gave it.

To read the record, use [roycehoe/hansard](https://github.com/roycehoe/hansard), the website built on this database.

## Status

The record runs from 22 April 1955 to 7 October 2026. Parliament 15 was loaded on 19 October 2026. `refresh.py` can add new sittings once a day, but it does not run on a schedule yet. The database is not published.

## What the record holds

Counted on 19 October 2026.

| | |
|---|---|
| Dates | 22 April 1955 to 7 October 2026 |
| Parliaments | 0, the colonial Legislative Assembly, to 15 |
| Sittings | 1,758 |
| Reports | 46,649 in 24 report types, among them oral answers, bills, motions and budget debates. 46,525 have text |
| Speech rows | 1,115,831 |
| Attendance rows | 139,189, all but 3 linked to a member |
| Speaker registry | 1,439 rows by Parliament, grouped into 573 people |

## How well speeches are attributed

97.9% of the body text sits in a speech linked to a member. That is 329,202,046 of 336,115,734 characters across Parliaments 0 to 15, counted by `scripts/attribution_text_share.py` on 19 October 2026 ([figures](docs/figures/2026-10-19-backfill-15.txt)). Most of the rest is text with no speaker, such as procedural lines and chamber events.

The figure counts text with a member attached. It does not say the member is the right one, and the comparison below does. [docs/vision.md](docs/vision.md#measuring-progress) gives the method, the two other rates the project tracks, and an audit that found this figure about 1.7 points high.

## How it compares

From [docs/benchmark.md](docs/benchmark.md), surveyed 18 October 2026.

| | This project | SPRS | Pair Search | sgparliament.com | Par-leh-mate |
|---|---|---|---|---|---|
| Unit of text | One row per utterance, marked speech or non-speech | One page per report | One report | One turn per printed speaker | One paragraph |
| Speech linked to a member | Yes, to a registry row | No, a printed name only | Not stated | Yes, to a member page | By cleaned name match |
| Procedural lines | Rows of their own with no speaker | Printed in the text | Not stated | Folded into the last speaker's turn | Not stated |
| Words credited to the right person | 99.4% | Not applicable | Not measured | 95.5% | Not measured |
| Published accuracy | Figures after every write, and a hand audit | None | Click rank only | None | None |
| API or download | Not yet | Undocumented JSON endpoints | None public | None | BigQuery, access required |

The 99.4% and 95.5% come from 191 reports sampled across Parliaments 0 to 14 and judged blind against SPRS ([comparison](docs/report/sgparliament-comparison-2026-10-18.md)). If the Addenda to the President's Address count as nobody's words, the figures are 98.5% and 96.8%. A hand audit on 17 October 2026 found 404 of 406 linked rows right.

## Known limits

- Records from 1955 to 1965 predate independence. They cover the colonial Legislative Assembly and the State of Singapore, not the Parliament of the Republic of Singapore.
- 124 reports have no text. Most are assent-to-bills records, which the newer SPRS system serves without text. Their bill lists are in `sitting.a2b`. Every report with text has speech rows.
- 15,913 speech rows have a speaker label but no link. 12,887 of them are "The Chairman" in reports that do not say who was in the chair ([ADR 0002](docs/adr/0002-role-holder-attribution.md)). Most of the rest are collective labels such as "An hon. Member".
- 66 reports keep speech rows from an older parser. Each needs a parser fix or a ruling before it is rebuilt.
- No hand audit covers the Parliament 15 rows yet.
- Some `title` fields carry encoding errors from the source API. `markdown_content` has the right characters.

[docs/data-dictionary.md](docs/data-dictionary.md) has the full caveats, and [docs/data-loss-register.md](docs/data-loss-register.md) lists every step that drops or changes source text.

## Repository layout

| Folder | What it holds |
|---|---|
| `gateway/` | HTTP calls to SPRS and parliament.gov.sg |
| `schemas/` | Pydantic models of the API responses |
| `services/` | Pure transforms, such as report text into speeches and names into members |
| `database/` | Table definitions |
| `crud/` | Database reads and writes |
| `populate/` | Pipeline stages, which join the folders above |
| `alembic/` | Database migrations |
| `scripts/` | Diagnostics and supervised one-off writes |
| `data/` | Hand-kept reference files, such as speaker overrides and the colonial member list |
| `docs/` | Data dictionary, decision records, audits and figures |
| `tests/` | Golden fixtures for the parser |

## Setup

Requires Python 3.11+, [Poetry](https://python-poetry.org) and Docker.

```bash
git clone https://github.com/roycehoe/hansard-scraper.git
cd hansard-scraper
poetry install
docker-compose up -d        # local PostgreSQL
python script.py            # sitting dates, sittings, attendance, speaker links, persons
```

`script.py` does not run the report stages. Fetching report HTML, parsing reports and splitting speeches are `populate_hansard_responses`, `populate_reports` and `populate_speeches` under `populate/`.

Load the speaker registry before the speaker links run:

```bash
python scripts/scrape_speakers_by_parliament.py
python scripts/load_colonial_la_speakers.py   # Legislative Assembly members before independence
python -m scripts.load_heads_of_state
```

`python refresh.py` adds the sittings published since the last stored one. [docs/refresh.md](docs/refresh.md) covers its halts and alerts.

`ruff check .` lints the code. `poetry run pytest` runs the parser fixtures against a scratch database named `hansard_launch` on port 5435, and `tests/conftest.py` refuses any other.

## Documentation

- [Data dictionary](docs/data-dictionary.md): what each table and field means, the report types, and data caveats.
- [Parsing internals](docs/parsing.md): quirks of the source HTML. Read it before changing the parser.
- [Vision](docs/vision.md): the project's goals and the current figure for each.
- [Benchmark](docs/benchmark.md): the comparison with other Singapore Hansard tools, with sources.
- [Daily refresh](docs/refresh.md): what the refresh fetches, its alerts and its halts.
- [Decision records](docs/adr/): why the parser and the linker work the way they do.

## Data source and terms

Records come from the Parliament of Singapore's Parliament Reports search system (SPRS) and the member lists on parliament.gov.sg. The content belongs to Parliament. This project is not affiliated with or endorsed by Parliament. Parliament's [terms of use](https://www.parliament.gov.sg/terms-of-use) require written permission to reproduce its content, so check them before you republish anything the pipeline fetches.

The fetcher sends one request at a time and waits at least 2 seconds between requests, retries included. It identifies itself as `hansard-scraper (+hansard@fancybinary.sg)` and backs off further on HTTP 429.

## Citation

> Royce Hoe (2026). *Singapore Parliamentary Record*. GitHub. https://github.com/roycehoe/hansard-scraper

## License

The code is under the [MIT license](LICENSE). The license does not cover the text of the reports, which belongs to Parliament.

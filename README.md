# Singapore Parliamentary Record

Pipeline and database for Singapore's parliamentary record, from the colonial Legislative Assembly (1955) to the present. Records are fetched from SPRS, parsed into individual speeches with speaker attribution, and stored in PostgreSQL.

## Coverage

Figures from the last full run, 2 to 5 June 2026. Record counts come from the `statistics.csv` export of 2 June, which is not published. Speech and attendance counts come from the database on 5 June (commit ccfcbb4 and [docs/attendance-speaker/progress.txt](docs/attendance-speaker/progress.txt)). The database itself is not published.

| | |
|---|---|
| Date range | 22 April 1955 to 7 May 2026 |
| Parliaments | 0 (colonial) through 15 |
| Sitting dates | 1,745 |
| Records | 45,302 fetched, 21,854 with full text |
| Report types | 24, of which 21 have full text: oral answers, written answers, bills, motions, ministerial statements, budget debates, and more |
| Speech start located | 21,813 of 21,854 records with full text |
| Full-text records with no speeches | About 490 of 21,854 as of 31 May: about 253 multi-speaker link indexes and about 237 procedural records that name no speaker |
| Speeches linked to a registry speaker | 235,944 of 257,344 (91.7%) |
| Attendance rows linked to a registry speaker | 96,298 of 96,500 (99.8%) |
| Sitting metadata | Attendance, PTBA, and debate sections (Parliament 13+) |
| Speaker registry | All speakers by parliament, from parliament.gov.sg |

## Quick start

Requires Python 3.11+, [Poetry](https://python-poetry.org), and Docker.

```bash
git clone https://github.com/roycehoe/hansard-scraper.git
cd hansard-scraper
poetry install
docker-compose up -d        # local PostgreSQL
python script.py            # sitting dates, sittings, attendance, speaker links
```

`script.py` no longer calls the report stages. Fetching report HTML, parsing reports and splitting speeches live in `populate_hansard_responses`, `populate_reports` and `populate_speeches` under `populate/`.

Populate the Speaker registry separately (needed before `speaker_id` foreign keys resolve):

```bash
python scripts/scrape_speakers_by_parliament.py
python scripts/load_colonial_la_speakers.py   # for pre-independence LA members
```

## Documentation

- [Data Dictionary](docs/data-dictionary.md) — entity semantics, field meanings, report types, data quality caveats.
- [Parsing Internals](docs/parsing.md) — HTML artifact details and edge cases. Read before touching parsing code.
- [Vision](docs/vision.md) — project goals and strategy.

## Data source

Records come from the Parliament of Singapore's Parliament Reports search system (SPRS) and the MP lists on parliament.gov.sg. The content belongs to Parliament. This project is not affiliated with or endorsed by Parliament. Parliament's [terms of use](https://www.parliament.gov.sg/terms-of-use) require written permission to reproduce its content, so check them before republishing anything the pipeline fetches. The fetcher caps concurrent requests and backs off on HTTP 429.

## Citation

> Royce Hoe (2026). *Singapore Parliamentary Record*. GitHub. https://github.com/roycehoe/hansard-scraper

## Known limitations

- Records from 1955–1965 predate independence and cover the colonial Legislative Assembly and the State of Singapore, not the Republic of Singapore Parliament.
- About 490 records with full text yield no speeches. About 253 are multi-speaker annex and index documents whose body is a list of links. About 237 are procedural records that name no speaker, mostly budget orders. See [docs/report/learnings.md](docs/report/learnings.md).
- Some `title` fields have encoding artifacts from the source API; `markdown_content` has correct Unicode.
- Speaker identity linking (`speaker_id`) is incomplete for colonial-era and early-parliament records.

Full details in [docs/data-dictionary.md](docs/data-dictionary.md).

## Development

```bash
ruff check .
ruff check --fix .
```

## License

[MIT](LICENSE)

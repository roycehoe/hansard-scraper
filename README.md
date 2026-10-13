# Singapore Parliamentary Record

Pipeline and database for Singapore's parliamentary record, from the colonial Legislative Assembly (1955) to the present. Records are fetched from SPRS, parsed into individual speeches with speaker attribution, and stored in PostgreSQL.

## Coverage

All figures below were queried from the database on 13 October 2026, after the speaker-link rerun of that day. The database itself is not published.

| | |
|---|---|
| Date range | 22 April 1955 to 8 April 2025 |
| Parliaments | 0 (colonial) through 14 |
| Sitting dates | 1,719 |
| Records | 41,829 fetched, 21,838 with full text |
| Report types | 23, of which 19 have full text: oral answers, written answers, bills, motions, ministerial statements, budget debates, and more |
| Full-text records with speeches | 18,795 of 21,838 |
| Full-text records with no speeches | 3,043 of 21,838; 3,032 of those are in Parliaments 0 to 11, and 1,470 of those are budget records |
| Speeches linked to a registry speaker, Parliaments 0 to 11 | 425,223 of 439,986 (96.6%) under the denominator in [docs/adr/0001-attribution-denominator.md](docs/adr/0001-attribution-denominator.md): rows with a speaker string, minus collective references and stage directions |
| Speeches linked, all rows with a speaker string | 443,132 of 461,558 (96.0%) across Parliaments 0 to 12; speeches exist only for those parliaments |
| Speeches linked, Parliament 12 | 17,909 of 18,215 (98.3%) under the same denominator; reported separately because its fetch is incomplete |
| Attendance rows linked to a registry speaker | 96,350 of 96,500 (99.8%) |
| Sitting metadata | Attendance, PTBA, and debate sections (Parliament 13+) |
| Speaker registry | 1,419 speakers by parliament, from parliament.gov.sg |

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
- 3,043 records with full text have no speech rows in the database as of 13 October 2026. 1,470 are budget records; the rest are mostly bills, motions, annex and index documents whose body is a list of links, and procedural records that name no speaker. See [docs/report/learnings.md](docs/report/learnings.md).
- Some `title` fields have encoding artifacts from the source API; `markdown_content` has correct Unicode.
- Speaker identity linking (`speaker_id`) is incomplete. The largest unlinked group is role-only strings such as "The Chairman" in Committee of Supply debates; see [docs/adr/0002-role-holder-attribution.md](docs/adr/0002-role-holder-attribution.md).

Full details in [docs/data-dictionary.md](docs/data-dictionary.md).

## Development

```bash
ruff check .
ruff check --fix .
```

## License

[MIT](LICENSE)

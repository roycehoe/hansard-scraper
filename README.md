# Singapore Parliamentary Record

Pipeline and database for Singapore's parliamentary record, from the colonial Legislative Assembly (1955) to the present. Records are fetched from SPRS, parsed into individual speeches with speaker attribution, and stored in PostgreSQL.

## Coverage

| | |
|---|---|
| Date range | 1955 – present |
| Parliaments | 0 (colonial) through 15 |
| Records | ~22,000 |
| Report types | 21 — oral answers, written answers, bills, motions, ministerial statements, budget debates, and more |
| Speaker attribution | Where source material names a speaker |
| Sitting metadata | Attendance, PTBA, and debate sections (Parliament 13+) |
| Speaker registry | All speakers by parliament, from parliament.gov.sg |

## Quick start

Requires Python 3.11+, [Poetry](https://python-poetry.org), and Docker.

```bash
git clone https://github.com/roycehoe/handsard-scraper.git
cd handsard-scraper
poetry install
docker-compose up -d        # local PostgreSQL
python script.py            # fetch and parse the full corpus
```

Populate the Speaker registry separately (needed before `speaker_id` foreign keys resolve):

```bash
python scripts/scrape_speakers_by_parliament.py
python scripts/load_colonial_la_speakers.py   # for pre-independence LA members
```

## Documentation

- [Data Dictionary](docs/data-dictionary.md) — entity semantics, field meanings, report types, data quality caveats.
- [Parsing Internals](docs/parsing.md) — HTML artifact details and edge cases. Read before touching parsing code.
- [Vision](docs/vision.md) — project goals and strategy.

## Citation

> Royce Hoe (2026). *Singapore Parliamentary Record*. GitHub. https://github.com/roycehoe/handsard-scraper

## Known limitations

- Records from 1955–1965 predate independence and cover the colonial Legislative Assembly and the State of Singapore, not the Republic of Singapore Parliament.
- ~490 documents have no speaker attribution — appendix indexes and colonial-era procedural orders where no author is named in the source.
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

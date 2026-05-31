# Singapore Parliamentary Record

A structured dataset of Singapore's parliamentary proceedings, from the colonial Legislative Assembly (1955) through the present Parliament. Every sitting, every report, every attributed speech — stored in PostgreSQL and queryable by MP, topic, date, or parliament.

Built for researchers studying Singapore's political history, legislative behaviour, and parliamentary language.

## Coverage

| Dimension | Detail |
|---|---|
| Date range | 1955 – present |
| Parliaments | 0 (colonial Legislative Assembly) through 15 |
| Records | ~22,000 parliamentary items |
| Report types | 21 categories — oral answers, written answers, bills, motions, ministerial statements, budget debates, and more |
| Speaker attribution | Extracted for all records where the source material names a speaker |
| Sitting metadata | Full attendance, permissions to be absent, and debate sections (Parliament 13+, 2015–present) |
| MP registry | All MPs by parliament, sourced from parliament.gov.sg |

## Quick start

Requires Python 3.11+, [Poetry](https://python-poetry.org), and Docker.

```bash
git clone https://github.com/roycehoe/handsard-scraper.git
cd handsard-scraper
poetry install
docker-compose up -d        # start a local PostgreSQL instance
python script.py            # fetch and parse the full corpus
```

To populate the MP registry (run separately before querying `mp_id` links):

```bash
python scripts/scrape_mps_by_parliament.py
```

## Documentation

- [Data Dictionary](docs/data-dictionary.md) — entity semantics, field meanings, all report types explained, and data quality caveats. Start here if you're working with the data.
- [Parsing Internals](docs/parsing.md) — HTML artifact details, format quirks, and edge cases. Read before touching parsing code.
- [Vision](docs/vision.md) — project goals and strategy.

## Citing this work

If you use this dataset in your research, please cite:

> Royce Hoe (2026). *Singapore Parliamentary Record*. GitHub. https://github.com/roycehoe/handsard-scraper

## Known limitations

- **Pre-independence records** from 1955–1965 cover the colonial Legislative Assembly and the State of Singapore — not the Republic of Singapore Parliament.
- **~490 documents are structurally unattributable** — appendix link indexes and colonial-era procedural orders with no named author. These are intentional exclusions, not parsing failures.
- **Some title fields contain encoding artifacts** from the source API. `markdown_content` has correct Unicode; `title` may not.
- **MP identity linking is incomplete** for colonial-era and early-parliament records.

See [docs/data-dictionary.md](docs/data-dictionary.md) for the full list.

## Development

```bash
ruff check .        # lint
ruff check --fix .  # lint and auto-fix
```

## License

[MIT](LICENSE)

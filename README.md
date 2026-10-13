# Singapore Parliamentary Record

Pipeline and database for Singapore's parliamentary record, from the colonial Legislative Assembly (1955) to the present. Records are fetched from SPRS, parsed into individual speeches with speaker attribution, and stored in PostgreSQL.

## Coverage

All figures below were queried from the database on 13 October 2026, after that day's speaker-link rerun, the approved attribution changes, the duplicate-report cleanup, the procedural-text and chair-annotation repairs, the person table, the head-of-state links, and the parse of 22 debates that had no rows. The database itself is not published.

| | |
|---|---|
| Date range | 22 April 1955 to 8 April 2025 |
| Parliaments | 0 (colonial) through 14 |
| Sitting dates | 1,719 |
| Records | 36,238 distinct records from 41,829 search hits (5,591 hits came back twice), 20,003 with full text |
| Report types | 23, of which 19 have full text: oral answers, written answers, bills, motions, ministerial statements, budget debates, and more |
| Full-text records with speeches | 19,484 of 20,003 |
| Full-text records with no speeches | 519 of 20,003; 510 of those are in Parliaments 0 to 11, mostly budget procedural orders (263), annex and link pages, and records that name no speaker |
| Speeches linked to a registry speaker, Parliaments 0 to 11 | 532,067 of 545,951 (97.5%) under the denominator in [docs/adr/0001-attribution-denominator.md](docs/adr/0001-attribution-denominator.md): rows with a speaker string, minus collective references and stage directions |
| Speeches linked, Parliaments 0 to 11, every row | 532,067 of 590,815 (90.1%), counting the 40,767 rows the parser gives no speaker |
| Body text in a linked speech, Parliaments 0 to 11 | 96.05% of 176.7M characters, counting reports with no rows and text the parser drops; from `scripts/attribution_text_share.py`, see [docs/vision.md](docs/vision.md#measuring-progress) |
| Speeches linked, all rows with a speaker string | 548,183 of 566,445 (96.8%) across Parliaments 0 to 12; speeches exist only for those parliaments |
| Speeches linked, Parliament 12 | 16,116 of 16,384 (98.4%) under the same denominator; reported separately because its fetch is incomplete |
| Attendance rows linked to a registry speaker | 96,350 of 96,500 (99.8%) |
| Sitting metadata | Attendance, PTBA, and debate sections (Parliament 13+) |
| Speaker registry | 1,434 speaker rows by parliament: 1,417 members from parliament.gov.sg and the colonial list, 17 heads of state marked as non-members; grouped into 573 persons |

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
- 519 records with full text have no speech rows in the database as of 13 October 2026. 263 are budget procedural orders; the rest are mostly annex and index documents whose body is a list of links, and procedural records that name no speaker. See [docs/report/learnings.md](docs/report/learnings.md).
- Some `title` fields have encoding artifacts from the source API; `markdown_content` has correct Unicode.
- Speaker identity linking (`speaker_id`) is incomplete. The largest unlinked group is "The Chairman" in Committee of Supply debates where the report does not say who was in the chair, followed by "Mr Deputy Speaker" on days with two Deputy Speakers; see [docs/adr/0002-role-holder-attribution.md](docs/adr/0002-role-holder-attribution.md).

- Stored speech rows can lag the parser. `populate_speeches` only parses reports that have no rows, so a parser fix reaches existing rows only through a targeted rebuild. An in-memory re-parse on 13 October 2026 found 8,614 of 19,227 Parliament 0 to 11 reports would change.
- Report text stops on 13 August 2012. SPRS serves later records through a different ID and response field that the fetcher does not use; see [docs/report/post-2012-text.md](docs/report/post-2012-text.md).

Full details in [docs/data-dictionary.md](docs/data-dictionary.md).

## Development

```bash
ruff check .
ruff check --fix .
```

## License

[MIT](LICENSE)

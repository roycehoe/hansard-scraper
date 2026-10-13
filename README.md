# Singapore Parliamentary Record

Pipeline and database for Singapore's parliamentary record, from the colonial Legislative Assembly (1955) to the present. Records are fetched from SPRS, parsed into individual speeches with speaker attribution, and stored in PostgreSQL.

## Coverage

All figures below were queried from the database on 13 October 2026, after that day's speaker-link rerun, the approved attribution changes, the duplicate-report cleanup, the procedural-text and chair-annotation repairs, the person table, the head-of-state links, the parse of 22 debates that had no rows, the refetch of 1,691 reports the search had skipped, and a guarded re-parse of 6,615 reports. The database itself is not published.

| | |
|---|---|
| Date range | 22 April 1955 to 8 April 2025 |
| Parliaments | 0 (colonial) through 14 |
| Sitting dates | 1,719 |
| Records | 37,929 distinct records from 43,520 stored search hits (5,591 hits came back twice), 21,693 with full text |
| Report types | 23, of which 20 have full text: oral answers, written answers, bills, motions, ministerial statements, budget debates, and more |
| Full-text records with speeches | 21,132 of 21,693 |
| Full-text records with no speeches | 561 of 21,693; 552 of those are in Parliaments 0 to 11, mostly budget procedural orders (266), annex and link pages, and records that name no speaker |
| Speeches linked to a registry speaker, Parliaments 0 to 11 | 564,509 of 578,359 (97.6%) under the denominator in [docs/adr/0001-attribution-denominator.md](docs/adr/0001-attribution-denominator.md): rows with a speaker string, minus collective references and stage directions |
| Speeches linked, Parliaments 0 to 11, every row | 564,509 of 624,332 (90.4%), counting the 42,767 rows the parser gives no speaker |
| Body text in a linked speech, Parliaments 0 to 11 | 96.81% of 188.1M characters, counting reports with no rows and text the parser drops; from `scripts/attribution_text_share.py`, see [docs/vision.md](docs/vision.md#measuring-progress) |
| Speeches linked, all rows with a speaker string | 580,410 of 597,709 (97.1%) across Parliaments 0 to 12; speeches exist only for those parliaments |
| Speeches linked, Parliament 12 | 15,901 of 16,137 (98.5%) under the same denominator; reported separately because its fetch is incomplete |
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
- 561 records with full text have no speech rows in the database as of 13 October 2026. 266 are budget procedural orders; the rest are mostly annex and index documents whose body is a list of links, and procedural records that name no speaker. See [docs/report/learnings.md](docs/report/learnings.md).
- Some `title` fields have encoding artifacts from the source API; `markdown_content` has correct Unicode.
- Speaker identity linking (`speaker_id`) is incomplete. The largest unlinked group is "The Chairman" in Committee of Supply debates where the report does not say who was in the chair, followed by "Mr Deputy Speaker" on days with two Deputy Speakers; see [docs/adr/0002-role-holder-attribution.md](docs/adr/0002-role-holder-attribution.md).

- Stored speech rows can lag the parser. `populate_speeches` only parses reports that have no rows, so a parser fix reaches existing rows only through a targeted rebuild. A guarded re-parse on 13 October 2026 rebuilt 6,615 reports and refused 2,078 (1,954 because the new parse would drop a line the stored rows hold, 87 refused for the same reason by an earlier role-label re-parse, 34 that would undo a hand fix, 3 that would bring back deleted rows), so some stored rows still lag the parser.
- Report text stops on 13 August 2012. SPRS serves later records through a different ID and response field that the fetcher does not use; see [docs/report/post-2012-text.md](docs/report/post-2012-text.md).

Full details in [docs/data-dictionary.md](docs/data-dictionary.md).

## Development

```bash
ruff check .
ruff check --fix .
```

## License

[MIT](LICENSE)

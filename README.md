# Singapore Parliamentary Record

Pipeline and database for Singapore's parliamentary record, from the colonial Legislative Assembly (1955) to the present. Records are fetched from SPRS, parsed into individual speeches with speaker attribution, and stored in PostgreSQL.

## Status

The data runs to October 2026. Parliament 15 was loaded on 19 October 2026. Next, a scheduled job will add new sittings every day at 04:00 Singapore time and re-check the last 14 days of reports. If a stored report has changed, the job sends an alert and leaves the stored copy as it is. It only adds rows.

## Coverage

All figures below were queried from the database on 14 October 2026, after the load of report text and sitting details from 10 September 2012 on (16,123 newer-system reports filled with text, 3,880 skipped search hits inserted, 386 sittings filled, 38,572 attendance rows built from the structured list), then stage 8 and the person stage. They predate the Parliament 15 backfill of 19 October 2026, which added the sittings from September 2025 to October 2026 ([docs/refresh.md](docs/refresh.md#the-parliament-15-backfill)); the three rows it changes give both values. The database itself is not published.

| | |
|---|---|
| Date range | 22 April 1955 to 8 April 2025; to October 2026 since the backfill |
| Parliaments | 0 (colonial) through 14; through 15 since the backfill |
| Sitting dates | 1,719; 1,758 since the backfill |
| Records | 41,809 distinct records from 47,400 stored search hits (5,591 hits came back twice), 41,678 with full text |
| Report types | 24, including oral answers, written answers, bills, motions, ministerial statements, budget debates, and more |
| Full-text records with speeches | 41,024 of 41,678 |
| Full-text records with no speeches | 654 of 41,678; 552 of those are in Parliaments 0 to 11, mostly budget procedural orders (266), annex and link pages, and records that name no speaker. The other 102 (35 in Parliament 12, 30 in 13, 37 in 14) are mostly Committee of Supply openers and procedural records that name no speaker |
| Speeches linked to a registry speaker, Parliaments 0 to 11 | 564,509 of 578,359 (97.6%) under the denominator in [docs/adr/0001-attribution-denominator.md](docs/adr/0001-attribution-denominator.md): rows with a speaker string, minus collective references and stage directions |
| Speeches linked, Parliaments 0 to 11, every row | 564,509 of 624,332 (90.4%), counting the 42,767 rows the parser gives no speaker |
| Body text in a linked speech, Parliaments 0 to 11 | 96.81% of 188.1M characters, counting reports with no rows and text the parser drops; from `scripts/attribution_text_share.py`, see [docs/vision.md](docs/vision.md#measuring-progress) |
| Speeches linked, all rows with a speaker string | 997,268 of 1,019,991 (97.8%) across Parliaments 0 to 14, of 1,068,620 speech rows |
| Speeches linked, Parliaments 12 to 14 | Under the same denominator: Parliament 12 89,536 of 90,511 (98.92%), Parliament 13 134,660 of 137,182 (98.16%), Parliament 14 208,563 of 210,646 (99.01%). Counting every row: 97.37%, 96.68%, 97.89%. Text share: 98.81%, 99.14%, 99.22%. Reported beside the headline, not in it |
| Attendance rows linked to a registry speaker | 134,916 of 135,072 (99.88%); before 10 September 2012 96,350 of 96,500, from that date 38,566 of 38,572 |
| Sitting metadata | Attendance for all 1,719 sittings; PTBA, debate sections, annexures, vernacular speeches and assent lists for the 386 sittings from 10 September 2012 |
| Speaker registry | 1,437 speaker rows by parliament: 1,417 members from parliament.gov.sg and the colonial list, 20 heads of state marked as non-members; grouped into 573 persons |

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
- [Daily refresh](docs/refresh.md): what the scheduled job fetches, its alerts and its halts.

## Data source

Records come from the Parliament of Singapore's Parliament Reports search system (SPRS) and the MP lists on parliament.gov.sg. The content belongs to Parliament. This project is not affiliated with or endorsed by Parliament. Parliament's [terms of use](https://www.parliament.gov.sg/terms-of-use) require written permission to reproduce its content, so check them before republishing anything the pipeline fetches. The fetcher sends one request at a time and waits at least 2 seconds between requests, retries included. It identifies itself as `hansard-scraper (+hansard@fancybinary.sg)` and backs off further on HTTP 429.

## Citation

> Royce Hoe (2026). *Singapore Parliamentary Record*. GitHub. https://github.com/roycehoe/hansard-scraper

## Known limitations

- Records from 1955–1965 predate independence and cover the colonial Legislative Assembly and the State of Singapore, not the Republic of Singapore Parliament.
- 654 records with full text have no speech rows in the database as of 14 October 2026. 266 are budget procedural orders; the rest are mostly annex and index documents whose body is a list of links, Committee of Supply openers, and procedural records that name no speaker. See [docs/report/learnings.md](docs/report/learnings.md).
- 131 records have no text: 106 `atbp` records (assent to bills; the newer system gives them no topic text, and the bill list is in `sitting.a2b`) and 25 others, among them 11 newer-system ids that SPRS no longer serves.
- Some `title` fields have encoding artifacts from the source API; `markdown_content` has correct Unicode.
- Speaker identity linking (`speaker_id`) is incomplete. The largest unlinked group is "The Chairman" in Committee of Supply debates where the report does not say who was in the chair, followed by "Mr Deputy Speaker" on days with two Deputy Speakers (4,018 and 1,119 rows among those added by the 14 October load); see [docs/adr/0002-role-holder-attribution.md](docs/adr/0002-role-holder-attribution.md).

- Stored speech rows can lag the parser. `populate_speeches` only parses reports that have no rows, so a parser fix reaches existing rows only through a targeted rebuild. A guarded re-parse on 13 October 2026 rebuilt 6,615 reports and refused 2,078 (1,954 because the new parse would drop a line the stored rows hold, 87 refused for the same reason by an earlier role-label re-parse, 34 that would undo a hand fix, 3 that would bring back deleted rows), so some stored rows still lag the parser.

Full details in [docs/data-dictionary.md](docs/data-dictionary.md).

## Development

```bash
ruff check .
ruff check --fix .
```

## License

[MIT](LICENSE)

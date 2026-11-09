# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@STYLE.md

## Goal and how progress is measured

The goal is in `docs/vision.md`. Its "Measuring progress" section holds the current verdict per objective, the open gaps, and where more work stops paying. Read it before planning work or reporting results.

- Run `python scripts/attribution_text_share.py` before and after any change to parsing or linking, and quote all three numbers it logs: the ADR 0001 rate, the all-rows rate, and text share. The ADR 0001 rate alone rises when the parser sets rows to NULL, so it can hide a regression.
- Every write to the speech table, and every round of links, ends with `python scripts/attribution_text_share.py --output docs/figures/YYYY-MM-DD-<write>.txt`, run on the replica after the write, and the file is committed. The file holds the same lines with the figures by report type and Parliament, the zero-row count and the single-speaker collapse share. To prove a rehearsal copy or the production database holds what the replica holds, run `python -m scripts.compare_table_hashes URL_A URL_B`: it reads both databases read only and prints each table's row count and content hash, so a table that differs is named.
- Before any write to the speech table, run the shared-link check (Royce's rule D1, amended 30 October 2026). A shared paragraph link carries the row's ordinal and first 8 words (`?s=&q=`). Read only, resolve the link of every stored row in the reports the write touches against the rows the plan leaves, with the site's own `get_speech_anchor` and `get_linked_speech_ordinal` (hansard `api/utils/speech_link.py`). Count the links that land on a paragraph with different opening words, on a different row with the same words, and on no paragraph (the site's "no longer in this report" note). The write goes ahead when the first two counts are zero or close to it. No script in this repo runs the check yet.
- Run every `apply_fresh_parse --commit` and `apply_speaker_links --commit` from a clean worktree of committed master (`git worktree add <dir> <commit>`, with `.env` symlinked and `PYTHONPATH=<dir>`), never from the shared working tree. The commit rebuilds its plan with whatever parser it imports, so another agent's uncommitted edits change the plan, and on 2 November 2026 the first write #12 attempt refused with "The plan differs from the reviewed plan" for that reason.
- A passing `diagnose.py` or `run_sanity_check.py` does not mean speeches are correct; see the table in that section.
- When a figure there moves, replace the current figure in the same change, and move the column and the paragraph it replaces to `docs/report/figures-history.md`.

## Data loss register

`docs/data-loss-register.md` records everything the pipeline loses between the raw API responses and any derived table. Any change that cleans data adds or updates a row there in the same change, or it is not done. Cleaning means dropping, merging, deduplicating, trimming, normalising, overriding, reclassifying or deleting anything the source holds. It covers parsing and speech rows, and also attendance, persons, memberships, sittings, report titles and the hand overrides in `data/`. The row says what is lost, where in code, why, the cost in counts, whether it can be rebuilt from the raw tables, and who decided.

Where the record prints something, store what it prints and put our reading in a note, as `speech.column_start` keeps the printed column and `column_note` with `column_suggested` holds our reading. See `docs/adr/0013-store-what-the-record-prints.md`.

## Commands

```bash
# Install dependencies
poetry install

# Start local Postgres (matches default DATABASE_URL)
docker-compose up -d

# Run linting
ruff check .
ruff check --fix .
ruff format .

# Type check (fails only on errors not in .basedpyright/baseline.json)
poetry run basedpyright

# Run the main scraping/processing pipeline
python script.py

# Database migrations (Alembic)
python -m alembic upgrade head          # apply all pending migrations
python -m alembic check                 # verify DB matches models (no pending changes)
python -m alembic revision --autogenerate -m "describe change"  # generate a new migration
python -m alembic downgrade -1          # roll back one migration

# Scrape speakers by parliament (run separately, not part of script.py)
python scripts/scrape_speakers_by_parliament.py          # a dry run; add --commit to write

# Daily refresh: adds new sittings, reports and speech rows (--allow-parliament N accepts one new Parliament, for a supervised backfill)
python refresh.py

# Load one Parliament's members into the Speaker table (a dry run unless --commit)
python scripts/load_parliament_speakers.py --parliament N
```

`poetry run pytest` runs the golden fixtures in `tests/`: each is a trimmed source HTML excerpt plus the speech rows the parser must produce. Each parser fix adds a fixture for the defect it closes. Tests run only against the scratch database on port 5435 (`hansard_launch`), and build their own schema there; `tests/conftest.py` refuses any other target.

A push to master deploys the refresh job to production: the `refresh` job of the `hansard` DigitalOcean app has `deploy_on_push: true`. Run `poetry run pytest` before every push.

## Architecture

This is a scraper for Singapore Parliament Hansard records (sprs.parl.gov.sg). The pipeline runs in stages — each stage's output feeds the next — and `script.py` is the orchestration file that runs stages 5 to 9 (sitting dates, sittings, attendance, speaker links, persons) in order, with the sitting details fill (`populate/sitting_details.py`) after stage 6, so stage 8's Deputy Speaker rule can read `sitting.sections`. Stages 2 to 4 (`populate/hansard_responses.py`, `populate/reports.py`, `populate/speeches.py`) are not part of `script.py`; the daily refresh below adds their rows.

### Layer rules

Each folder has a strict responsibility boundary. `populate/` is the only layer that may combine gateway calls, service transforms, and DB writes.

| Layer | Responsibility | Forbidden |
|---|---|---|
| `schemas/` | Pydantic models for external data shapes: API bodies and `data/` files | DB access, logic |
| `gateway/` | HTTP calls; return parsed Pydantic models from `schemas/` | Business logic, DB writes, interpreting a missing field |
| `services/` | Pure transforms: input data → output entity | HTTP calls, DB access |
| `database/` | SQLModel table class definitions | Logic of any kind |
| `crud/` | DB read/write helpers | Business logic, HTTP |
| `populate/` | Pipeline stages: orchestrate gateway + services + crud | — |
| `utils/` | Shared pure functions | DB access, HTTP |
| `scripts/` | One-off diagnostics: use Session + crud + services, and may call gateways | Raw SQL, direct `select()`/`session.add()` bypassing crud |

Every request to SPRS or parliament.gov.sg goes through `paced_request()` or `paced_request_async()` in `gateway/http.py` and sends `CRAWL_HEADERS`.

### Data flow

1. **Fetch search index** (`gateway/hansard_search.py`): POST to the Hansard search API, paginate through all results, return `list[HansardSearchResult]` (Pydantic model in `schemas/hansard_search_result.py`); a non-list body is an empty page.

2. **Fetch report HTML** (`populate/hansard_responses.py` + `gateway/hansard_topic.py` + `services/hansard_website.py`): for each search result, `populate` calls `gateway` to POST to `getHansardTopic` with a JSON body, which returns a `HansardTopicResponse` (`schemas/hansard_topic_response.py`). The fetch picks the id and the field by system (`services/hansard_website.py::get_topic_id` and `get_topic_html_content`): an older-system hit (`report_version` sprs2, sittings before 10 September 2012) is fetched by `html_file_name` and read from `htmlContent`; a newer-system hit (sprs3) is fetched by `report_id` without its trailing `#` and read from `resultHTML.content`. Both land in `HansardWebsiteResponse.content` through `build_hansard_website_response` (see `docs/adr/0003-newer-system-raw-mapping.md`). Newer-system atbp reports return no text and keep `content` null. Hits listed in `data/excluded_report_ids.json` (a stored report returned again under another id, with the id of the copy kept) are never inserted, and stage 3 builds no report from their raw rows. `populate/hansard_response_contents.py` and `populate/report_contents.py` fill `content` and `markdown_content` in place on rows stored without text.

3. **Parse into Report** (`services/report.py`) — converts `HansardWebsiteResponse` → `Report`. Parses the `title` field to split off a `subtitle` (the trailing parenthetical, when it holds a lowercase letter; brackets elsewhere stay in the title). The title is trimmed, loses HTML tags, and a title repeated around commas outside brackets keeps one copy; `original_title` keeps the source form. Also converts HTML content to cleaned markdown via `utils/markdown_parser.py`. An older-system hit of 2003 to 2011 carries no sitting number, so it is read from the `Sitting No` line of the report's header table (`utils/markdown_header.py`).

4. **Parse into Speeches** (`services/speech.py`) — walks the markdown line-by-line to find where speeches begin (by matching the report title in bold), then splits the transcript into `Speech` records by detecting bold speaker names (`**Name:**`). `build_speeches` numbers the records and gives each its report's sitting date and report type. Newer-system reports (sprs3) start at the top of the body, because their text never repeats the title; `utils/markdown_parser.py` also cleans their HTML differently (empty emphasis tags and `(proc text)` markers go). Every such branch is guarded by `report_version`, so older-system output is unchanged.

5. **Fetch sitting dates** (`gateway/hansard_report.py` + `populate/hansard_sitting_dates.py`) — for each unique sitting date seen in the search results, POST to `getHansardReport/` with a JSON body (`{"sittingDate": "DD-MM-YYYY"}`, zero padded) to retrieve full sitting metadata. The gateway picks the schema by the shape of the body (a `metadata` key means the nested format) and the stage dispatches on the model type. Stores the result in `HansardSittingDateResponse`; the attendance and PTBA lists are stored as raw JSON strings on that table, and the other nested lists have columns only on `Sitting`. `populate/sitting_details.py` fills null columns in place on sittings stored without their details.

6. **Parse into Sittings** (`services/sitting.py` + `populate/sittings.py`) — converts `HansardSittingDateResponse` → `Sitting`, adding a `markdown_content` field parsed from `html_full_content`. The nested JSON columns (sections, annexures, vernaculars, a2b) have no raw column (ADR 0003), so stage 6 leaves them NULL; `populate/sitting_details.py` fetches them when `script.py` runs, and the daily refresh sets them from the response it fetched. An older-system response has no session number and sometimes no sitting number; both are read from the header table of the sitting's HTML.

7. **Extract attendance** (`services/attendance.py` + `populate/attendances.py`) — for each `Sitting`, parses the PRESENT/ABSENT sections from `markdown_content` and writes one `Attendance` row per name found. Sittings with no markdown (every sitting from 10 September 2012) take their rows from the structured `attendance_list` instead, with the same name cleaning and resolution. The constituency in each row's bracket goes through `data/constituency_names.json`, which turns typos and variant spellings into the Elections Department's name and leaves seat types printed in place of a constituency ("Nominated Member", "ex-officio") and other text as printed. A "GRC" suffix is dropped, since the Elections Department leaves it out of the division's name. A list ends at the first line that is not a name entry (a heading, a table row, a line that opens with bold or an asterisk, a date line, or an entry that carries a heading glued to its end). A line in the list with neither a title nor a bracketed constituency is skipped, a name that holds markup is never kept, and a member listed twice in a sitting keeps one row, the present one. Skips sittings already processed.

8. **Wire Speaker foreign keys** (`services/speaker_link.py` + `populate/speaker_links.py`) — resolves speaker/attendee names against the `Speaker` table and sets `speaker_id` on `Attendance` and `Speech` rows. `services/speaker_link.py` holds the resolver (`resolve_speech_rows`, `resolve_attendance_rows` and their helpers); `populate/speaker_links.py` keeps the session-taking passes and entry points. Depends on the `Speaker` table being populated first (see out-of-band step below). The printed office of each attendance entry follows stage 7 and stage 8: `populate/attendance_offices.py` stores it in `attendance_office` against the attendance row stage 7 wrote, and `populate/office_printed_ranges.py` builds `office_printed_range` from the rows whose attendance row stage 8 has linked.

**Out-of-band:** `scripts/scrape_speakers_by_parliament.py` scrapes `parliament.gov.sg` for the full list of speakers per parliament and stores them in the `Speaker` table. This must be run before step 8; it is not part of `script.py`. The source gives one party and one Assembly flag per person, so `data/speaker_overrides.json` corrects the flag and the party per Parliament row, both at scrape time (`services/speaker.py`) and on stored rows (`scripts/apply_speaker_overrides.py`). For colonial-era Legislative Assembly members, run `scripts/load_colonial_la_speakers.py` first. A member who sat only in the Assembly is a Parliament 0 row, and one who sat in both bodies has one row in Parliament 1; `scripts/apply_speaker_parliaments.py` moves stored rows to the Parliament the two colonial data files give them, and runs before the loaders and `apply_speaker_overrides.py` read the changed files. `data/unscraped_members.json` holds the Parliament 13 row of Lee Li Lian, who declined the seat the Hansard still lists her for, so the scrape omits her; `scripts/load_colonial_la_speakers.py` reads it with the colonial file and inserts it after the Parliament moves, and `scripts/clean_attendance.py` needs it to link her six attendance rows. A few members changed party inside one Parliament while a `Speaker` row holds only the ballot party, so `data/party_affiliations.json` records their dated party history; run `python -m scripts.load_party_affiliations` once the `Speaker` table is final (after `apply_speaker_parliaments.py`, the loaders and `apply_speaker_overrides.py`), because it finds each Membership by name and Parliament and refuses unless the stored party is one of the spans' parties.

### Daily refresh

`refresh.py` runs `populate/refresh_runs.py` once a day. It only adds rows: new raw report and sitting rows, their reports, speech rows, sittings and attendance, with stage 8 run on the new rows only and, after it, the askers of the new parliamentary question reports stored in `report_asker` and their participants and states stored in `report_participant` and `report_question_state`, then the printed office of each new attendance entry in `attendance_office`, the office each new question report was put to in `report_put_to`, the ministries of each new printed title in `office_title_ministry` (inserts only; it never writes `ministry` or `ministry_see_also`), and the new sittings' extension of `office_printed_range`. It never re-parses or rewrites a stored row, except that extending `office_printed_range` updates a Member's latest range. It commits one month at a time and halts on a new Parliament number, on a field the mapping loses, or when more than 5% of a month's new named speech rows have no registry link; a halt keeps the months before it. A run also ends `FAILED` when every topic answer it fetched has no text (new non-atbp hits plus rechecks); earlier months stay committed. After the last month it runs `VACUUM (ANALYZE)` on `speech`, `report` and `attendance` before it marks the run `SUCCEEDED`, and a VACUUM that fails or is skipped fails the run. After the VACUUM the run stores the report links of the full corpus that the table lacks, inserting only, and sends an alert for each stored link that differs from the plan; a failure there fails the run. Each run is one `refresh_run` row with its counts and status. A scheduled run cannot commit a `docs/figures/` file, so every run stores the figures in `refresh_run.figures` instead, including a run that adds nothing, so the figures catch up with a supervised write by the next morning; supervised writes still commit theirs. A run sends two alerts about offices: one when a new sitting is dated earlier than the latest sitting with an office row, in which case it writes no range for that month, and one for printed titles with no ministry, which repeats on each run that prints them until they are on the hand-kept list. See `docs/refresh.md`.

### Sitting date API — two formats

The `getHansardReport/` endpoint returns two distinct formats depending on the sitting date:

- **Old format** (sittings before 10 September 2012): flat body, all fields at top level, parsed as `HansardReportOldResponse`.
- **New format** (sittings from 10 September 2012): nested body with a `metadata` object plus child lists (`attendanceList`, `ptbaList`, `takesSectionVOList`, `annexureList`, `vernacularList`, `a2bList`), parsed as `HansardReportNewResponse`. It carries no full-sitting HTML.

Both schemas live in `schemas/hansard_report_response.py`; every field is `Optional` because the endpoint also answers with `{errorCode, description}`. `gateway/hansard_report.py` strips NUL bytes and picks the schema by the presence of the `metadata` key, and `services/hansard_sitting_date_response.py` exposes `build_old_hansard_sitting_date_response` and `build_new_hansard_sitting_date_response`, which `populate/hansard_sitting_dates.py` dispatches on the model type. `settings.sitting_date_format_change` (`datetime(2015, 8, 18)`) is read only by `scripts/validate_api_field_mapping.py`.

### Database models

Two-tier design: every data source has a **raw response table** and an **entity table**.

**Raw response tables** store API responses exactly as received. No type casting, no field dropping. The only transformation allowed is what storage requires (e.g. serialising list fields to JSON strings so they fit in a column).

**Entity tables** are pure extensions of their raw counterparts — every field from the raw response is preserved with the same value and structure. They exist to provide a stable, first-class DB schema ready for relationships and future enrichment, not to transform or interpret the source data. The one exception: where the raw response leaves a sitting or session number NULL, `Report` and `Sitting` fill it from the header table of the stored text, so those columns can differ from the raw row (see `docs/data-loss-register.md`).

- `HansardWebsiteResponse` — raw API response, one row per Hansard entry
- `Report` — entity table extending `HansardWebsiteResponse`; has a one-to-many to `Speech`; `column_start` and `column_end` hold the printed column range of an older-system report, set by `scripts/apply_column_numbers.py`
- `Speech` — individual utterance with `speaker`, `transcript`, and `ordinal` within the report; has a `speaker_id` FK to `Speaker` (populated in stage 8) and a `kind` (`SpeechKind` enum, Postgres type `speechkind`) saying what the row's text is: SPEECH, PROCEDURAL, CHAMBER_EVENT, EDITORIAL_NOTE, DOCUMENT_TEXT, HEADING or UNCLASSIFIED (see `docs/adr/0009-speech-kind-column.md`); `sitting_date` is NOT NULL and copies its report's date, which every writer sets, so a rum index can return word matches in date order (see `docs/adr/0010-speech-sitting-date-set-by-each-writer.md`); `report_type` is NOT NULL and copies its report's type the same way, so both rum indexes can filter word matches by type (see `docs/adr/0014-speech-report-type-set-by-each-writer.md`); `column_start` is the printed column the row starts in, kept as printed even when it is a likely misprint, and `column_note` (`ColumnNote`, Postgres type `columnnote`) with `column_suggested` carries our reading of it: a likely misprint and the column the marker sequence suggests, a speaker named in the column before, or a marker printed with the letter l for the digit 1
- `HansardSittingDateResponse` — raw API response, one row per sitting date; handles both old and new API formats with all fields `Optional`
- `Sitting` — entity table extending `HansardSittingDateResponse`; adds `markdown_content` parsed from `html_full_content`, plus four JSON TEXT columns (`sections`, `annexures`, `vernaculars`, `a2b`) serialised from the API nested lists
- `Attendance` — one row per name per sitting, parsed from `Sitting.markdown_content` in stage 7; has a `speaker_id` FK to `Speaker` (set in stage 8)
- `Speaker` — everyone who appears in the Hansard record, scraped from parliament.gov.sg; keyed by name, party, parliament number, and whether they are a Legislative Assembly member (not all are MPs)
- `PartyAffiliation` — one row per party a Membership sat for, with the date it began (`started_on`, and `started_on_precision`, a `DatePrecision` of DAY or MONTH, Postgres type `dateprecision`; a MONTH date is stored as the first of the month), `is_started_on_upper_bound` (true when `started_on` is the earliest day a source shows the new party, not the day of the change), one plain sentence for the footnote (`event`), exactly one source (`source_url` for a page outside the corpus, or `source_report_id`, an FK to `Report`, for a Hansard report in it; a check constraint holds this), and a `speaker_id` FK to `Speaker`; the `Speaker` row keeps the ballot party and this table adds the history
- `PersonNameSpelling`: one row per person and spelling in a spelling note, loaded by stage 9 from `data/person_name_spellings.json`, and the site reads it: `ordinal` (the order within the person, unique with `person_id`), `spelling` (unique with `person_id`), `kind` (`PersonNameSpellingKind`, Postgres type `personnamespellingkind`: CANONICAL for the row that equals `person.canonical_name`, OTHER_SPELLING, TRANSLITERATION, or OTHER_NAME for a printed name that is not a spelling of it), `note` (a sentence whose sources are `[name](link)` links to an https address or a `/reports/` page) and a `person_id` FK to `Person`; see `docs/adr/0017-elected-members-take-the-elections-departments-spelling.md`
- `Bill` — one row per bill, grouped from the `bill` and `bill-intro` reports and the reports of another type whose title ends in Bill and which hold a reading line, by `services/bill.py`: `title` as the group's last report prints it, `title_key` (lower case letters and digits of the title), `first_sitting_date` and `last_sitting_date`, and `is_passed` (the group closes on a third-reading line); `bill_number` (`N/YYYY`, indexed) with `bill_number_source` (a `BillNumberSource`, Postgres type `billnumbersource`: BILLS_SUPPLEMENT_LISTING or EGAZETTE_BILLS_SUPPLEMENT) is the Supplement number of the one entry whose title key equals the bill's (less a leading "the") and whose window holds one of the bill's first readings (the 35, 18, 9 or 4 days before the listing's publication date by era, or a day either side of the eGazette's printed first reading), set only when one distinct number matches the bill and that number matches one bill, the listing preferred where both sources agree; `bill_class` (a `BillClass`, Postgres type `billclass`: SUPPLY for a supply or appropriation title, REPEAL for a repeal title that is not an amendment, otherwise NULL). Two groups become one bill when a head (not passed, with a first reading) and a tail (passed, without one) are 1 to 800 days apart, their title keys are at least 0.85 similar, no other head claims the tail and no Supplement entry of the tail's title published between them carries another number; `act_number` (`N/YYYY`) with `act_number_source` (an `ActNumberSource`, Postgres type `actnumbersource`: ACTS_SUPPLEMENT_LISTING) is the Act number of the Acts Supplement entries whose title key equals a passed bill's and whose publication date falls from one day before to 120 days after the bill's last report, set only when exactly one distinct Act number matches; it is a claim that the bill became an Act that was published, whose text the project does not hold, and says nothing about whether the Act is in force (Royce's ruling of 8 November 2026); `repealed_act_url` with `repealed_act_url_source` (a `RepealedActUrlSource`, Postgres type `repealedacturlsource`: REPEALED_ACTS_LISTING) is the SSO page of a repealed, spent, expired or omitted Act, set for a passed bill when exactly one distinct SSO code of `RepealedActEntry` rows has the bill's loose title key (status words removed) and fits its dates (an amendment bill: enacted by its first report's year and repealed on or after its last report; any other bill: enacted in its first or last report's year); it says only that the bill's title matches an Act SSO lists as repealed, spent, expired or omitted and that the bill's dates fit that Act's enactment year and life (Royce's direction of 8 November 2026)
- `BillsSupplementCapture` — one row per Internet Archive capture of an SSO Bills Supplement listing page, as received: `original_url`, `archive_timestamp`, `capture_url` (unique) and the page `content`
- `BillsSupplementEntry` — one row per listing row across the captures, unique on `bill_number` and `link`: `printed_title`, `printed_number` ("Bill N of YYYY" as printed), `link` and `pdf_link` with `pdf_size` as printed, `bill_number` (`N/YYYY`), `publication_date` (the link's DocDate) and a `capture_id` FK to `BillsSupplementCapture`
- `ActsSupplementCapture` — one row per Internet Archive capture of an SSO Acts Supplement listing page, as received: `original_url`, `archive_timestamp`, `capture_url` (unique) and the page `content`
- `ActsSupplementEntry` — one row per listing row across the captures, unique on `act_number` and `link`: `printed_title`, `printed_number` ("Act N of YYYY" as printed), `link` and `pdf_link` with `pdf_size` as printed, `act_number` (`N/YYYY`), `publication_date` (the first eight digits of the link's DocDate, never the `/Published/` segment, which is a revised-edition date) and a `capture_id` FK to `ActsSupplementCapture`
- `RepealedActsCapture` — one row per Internet Archive capture of the SSO Repealed Acts listing page, as received: `original_url`, `archive_timestamp`, `capture_url` (unique) and the page `content`
- `RepealedActEntry` — one row per Act across the captures, unique on `sso_code`: `printed_title` (with its `(Repealed)`, `(Spent)` or `(Omitted)` status as printed), `printed_chapter` ("Cap. 2" as printed, NULL where the capture prints no chapter), `link`, `sso_code` (the code in the link's path), `enactment_year` (the trailing four digits of the code, NULL where it has none), `repeal_date` (the 8 digits after `/Repealed/` in the link), `last_version_date` (the first eight digits of the link's DocDate) and a `capture_id` FK to `RepealedActsCapture`
- `EgazetteSupplement` — one row per eGazette Bills or Acts Supplement PDF fetched by `scripts/fetch_egazette_supplements.py`; the PDF stays a file outside the repository: `url` (unique), `year`, `supplement_kind` (an `EgazetteSupplementKind`, Postgres type `egazettesupplementkind`: BILLS or ACTS), `number` (the file's number in its year), `file_path`, `size_bytes`, `sha256`, `fetched_at`, the fields read from its first pages (`printed_title`, `printed_bill_number`, `bill_number` as `N/YYYY`, `first_reading_date`, and for an Acts Supplement `passing_date` and `printed_act_number`, NULL where the PDF prints none), and for an Acts Supplement a `bill_id` FK to `Bill` with `bill_link_source` BILL_NUMBER_PASSING_DATE, set when exactly one bill carries its bill number and a third-reading report of that bill falls on the printed passing date
- `BillReport` — one row per report of a bill, unique on `bill_id` and `report_id`; a report belongs to one bill, because the grouping reads one title key per report; `role` (a `BillReportRole`, Postgres type `billreportrole`): READING for a report grouped as a reading of the bill, BUDGET_DEBATE for a `budget` report (the Budget Statement, a Committee of Supply head, the Estimates) attached to the year's Supply Bill, so a reader can tell a head's debate from a reading (Royce's direction of 8 November 2026)
- `Act` — one row per current Act of the SSO harvest: `sso_code` (unique) and `title` as the SSO browse page prints it. The Act's text is not stored (`docs/data-loss-register.md`)
- `ActHistoryEntry` — one row per entry of an Act's Legislative History, unique on `act_id` and `ordinal`: `printed_text` (the entry as printed, page-break noise removed), `printed_law_number`, `printed_title`, `printed_bill_number` (only an `N/YY` or `N/YYYY` form, as printed), the first, second and third reading dates and the commencement date (NULL where the source prints no usable date), `kind` (an `ActHistoryEntryKind`, Postgres type `acthistoryentrykind`), `bill_id` (an FK to `Bill`, NULL when no bill matches) and `bill_link_source` (a `BillLinkSource`, Postgres type `billlinksource`, saying which reading date, the looser or similar title rule, or a hand-kept link, matched)
- `ReportAsker` — one row per asker of a parliamentary question in a report: `ordinal` (order of first appearance, unique with `report_id`), `printed_name` as the record prints it, `source` (a `ReportAskerSource`, Postgres type `reportaskersource`, saying which rule found the name), `reader_printed_name` (the member who read out a question that stood in an absent member's name, otherwise NULL), a `report_id` FK to `Report`, a `speaker_id` FK to `Speaker` that is NULL when the printed name resolves to no single Membership, and a `reader_speaker_id` FK to `Speaker` for the reader
- `ReportParticipant` — one row per person and role in a parliamentary question report, so a member who holds two roles has two rows: `ordinal` (unique with `report_id`), `role` (a `ParticipantRole`, Postgres type `participantrole`), `role_source` (a `ParticipantRoleSource`, Postgres type `participantrolesource`, saying which rule found the role), `first_ordinal` (the `speech.ordinal` of the person's first row in that role), `printed_name` as the record prints it, `answering_for_printed` (the "for the" or "on behalf of the" bracket as printed, otherwise NULL), `office_printed` (the office as its source prints it), `office_class` (an `OfficeClass`, Postgres type `officeclass`), `office_source` (an `OfficeSource`, Postgres type `officesource`, saying which source gave the office), a `report_id` FK to `Report`, and a `speaker_id` FK to `Speaker` that is NULL when the printed name resolves to no single Membership
- `ReportQuestionState` — one row per report and state that the record prints for a parliamentary question: `state` (a `QuestionState`, Postgres type `questionstate`), `printed_text` (the line or title that shows it), `first_ordinal` (the `speech.ordinal` of the row that prints it, NULL when the title does), and a `report_id` FK to `Report`; unique on `report_id` and `state`
- `AttendanceOffice`: one row per attendance entry that prints an office, built from the entry line by stage 7's reader: `office_printed` (the office as the line prints it, trimmed of commas, periods and spaces at its ends), `entry_line_printed` (the whole line), `office_class` (an `OfficeClass`, Postgres type `officeclass`), `source` (an `AttendanceOfficeSource`, Postgres type `attendanceofficesource`: AFTER_CONSTITUENCY_BRACKET, AFTER_NAME_COMMA, CHAIR_FORM or BEFORE_EX_OFFICIO_BRACKET), `extracted_at`, and an `attendance_id` FK to `Attendance`, unique
- `OfficePrintedRange`: one row per unbroken run of sittings at which one `Speaker` row's attendance entry printed the same office: `office_printed`, `office_class`, `sitting_count`, `first_sitting_date` and `last_sitting_date` (printed dates, never appointment or resignation dates; see `docs/office-dates.md`), `built_at`, a `speaker_id` FK to `Speaker`, a `first_attendance_office_id` FK to `AttendanceOffice` (unique) and a `last_attendance_office_id` FK to `AttendanceOffice`
- `ReportPutTo`: one row per office a parliamentary question report says the question was put to: `ordinal` (unique with `sprs_report_id`), `office_printed` (indexed), `printed_text` (the phrase as printed), `source` (a `ReportPutToSource`, Postgres type `reportputtosource`: ASKED_THE, TO_ASK_THE or MISPRINTED_OPENING), `first_ordinal` (the `speech.ordinal` of the row that prints it), and a `sprs_report_id` FK to `Report.report_id`
- `Ministry`: one row per name of `data/ministry_names.json`: `name` (unique); the API exposes `ministry.id`, so a rerun keeps the id of a kept name
- `OfficeTitleMinistry`: one row per printed office title and ministry it names: `office_printed` (indexed), `ordinal` (the order within the title), `source` (an `OfficeTitleMinistrySource`, Postgres type `officetitleministrysource`: CLOSED_LIST_RULE or HAND_KEPT_TITLE), and a `ministry_id` FK to `Ministry`; unique on `office_printed` and `ministry_id`. A row claims no ministry of that name existed
- `MinistrySeeAlso`: one row per sourced link between two ministries: `note`, `source_url`, a `ministry_id` FK to `Ministry` and a `see_also_ministry_id` FK to `Ministry`; unique on the pair
- `ReportLink`: one row per printed citation of another report, stored on the report that prints it: `link_type` (`ReportLinkType`, Postgres type `reportlinktype`: CORRECTION, REPLY or CONTINUATION), `rule` (`ReportLinkRule`, Postgres type `reportlinkrule`: the rule that found the one target, `PRINTED_TITLE_ON_PRINTED_DATE`, `SAME_TITLE_ON_PRINTED_DATE`, `LAST_PART_ON_PRINTED_DATE`, `TITLE_KEY_ON_PRINTED_DATE` or `HAND_KEPT_TITLE_ON_PRINTED_DATE`), `printed_citation` as the record prints it, and `source_report_id` and `target_report_id`, both FKs to `Report.report_id`; unique on source, target and link type, with a check that source and target differ. A pair printed from both sides is two rows, and the API returns it once (see `docs/adr/NNNN-a-report-link-row-is-one-printed-citation.md`)

### Key parsing logic

`utils/markdown_parser.py` — HTML → clean markdown pipeline: turns `&nbsp;` into a space (an emphasis tag holding only `&nbsp;` becomes one space), strips column/page markers, then merges consecutive bold-only lines that were split across page breaks. This merged form is required for speaker detection to work correctly. Also has `get_cleaned_sitting_markdown` for sitting HTML.

`services/speech.py::get_start_of_speech_line` — locates the line in the markdown that marks where speeches begin (the report's own title appears in bold as the first "heading" before actual speeches). Returns `None` if the title can't be matched.

`services/attendance.py`: extracts names from sitting markdown and from the structured attendance list. `build_speaker_lookups(speakers: list[Speaker]) -> SpeakerLookups` builds all six in-memory lookup dicts from a pre-loaded Speaker list (no DB access). Callers must load Speakers via `crud/speaker.py` and pass the resulting `SpeakerLookups` to `resolve_canonical_name` and `build_sitting_attendances`, the dispatcher that calls `build_sitting_attendances_from_markdown` and `build_sitting_attendances_from_list`. `resolve_canonical_name`, `SpeakerLookups` and the reference tables behind them live in `utils/speaker_resolution.py`. The resolution cascade: manual overrides → inverted-name lookup → direct lookup → bin-free lookup → word-set lookup → prefix lookup → spelling normalisation → Haji-prefix stripping → surname-only fallback. The pure name helpers (`strip_title`, which removes 25+ title prefixes such as Dr, BG, RAdm and Tuan Haji before matching, plus `normalize_name`, `period_normalize`, `strip_bin`, `invert_to_natural`, `strip_middle_haji` and `spelling_normalize`) live in `utils/names.py`, because `services/attendance.py` and `services/person.py` both need them. `infer_parliament(parlement_no, volume_no)` and `VOLUME_TO_PARLIAMENT` live in `utils/parliament_numbers.py`. CRUD projections come back as dataclasses declared beside their method (`SpeechRow`, `SpeechSpeakerRow`, `AttendanceSpeakerRow`), never tuples, and CRUD lookups are named for the columns they filter on (`get_speaker_rows_by_speaker_id_null`, `get_by_markdown_content_not_null`).

### Environment

Requires a `DATABASE_URL` env var (or `.env` file). Falls back to `postgresql://user:password@localhost:5432/postgres`.

All configurable URLs and search date bounds live in `settings.py` (`AppSettings`).

### `scripts/` directory

One-off diagnostic and analysis scripts, not part of the main pipeline.

Every script that calls `validate_can_write` ends a `--commit` run with `vacuum_analyze_written_tables` (`populate/written_tables.py`) on the tables it wrote, so search does not wait for the 04:00 refresh to get a vacuumed table. It raises `HansardWriteCheckError` when a table's `vacuum_count` did not rise, which is what Postgres leaves behind when the role lacks `MAINTAIN` or ownership. A new write script adds the call in the same change.

A write that adds, rewrites or deletes speech rows of an older-system report (Parliaments 0 to 11) also sets their column numbers again, so `speech.column_start` and its note never go stale: `apply_coverage_refill.py`, `apply_language_note_close_marks.py` and `apply_footnote_markers.py` run the column pass inside their own write, and any other such write, the speech fidelity loop's ship tools included, ends with `python -m scripts.apply_column_numbers --commit --report-id ...` for the reports it touched.

A write that adds, rewrites, deletes or relinks speech rows of a parliamentary question report (oral-answer, written-answer, written-answer-na) ends with `python -m scripts.apply_report_askers --commit --report-id ...` and then `python -m scripts.apply_report_participants --commit --report-id ...` for the reports it touched.

A write that adds, rewrites, deletes or relinks attendance rows (`clean_attendance.py` and `apply_speaker_links.py` among them) ends with `python -m scripts.apply_attendance_offices --commit`. A write that rewrites speech rows of a parliamentary question report also ends with `python -m scripts.apply_report_put_to --commit --report-id ...` for the reports it touched.

A write that adds, rewrites or deletes speech rows of any report ends with `python -m scripts.apply_report_links --commit`.

The scripts:

- `diagnose.py` — inspect parsing failures across the corpus
- `inspect_failures.py` — drill into specific failure cases
- `run_sanity_check.py`, `run_no_speech_validation.py`, `run_single_speaker_check.py` — targeted validation runs
- `run_exclusion_sanity_check.py` — analyses zero-speech (excluded) documents by checking HTML bold tags vs markdown speaker patterns
- `find_unmatched_attendees.py` — finds attendance names with no match in the Speaker table, grouped by frequency; outputs a JSON template for `colonial_la_members.json`
- `attribution_text_share.py` — the three attribution numbers in `docs/vision.md`: ADR 0001 rate, all-rows rate, and share of body text in a linked speech; also per report type within each Parliament group, with the zero-row count and the single-speaker collapse share; `--output PATH` keeps the lines in `docs/figures/`, one file per write
- `check_link_plausibility.py`: read-only check on stage 8 links: lists linked rows whose person was absent or unlisted that sitting, unlinked speaker strings outside the known-unlinkable classes, and sittings with a short attendance list; `--json FILE` keeps the review list
- `speech_speaker_match_rate.py` — samples speeches stratified by report type, applies the full `SpeakerLookups` name-resolution pipeline via `resolve_canonical_name`, reports match rate overall and by type
- `load_colonial_la_speakers.py` — idempotent load of `data/colonial_la_members.json` and `data/unscraped_members.json` into the `Speaker` table; must be run before `populate_speaker_links`; a dry run unless `--commit`
- `load_heads_of_state.py`: idempotent load of `data/heads_of_state.json` (Governors, the Yang di-Pertuan Negara, Presidents) into the `Speaker` table as non-member rows; run after `load_colonial_la_speakers.py` and before `populate_speaker_links`; a dry run unless `--commit`
- `scrape_speakers_by_parliament.py` — populates the `Speaker` table from parliament.gov.sg; a dry run unless `--commit`
- `fill_sitting_numbers.py`: fills empty `report.sitting_number`, `sitting.session_no` and `sitting.sitting_no` from the stored header tables; a dry run unless `--commit`
- `apply_report_titles.py`: rewrites stored titles and subtitles that the current title rule would change; a dry run unless `--commit`
- `apply_source_characters.py`: applies `repair_source_characters`, the parser's repair of the characters SPRS sends broken (mojibake, lost closing quotes and the lost characters with one answer, byte-order marks), to stored speech transcripts and labels and report and sitting markdown; a dry run unless `--commit`
- `apply_language_note_close_marks.py`: drops the `_` a language note left open at the start of a stored transcript, as the parser has since `69476f4`, on rows where nothing else differs from a fresh parse; counts and leaves every other difference; reruns the column pass for the reports it wrote; a dry run unless `--commit`; run as a module
- `apply_footnote_markers.py`: writes the footnote markers the parser has set after a unit letter or a possessive since the exponent test took only 2 and 3, to stored report markdown and transcripts where nothing else differs from a fresh parse; counts and leaves every other difference; reruns the column pass for the reports it wrote; a dry run unless `--commit`; run as a module
- `audit_characters.py`: read-only count of character faults (U+FFFD, mojibake, control and private-use characters, leftover HTML, unbalanced quotes and parentheses) in every stored text column, with the rows whose raw text does not hold the fault; `--output PATH` keeps the lines in `docs/figures/`
- `count_column_coverage.py`: read-only count, by system and Parliament, of the reports whose raw HTML holds "Column: N" markers, and of the stored speech rows `utils/column_numbers.py` gives a start column; checks each report range against the `Start_Col` and `End_Col` of the report head; run as a module
- `apply_column_numbers.py`: sets `report.column_start` and `column_end` and each speech row's `column_start`, `column_note` and `column_suggested` from the column markers in the raw HTML, through `populate/column_numbers.py`; `--report-id` limits it to the reports given; checks the stored counts by Parliament against its plan before it commits; a dry run unless `--commit`; run as a module
- `apply_report_askers.py`: stores the askers of each parliamentary question report (oral-answer, written-answer, written-answer-na) in `report_asker`, through `populate/report_askers.py`: finds them from the report's speech rows with the four rules of `services/report_asker.py`, resolves the printed names of a stood line and of a name in text as stage 8 does, and deletes and rewrites the rows of each report it plans; `--report-id` limits it to the reports given; checks the stored counts by Parliament group and source against its plan before it commits; a dry run unless `--commit`; run as a module
- `apply_report_participants.py`: stores the participants and question states of each parliamentary question report (oral-answer, written-answer, written-answer-na) in `report_participant` and `report_question_state`, through `populate/report_participants.py`: labels every person of the report from its speech rows with `services/report_participant.py`, takes each person's office from the first source that has one (the report's label, its MPs Speaking header, the sitting's attendance entry, a same-day label, the Parliament's most common label), and deletes and rewrites both tables' rows for each report it plans; `--report-id` limits it to the reports given; checks the stored counts by Parliament group, role, role source, office source and state against its plan, and the asker, absent filer and reader rows against the stored `report_asker` rows, leaving out the readers with role source `QUESTION_NUMBER_CALL` that only this pass records, before it commits; a dry run unless `--commit`; run as a module
- `apply_attendance_offices.py`: stores the printed office of each attendance entry in `attendance_office` through `populate/attendance_offices.py`, then deletes every `office_printed_range` row and builds the ranges again from the stored offices; `--sitting-id` limits the office rows, never the ranges; checks the stored counts by decade against its plan before it commits; a dry run unless `--commit`; run as a module
- `apply_report_put_to.py`: stores the office each parliamentary question report (oral-answer, written-answer, written-answer-na) was put to in `report_put_to`, through `populate/report_put_to.py`, read from the question row's "asked the" or "To ask the"; deletes and rewrites the rows of each report it plans; `--report-id` limits it to the reports given; checks the stored counts by decade and source against its plan before it commits; a dry run unless `--commit`; run as a module
- `apply_ministries.py`: stores the names of `data/ministry_names.json` in `ministry` and places every printed office title of `attendance_office`, `report_put_to` and `report_participant` under its ministries in `office_title_ministry`, through `populate/office_title_ministries.py`; a name kept in the file keeps its `ministry.id`; logs the titles it cannot place; checks the stored names and placements against its plan before it commits; a dry run unless `--commit`; run as a module
- `check_office_ranges_against_ministers.py`: read only; compares the printed ranges of each minister in `data/office_check_ministers.json` with the minister's known dates and writes one JSON object per flag (`RANGE_OUTSIDE_DATES`, `NO_PRINT_INSIDE_DATES`) to `--output`, which it refuses to overwrite; changes no row; run as a module
- `draw_office_check_sample.py`: read only; draws a seeded sample of at most 50 rows per group of one rule (`attendance-office`, `put-to` or `ministry`), with 15 planted errors, and writes `records.json`, `reader-packets.md` (no row key, source or group), a sealed `plant-key.json` with its SHA-256 and `summary.txt` to a directory that does not exist yet; run as a module
- `list_office_check_flags.py`: needs no database; refuses unless each packet has exactly one valid verdict from the Sonnet and the Opus reader and the plant key matches its committed hash; flags a sampled row when either reader's verdict is not `RIGHT`, scores each reader against the plants and never lists a plant as a flag; refuses to overwrite its output; run as a module
- `apply_report_links.py`: stores the links between reports that the record prints, through `populate/report_links.py`: reads every speech row that holds "please refer to" or "resumption of debate on", finds the printed citations and the dated resumption headings with `services/report_citation.py`, and places each with the rules of `services/report_link.py` and refuses an entry of `data/report_link_title_corrections.json` that the record does not print; a dry run logs the links by type and rule and the unplaced citations by reason, and `--unplaced-file` keeps them as JSON; `--commit` deletes and rewrites the table, checks the stored counts by type and rule against the plan, and runs `VACUUM (ANALYZE)` on it; run as a module
- `build_report_link_check.py`: read only; draws the report link accuracy check from the stored links, after refusing unless the stored keys equal the plan's. Stage 1 samples up to 50 links from each of five groups (correction, reply, continuation with one title, last part in the newer system, last part in the older system) and `--rule` draws stage 2 for one looser rule, grouped by decade and report type. It plants 5 wrong links per group (or per rule), writes `records/packets.json`, `records/draw-summary.txt`, the sealed `key/plant-key.json` with its SHA-256, and shuffled `batches/sonnet` and `batches/opus` trees of `packets.md` that show a random packet id and never a report id, rule or group; the output directory must not exist yet; run as a module. The readers' rules are `docs/report/report-links-check.md`
- `list_report_link_flags.py`: the report link check's flag list, read only and needing no database: refuses unless the key's SHA-256 equals the committed hash and each reader (`--sonnet-verdicts`, `--opus-verdicts`) has exactly one valid verdict for every packet, logs each reader's catches of the plants, and flags a sampled packet when either reader's verdict is not `RIGHT`; writes the flag list as JSON (never over an existing file); a reader can add a flag and never clear one; run as a module
- `apply_speaker_overrides.py`: applies `data/speaker_overrides.json` and the party values of `data/colonial_la_members.json` to stored speaker rows, and straightens the apostrophe in party; a dry run unless `--commit`
- `complete_truncated_attendance.py`: inserts the attendance rows stage 7 builds from a sitting's markdown that its stored rows lack, linked as stage 8 links them, in sittings that already hold rows (stage 7 fills a sitting with none); refuses the whole run when a short sitting holds a stored row stage 7 does not build; a dry run writes the plan file, and `--commit` builds the plan again, refuses unless it equals the reviewed file, and checks each sitting's count before it commits
- `attendance_fresh_vs_stored.py`: read-only comparison of the attendance rows stage 7 builds now with the stored rows, one JSON line per differing or watched row with its printed source lines; `--batches` writes reader files of at most 150 rows per class; run as a module
- `apply_constituency_names.py`: rewrites stored attendance location names that `data/constituency_names.json` would change; a dry run unless `--commit`
- `apply_attendance_names.py`: sets stored attendance names to the names stage 7 builds, on rows where nothing else differs; pairs the rows equal in name, presence and location first and the rest by position, and refuses a sitting whose rows differ in more than a name; a dry run unless `--commit`
- `clean_attendance.py`: deletes the attendance rows of `data/attendance_cleanup.json` that the stage 7 parser no longer builds, renames and links its corrections, and links each `Speaker` role row to the presiding officer of its date or deletes it when he has another row; a dry run unless `--commit`
- `apply_speaker_parliaments.py`: moves the stored Assembly-only speaker rows to the Parliament that `data/colonial_la_members.json` and `data/heads_of_state.json` give them; a dry run unless `--commit`
- `fresh_vs_stored.py`: read-only comparison of every report's stored speech rows with a fresh parse of its raw text, in read-only transactions over two workers; writes one JSON record per report with its status (same, ordinal only, content, no content, no start line or error), and for a content difference the differing blocks, the words lost and gained and whether only `kind` differs; `--held` marks the reports of a held file and `--report-id` limits it to the reports given; run as a module
- `apply_fresh_parse.py`: rewrites the stored speech rows and markdown of every report whose fresh parse differs, except the reports of a `--held` file and the reports that differ in `kind` only; pairs stored and parsed rows by speaker and text, keeps the ids of paired rows and the stored `kind` of a paired row whose speaker and text are unchanged, numbers every row 1..n and clears the link of a row whose speaker changes; a dry run writes the plan file, and `--commit` locks the planned reports, builds the plan again, refuses unless it equals the reviewed file, checks the written reports equal the parse, links them through stage 8 and reruns the column pass; run as a module
- `apply_speaker_links.py`: links the stored speech and attendance rows that stage 8 would link; a dry run writes the plan file, and `--commit` locks the planned rows, checks they are still unlinked, builds the plan again and refuses unless it equals the reviewed file
- `apply_coverage_refill.py`: stores the hits SPRS lists that the database lacks and fills reports stored with empty text, with their speech rows; a dry run fetches the text into the plan file, and `--commit` checks the hits are still unstored and the reports still empty, writes the plan's text and checks the speech counts; run `apply_speaker_links.py` after it
- `apply_speech_sitting_date.py`: runs migration `c93f77e499cc`, which copies `speech` with each report's sitting date and swaps the copy in, and `alembic check` in one transaction, run as a module; rolled back unless `--commit`
- `apply_speech_report_type.py`: runs migration `82478ba59541`, which copies `speech` with each report's type and swaps the copy in, and `alembic check` in one transaction, run as a module; rolled back unless `--commit`
- `load_party_affiliations.py`: idempotent load of `data/party_affiliations.json` into the `PartyAffiliation` table, run as a module; skips rows already stored and refuses when a stored row for the same speaker differs from the file; a dry run unless `--commit`
- `apply_act_links.py`: stores the bills grouped from the `bill` and `bill-intro` reports and the other-type reports whose title ends in Bill and which hold a reading line (a report whose printed title misspells its bill is grouped under the corrected title of `data/bill_title_corrections.json`, and the bills of `data/hand_kept_bills.json` are built from their listed reports, a motion's among them; the three entries of `data/hand_kept_act_links.json` link to the bill holding exactly their listed reports before any rule is tried), the Acts of a harvest directory (`--harvest-directory`: `acts.json` and one `pdftotext -layout` text file per Act, named `<sso_code>.txt`), their Legislative History entries and the link from each Act or Ordinance entry to a bill, through `populate/act_links.py`; the link takes the bill whose title key matches the entry's title and which has a report within a day of the entry's first, then third, then second reading date, failing that the one bill whose looser key (amendment and number words removed) has reports within a day of the first and third reading dates, and failing that the one bill whose title key is at least 0.85 similar to the entry's and whose first and last reports fall within a day of the first and third reading dates; the dry run logs the counts (bills, Acts, entries by kind, links by rule, unlinked entries by kind and decade, source defects, unparsed entries) and writes the plan file (`--plan-file`); the dry run also logs what the write would change against the stored rows (bills kept, updated, inserted and deleted; Acts and entries inserted, updated and deleted; linked entries that change bill); `--commit` refuses unless the plan equals the reviewed file, then applies it to the four tables (a bill is keyed by its report ids, an Act by `sso_code`, an entry by its Act's `sso_code` and `ordinal`; unchanged rows keep their ids) and checks the stored counts and rows against the plan before it commits, so a second run of the same plan writes nothing; run as a module. The plan also carries each bill's number, source and class, the split merges, the eGazette Acts links, and for each Act or Ordinance entry the bill its printed bill number names when that bill has a report within a day of the entry's first reading (`bill_number_bill_index`); that number rule is logged by outcome against the title rule (agree, disagree, title only, number only, neither) and is never the stored link. The plan also carries each passed bill's Act number from the Acts Supplement entries (`act_number`, `act_number_source`), logged by source with the count of passed bills without one, and the commit checks the stored count of bills with an Act number. The plan also carries each passed bill's repealed Act page (`repealed_act_url`, `repealed_act_url_source`), logged by source with the count of passed bills without one, and the commit checks the stored count of bills with one. The plan also attaches each `budget` report to a Supply Bill as a BUDGET_DEBATE `billreport` row (`budget_report_links`, `budget_report_count`), through `get_supply_bill_indexes_for_budget_report`: a main budget report (its title has no "supplementary", "excess" or "final") takes the main Supply Bill (title key `supply` or `appropriation` with year and number parts, then `bill`), and any other budget report takes a Supplementary, Final or Excess Supply Bill, whose window holds the report's date from 45 days before the bill's first report to 30 days after its last; a report with exactly one such bill is linked, one with two or none is not, and a report already grouped as a reading is left out; the dry run logs the linked count of the budget reports, the write logs the budget links inserted and deleted, and the commit checks the stored READING rows against the planned reports and the stored BUDGET_DEBATE rows against the planned links. Run it after `apply_bills_supplement.py`, `apply_egazette_supplements.py`, `apply_acts_supplement.py` and `apply_repealed_acts.py`, which it reads
- `fetch_egazette_supplements.py`: fetches the eGazette Bills and Acts Supplement PDFs of the years given (`--year`, repeatable) into `--output-directory/<year>/<bills|acts>/NN.pdf`, walking the file number up from 1 and ending a year's series after three files in a row answer 403, one request at a time and 3 s apart through `gateway/egazette.py`, and records every request in `fetches.json` (URL, status, size, SHA-256, fetched time); a rerun skips the files it holds. The eGazette terms (clause 11) require the attribution lines of `docs/report/bill-linking-build-2026-11-08.md` wherever the PDFs' content is reproduced
- `apply_bills_supplement.py`: stores the Bills Supplement listing captures of a directory (`--captures-directory`: `captures.json` and one HTML file per capture) in `billssupplementcapture` and their rows in `billssupplemententry`, through `populate/bills_supplements.py`; a row seen in two captures is stored once; the dry run writes the plan file (`--plan-file`) and logs the capture, entry and duplicate counts, and `--commit` refuses unless the plan equals the reviewed file and checks the stored counts; run as a module
- `apply_acts_supplement.py`: stores the Acts Supplement listing captures of a directory (`--captures-directory`: `captures.json` and one HTML file per capture) in `actssupplementcapture` and their rows in `actssupplemententry`, through `populate/acts_supplements.py`; a row seen in two captures is stored once; the dry run writes the plan file (`--plan-file`) and logs the capture, entry and duplicate counts, and `--commit` refuses unless the plan equals the reviewed file and checks the stored counts; run as a module
- `apply_repealed_acts.py`: stores the SSO Repealed Acts listing captures of a directory (`--captures-directory`: `captures.json` and one HTML file per capture) in `repealedactscapture` and their rows in `repealedactentry`, through `populate/repealed_acts.py`; an Act seen in two captures is stored once, from the first; the dry run writes the plan file (`--plan-file`) and logs the capture, entry and duplicate counts and the entries by decade of enactment year, and `--commit` refuses unless the plan equals the reviewed file and checks the stored counts; run as a module
- `apply_egazette_supplements.py`: stores one `egazettesupplement` row per PDF of a fetch directory (`--harvest-directory`: the `fetches.json` and PDFs of `fetch_egazette_supplements.py`) with the fields read from its text through `populate/egazette_supplements.py`, inserting new rows and updating changed ones by URL; the dry run writes the plan file (`--plan-file`) and logs the PDFs it could not read, and `--commit` refuses unless the plan equals the reviewed file and checks the stored rows; run as a module
- `list_bill_review_items.py`: read only; writes the review list of objective 7 (`--review-file`, JSON parsed by `schemas/bill_review_list.py`) and its summary lines (`--summary-file`, kept in `docs/figures/`): Supplement entries placed only by a loose or similar title, entries with two same-title bills in their window, unplaced entries with the bill the neighbouring numbers' first readings propose, misprinted publication dates, split-bill merges (marked when they equal a hand-kept bill), Legislative History entries whose printed bill number names a bill the title rules do not link or a different one, linked entries whose bill has no report within a day of the third reading, passed bills from 1966 with no Supplement entry, passed bills with two Act numbers of their title in the Acts Supplement window, and Acts Supplement entries whose Act number no passed bill takes (with the nearest passed bill of the title), and passed bills whose dates fit two repealed Acts of their title (`REPEALED_ACT_BILL_WITH_TWO_ACTS`); the summary gives done tests 1 to 4 of `docs/vision.md` by era (1955 to 1960, 1961 to 2005, 2006 on), and test 3 both over every passed bill and over the passed bills of no class, counting a stored repealed Act link as resolved, and the summary also gives the passed bills that link to a repealed Act's page and those resolved by that link alone; two more kinds list the budget reports with two supply bills in their window (`BUDGET_REPORT_WITH_TWO_SUPPLY_BILLS`) and those with none while a Supply Bill has a report within 120 days (`BUDGET_REPORT_WITHOUT_SUPPLY_BILL`), and a budget debates line gives the budget reports by era with a stored BUDGET_DEBATE row; run as a module after `apply_act_links.py`
- `remove_excluded_reports.py`: deletes the stored reports listed in `data/excluded_report_ids.json` and their speech, asker, participant and question state rows, after checking each against its kept copy; a dry run unless `--commit`
- `find_presiding_officers.py`: tallies the most common Speaker and Deputy Speaker per parliament from the PRESENT sections
- `trace_speaker_links.py`: read-only regression guard for stage 8 speech links: re-runs the resolver per key and compares with stored `speaker_id`
- `expand_sample.py`: expands the stratified speech sample in `docs/speech-speaker/sample.json`
- `validate_api_field_mapping.py`: checks that every non-null field in a live or synthetic API body survives the schema and the ORM mapping
- `load_parliament_speakers.py`: stores the members of one Parliament (`--parliament N`) that the `Speaker` table lacks, from parliament.gov.sg, with the overrides of `data/speaker_overrides.json`; a dry run unless `--commit`
- `draw_hand_check_sample.py`: read-only draw of the human hand check's sample. In one read-only repeatable-read transaction it streams the speech id and Parliament number of every speech row with a speaker id, ordered by the database by Parliament, report version, report type, sitting date, SPRS report id, ordinal and speech id (`COLLATE "C"` on the three string columns, so the order is byte order), splits them into the Parliament groups of `services/attribution.py::get_group` as they arrive, allocates the sample by largest remainder, and picks rows by systematic sampling from a start drawn with the seed. Writes `snapshot.json` (the drawn rows with their credited names and the next row of the report) to `--snapshot-directory`, and `draw.tsv` (speech id, group, frame position) and `draw-summary.txt` (database label, read time, seed, group counts, allocation, starts, frame hash, weight spread) to `--record-directory`. `--pilot` draws 20 rows with the pilot seed and overwrites earlier files; otherwise it draws 1,000 with the main seed, refuses when the weights spread by more than 3% and refuses to overwrite an existing file. Logs the database label, never the URL; run as a module
- `build_hand_check_plants.py`: read-only; builds one round of the human hand check's planted errors (15 wrong member, 15 non-speech line credited to a member) from rows outside the main snapshot, and writes the planted snapshot rows, a sealed key file and the key's SHA-256; the non-speech lines come from uncredited procedural rows and caption notes; leaves out role-labelled rows; refuses to overwrite a plants file or a key; `--round` picks the seed and `--previous-plants` leaves an earlier round's rows out; run as a module
- `build_hand_check_packets.py`: read-only; builds the human hand check's reader packets from a draw's snapshot and, for a rerun, a plants file: reads the stored SPRS answer (`report.content`) of every sampled and planted report and stops if one has none, matches every row to the report's paragraphs, checks a seeded 50 of the sampled reports against today's SPRS (its only requests; a gateway error, an error answer, an empty answer or more than 2 differing reports stops the build with nothing written), and writes `records/packets.json` and shuffled `batches/sonnet` and `batches/opus` trees of `packets.md` (batches of at most 50 packets or 80,000 characters, cut per reader; the Opus packets never show the script's word differences, and the Sonnet packets show them, numbered, only on inexact packets) that show a random packet id and never a speech, report or speaker id or the row's kind; the output directory must not exist yet; run as a module
- `compare_hand_check_text.py`: the hand check's published text check, read only and needing no database: reruns the normalisation and word diff of `utils/hand_check_text.py` on each packet's snapshot text and matched SPRS paragraphs, and writes a TSV of packet id, match status, the differences left, each of a taught kind marked with its kind, and any stray `**` or `__` the row holds and its matched paragraph lacks; run as a module
- `list_hand_check_flags.py`: the hand check's flag list, read only and needing no database: refuses unless each packet has exactly one valid verdict from each reader given (`--sonnet-verdicts` and `--opus-verdicts`, directories of `verdicts.jsonl` files; run 1 needs Sonnet, a later run needs at least one reader, and a run past run 2 is refused), and unless a Sonnet line on an inexact packet carries one difference class per script difference and every other line carries none; with `--key` and `--key-hash` it also refuses unless the sealed plant key's SHA-256 equals the committed hash file, then scores each given reader's catches per plant (a plant is caught when the speaker verdict is not right) and leaves the plants out of the flags; flags a sampled row when a given reader's speaker verdict is not right, the packet holds a word difference of no taught kind, the match is not found, or is inexact and not wholly explained by taught differences, or the report's live check against today's SPRS differs; `--earlier-flags` is required from run 2 and keeps every row flagged in an earlier run, each reader's verdict from its latest run; writes the flag list as JSON (never over an existing file) and a summary text file (flags by reason, speaker verdicts by reader, taught differences by kind, recall and the readers that missed a plant, match status, gap check, role credits, rows in held reports); run as a module

The speech fidelity loop has its own tools for rewriting stored speech rows. They live outside the repo's tracked tree, in the gitignored `plans/speech-fidelity-loop/bin/`. Run them only for a planned write, and follow a ship that touches Parliaments 0 to 11 with `apply_column_numbers.py --commit --report-id` for its reports.

Scripts log through `logs.logger`; the one script whose stdout is data (`find_presiding_officers.py`, paste-ready `SPEAKER_TERMS` and `DEPUTY_SPEAKER_TERMS` tuple literals) prints that output under `# noqa: T201`. `find_unmatched_attendees.py` writes its JSON template to the path given by `--json`.

## Module structure

```
hansard-scraper/
│
├── script.py                        # Pipeline orchestrator — runs populate stages 5 to 9 in order
├── refresh.py                       # Daily refresh entry point; exits 2 on a halt
├── settings.py                      # AppSettings (DATABASE_URL, API endpoints, date bounds)
├── enums.py                         # ReportType and ReportVersion (sprs2 older system, sprs3 newer system), RefreshRunStatus, PersonNameSpellingKind, ReportAskerSource, ParticipantRole, ParticipantRoleSource, OfficeClass, OfficeSource, QuestionState, LegislativeAssemblyFlag, PersonDecisionKind, HandCheckFormOfAddress, HandCheckPlantKind, HandCheckMatchStatus, HandCheckLiveCheckStatus, HandCheckAnswerStatus, HandCheckSpeakerVerdict, HandCheckDifferenceClass, HandCheckDifferenceKind, HandCheckErrorTier, HandCheckFlagReason, ActHistoryEntryKind, ActHistoryDefect, BillLinkSource, BillClass, BillNumberSource, ActNumberSource, EgazetteSupplementKind, BillEra, BillReportRole, BillReviewItemKind, AttendanceOfficeSource, ReportPutToSource, OfficeTitleMinistrySource, OfficeCheckFlagKind, OfficeCheckRule, OfficeCheckVerdictKind, ReportLinkType, ReportLinkRule, ReportLinkUnplacedReason, ReportLinkVerdict, ReportLinkPlantKind
├── exceptions.py                    # HansardError / HansardGatewayError / HansardSearchRangeError / HansardMemberListError / HansardDataFileError / HansardSittingReportError / HansardUnattributedSpeechError / HansardWriteTargetError / HansardWriteCheckError / HansardPartyAffiliationError / HansardRefreshHaltError / HansardRefreshFailureError / HansardRefreshRunError / HansardTestGuardError / HansardHandCheckError / HansardHandKeptEntryError / HansardActHistoryError / HansardSsoListingError / HansardActsSupplementError / HansardBillsSupplementError / HansardEgazetteSupplementError / HansardRepealedActsListingError / HansardOfficeCheckError / HansardReportLinkCheckError
├── logs.py                          # Loguru logger initialisation
├── Dockerfile                       # Image for the refresh job (run as `sh refresh.sh`); the build imports `refresh`, so an import error fails it
│
├── schemas/                         # Pydantic validation models (API bodies and data/ files, not DB)
│   ├── hansard_search_result.py    # HansardSearchResult — camelCase alias support
│   ├── hansard_topic_response.py   # HansardTopicResponse: the getHansardTopic body (three shapes)
│   ├── hansard_report_response.py  # HansardReportOldResponse / HansardReportNewResponse / HansardReportMetadata / HansardReportAttendanceEntry
│   ├── excluded_report_id.py       # ExcludedReportId / ExcludedReportIds: data/excluded_report_ids.json entries
│   ├── bill_title_correction.py    # BillTitleCorrection / BillTitleCorrections: data/bill_title_corrections.json entries
│   ├── hand_kept_bill.py           # HandKeptBill / HandKeptBills: data/hand_kept_bills.json entries
│   ├── hand_kept_act_link.py       # HandKeptActLink / HandKeptActLinks: data/hand_kept_act_links.json entries
│   ├── report_link_title_correction.py  # ReportLinkTitleCorrection / ReportLinkTitleCorrections: data/report_link_title_corrections.json entries
│   ├── attendance_cleanup.py       # AttendanceCleanup: data/attendance_cleanup.json entries
│   ├── party_affiliation.py        # MembershipPartyAffiliations / PartyAffiliationSpan / PartyAffiliationMemberships: data/party_affiliations.json entries
│   ├── hand_kept_member.py         # HandKeptMember / HandKeptMembers: data/colonial_la_members.json and data/unscraped_members.json entries
│   ├── person_decision.py          # PersonDecision / PersonDecisionMember / PersonDecisions: data/person_decisions.json entries
│   ├── person_name_spelling.py     # PersonNameSpellingEntry / PersonNameSpellingEntries: data/person_name_spellings.json entries
│   ├── head_of_state.py            # HeadOfStateResult / HeadsOfState: data/heads_of_state.json entries
│   ├── hand_check_office_holder.py # HandCheckOfficeHolder / HandCheckOfficeHolders: data/hand_check_office_holders.json entries, the hand check's office holders by date, each cited from an outside source and never copied from the stage 8 terms
│   ├── unattributed_speech.py      # UnattributedSpeechRange / UnattributedSpeechRanges: data/unattributed_speech.json entries
│   ├── constituency_names.py       # ConstituencyName / ConstituencyRowName / ConstituencyNames: data/constituency_names.json
│   ├── speaker_link_plan.py        # SpeakerLinkPlan: the plan file of scripts/apply_speaker_links.py
│   ├── fresh_vs_stored_report.py   # FreshVsStoredReport / FreshVsStoredReports / RowDifferences: the output file of scripts/fresh_vs_stored.py
│   ├── fresh_parse_plan.py         # FreshParsePlan / ReportFreshParsePlan / HeldReports: the plan and held files of scripts/apply_fresh_parse.py
│   ├── attendance_completion_plan.py  # AttendanceCompletionPlan / SittingAttendanceCompletion / PlannedAttendance: the plan file of scripts/complete_truncated_attendance.py
│   ├── coverage_refill_plan.py     # CoverageRefillPlan / FetchedHit / FetchedReport: the plan file of scripts/apply_coverage_refill.py
│   ├── sample_sets.py              # SampleSets: the pilot, held-out and regression report ids of the speech sample
│   ├── hand_check_snapshot.py      # HandCheckSnapshotRow / HandCheckFrameSummary / HandCheckSnapshot / HandCheckSnapshotRows: the snapshot file of the human hand check's draw (a frame summary and the drawn rows), and a bare list of the same rows
│   ├── hand_check_plant_key.py     # HandCheckPlantKey / HandCheckPlant: the sealed key file of scripts/build_hand_check_plants.py
│   ├── hand_check_packet.py        # HandCheckPackets / HandCheckPacket / HandCheckWordDifference / HandCheckGapCheck / HandCheckRoleSection: the packet records file of the human hand check
│   ├── hand_check_verdict.py       # HandCheckVerdict: one line of a reader's verdicts.jsonl in the hand check
│   ├── hand_check_flag.py          # HandCheckFlag / HandCheckFlags: the flag list of scripts/list_hand_check_flags.py
│   ├── report_link_check.py        # ReportLinkCheckPacket / ReportLinkCheckPackets / ReportLinkCheckKey / ReportLinkCheckVerdict / ReportLinkCheckFlag / ReportLinkCheckFlags and their parts: the files of the report link accuracy check
│   ├── act_link_plan.py            # ActLinkPlan / PlannedBill / SkippedReport / PlannedAct / PlannedActHistoryEntry / UnparsedEntry: the plan file of scripts/apply_act_links.py
│   ├── harvested_act.py            # HarvestedAct / HarvestedActs: the acts.json of a harvest directory
│   ├── bills_supplement_capture.py # BillsSupplementCaptureManifestEntry / BillsSupplementCaptureManifest: the captures.json of a Bills Supplement captures directory
│   ├── bills_supplement_plan.py    # BillsSupplementPlan / PlannedCapture / PlannedEntry: the plan file of scripts/apply_bills_supplement.py
│   ├── acts_supplement_capture.py  # ActsSupplementCaptureManifestEntry / ActsSupplementCaptureManifest: the captures.json of an Acts Supplement captures directory
│   ├── acts_supplement_plan.py     # ActsSupplementPlan / PlannedActsSupplementCapture / PlannedActsSupplementEntry: the plan file of scripts/apply_acts_supplement.py
│   ├── repealed_acts_capture.py    # RepealedActsCaptureManifestEntry / RepealedActsCaptureManifest: the captures.json of a Repealed Acts captures directory
│   ├── repealed_acts_plan.py       # RepealedActsPlan / PlannedRepealedActsCapture / PlannedRepealedActEntry: the plan file of scripts/apply_repealed_acts.py
│   ├── egazette_supplement_response.py  # EgazetteSupplementResponse: one eGazette PDF fetch, status and bytes
│   ├── egazette_fetch.py           # EgazetteFetchRecord / EgazetteFetchRecords: the fetches.json of scripts/fetch_egazette_supplements.py
│   ├── egazette_supplement_plan.py # EgazetteSupplementPlan / PlannedEgazetteSupplement / UnparsedEgazetteSupplement: the plan file of scripts/apply_egazette_supplements.py
│   ├── bill_review_list.py         # BillReviewList / BillReviewItem / BillEraDoneTests: the review file of scripts/list_bill_review_items.py
│   ├── ministry_list.py            # MinistryNames / OfficeTitleMinistryEntry / MinistrySeeAlsoEntry: data/ministry_names.json, data/office_title_ministries.json and data/ministry_see_also.json
│   ├── office_check_minister.py    # OfficeCheckMinister / OfficeCheckMinisters: data/office_check_ministers.json, the ministers with known dates
│   ├── office_check.py             # OfficeCheckPacket / OfficeCheckPlantKey / OfficeCheckVerdict / OfficeCheckFlag: the files of the office check drawn by scripts/draw_office_check_sample.py
│   ├── speaker_override.py         # SpeakerOverrides: data/speaker_overrides.json
│   ├── parliament_member_list_response.py  # ParliamentMemberListResponse: the member data in the parliament.gov.sg list page
│   └── speaker.py                   # SpeakerResult — party and parliament metadata
│
├── gateway/                         # HTTP API clients
│   ├── http.py                      # Crawl pacer (one request at a time, at least 2 s apart, named user agent), async POST with retry and sync `send_with_retry`, alike (a 429, a 5xx other than a "No Results Found" body, a transient 400 or a transport error; five sends)
│   ├── hansard_search.py           # Paginated Hansard full-text search
│   ├── hansard_topic.py            # Fetch report HTML by ID (sync + async)
│   ├── hansard_report.py           # Fetch sitting metadata by date (sync + async)
│   ├── speakers_by_parliament.py    # Read the member list embedded in the parliament.gov.sg page, all Parliaments or one
│   ├── egazette.py                  # Fetch one eGazette Bills or Acts Supplement PDF by year, kind and number
│   ├── telegram.py                  # Send one Telegram alert message
│   └── healthchecks.py              # Send the healthchecks.io success and failure pings
│
├── services/                        # Business logic — transforms raw data into entities
│   ├── hansard_website.py          # Pure transform: (HansardSearchResult, html_content) → HansardWebsiteResponse
│   ├── hansard_sitting_date_response.py  # Build old/new-format HansardSittingDateResponse
│   ├── report.py                    # HansardWebsiteResponse → Report (markdown + subtitle)
│   ├── speech.py                    # Report markdown → Speech list (speaker detection)
│   ├── sitting.py                   # HansardSittingDateResponse → Sitting
│   ├── attendance.py                # Sitting markdown → Attendance; build_speaker_lookups(list[Speaker]) → SpeakerLookups
│   ├── attendance_cleanup.py        # Plan for scripts/clean_attendance.py: checks the listed rows, then links or deletes each
│   ├── person.py                    # Speaker rows → person clusters (name normalisation + review decisions); spelling entries → PersonNameSpelling rows
│   ├── speaker_link.py              # Stage 8 resolver: Chairman, Deputy Speaker and carried-role names, speech and attendance rows → speaker ids
│   ├── party_affiliation.py         # Party affiliation file + Speaker rows → PartyAffiliation rows; picks the rows not yet stored
│   ├── bill.py                      # Bill report rows → bills: groups by title key, closes on a third-reading line, starts a new bill after 366 days; hand-kept bills replace the rule-built ones; bill numbers and Act numbers from the Supplement candidates
│   ├── act_history.py               # Act text → Legislative History entries: splits the entries, reads kind, titles, bill number, reading and commencement dates and source defects
│   ├── act_link.py                  # Entry title and reading dates → the bill it links to, and by which reading date; hand-kept links first
│   ├── act_link_write.py            # Stored bills, Acts and entries + the plan → what to insert, update and delete, and the first difference left
│   ├── bills_supplement.py          # Bills Supplement listing HTML → entries: printed title and number, link, bill number N/YYYY, publication date
│   ├── acts_supplement.py           # Acts Supplement listing rows → entries: act number N/YYYY from "Act N of YYYY", publication date from the link's DocDate
│   ├── repealed_acts.py             # Repealed Acts listing rows → entries: SSO code, repeal date and last version date from the link, enactment year from the code
│   ├── egazette_supplement.py       # eGazette Supplement PDF text → printed title, bill number, first reading, passing date and Act number
│   ├── api_field_mapping.py         # Fields an API body loses on its way to a row (the refresh halt and validate_api_field_mapping.py)
│   ├── attribution.py               # Speech row categories and the figures JSON for refresh_run.figures
│   ├── character_audit.py           # Character fault signatures and pair balance for scripts/audit_characters.py
│   ├── refresh.py                   # Refresh rules: dates, halt checks and alert text
│   ├── report_asker.py              # Speech rows of a parliamentary question → its askers, and the reader of a question that stood in an absent member's name
│   ├── report_participant.py        # Speech rows, askers and offices of a parliamentary question → each person's role, and the question's state
│   ├── report_put_to.py             # Speech rows of a parliamentary question → the offices it says it was put to
│   ├── office_printed_range.py      # Attendance offices and sitting dates → runs of one printed office per speaker; the extension of stored ranges
│   ├── office_title_ministry.py     # A printed office title, the closed ministry list and the hand-kept titles → the ministries it names
│   ├── report_citation.py           # Speech rows → the citations of other reports they print, and the dated resumption heading of a resumed debate
│   ├── report_link.py               # Citations, headings and report rows → planned report links by fixed rules, and the citations no rule placed
│   └── speaker.py                   # SpeakerResult → Speaker DB entity
│
├── database/                        # SQLModel table definitions
│   ├── init.py                      # Engine setup, runs Alembic migrations on startup; build_read_only_engine for the scripts that must not write
│   ├── hansard_website_response.py # Raw API response — one row per Hansard entry
│   ├── hansard_sitting_date_response.py  # Raw sitting metadata (all fields Optional)
│   ├── report.py                    # Entity: extends HansardWebsiteResponse + markdown
│   ├── speech.py                    # Entity: speaker + transcript + ordinal + speaker_id FK
│   ├── sitting.py                   # Entity: extends HansardSittingDateResponse + markdown + JSON columns
│   ├── attendance.py                # One row per name per sitting + speaker_id FK
│   ├── person.py                    # Person: one row per clustered identity
│   ├── person_name_spelling.py      # PersonNameSpelling: one row per person and spelling in a spelling note + person_id FK
│   ├── party_affiliation.py         # PartyAffiliation: dated party history within a Membership + speaker_id FK
│   ├── bill.py                      # Bill and BillReport: bills grouped from reports, and their reports
│   ├── act.py                       # Act and ActHistoryEntry: an Act's code and title, and its Legislative History entries with the bill each links to
│   ├── bills_supplement.py          # BillsSupplementCapture and BillsSupplementEntry: the archived listing pages as received, and their rows
│   ├── acts_supplement.py           # ActsSupplementCapture and ActsSupplementEntry: the archived Acts Supplement listing pages as received, and their rows
│   ├── repealed_acts.py             # RepealedActsCapture and RepealedActEntry: the archived Repealed Acts listing page as received, and its rows
│   ├── egazette_supplement.py       # EgazetteSupplement: one row per fetched eGazette PDF, its fields and the bill an Acts Supplement links to
│   ├── refresh_run.py               # RefreshRun: one row per refresh run, its counts, figures and status
│   ├── report_asker.py              # ReportAsker: one row per asker of a parliamentary question + report_id, speaker_id and reader_speaker_id FKs
│   ├── report_participant.py        # ReportParticipant: one row per person and role in a parliamentary question + report_id and speaker_id FKs
│   ├── report_link.py               # ReportLink: one row per printed citation of another report + source_report_id and target_report_id FKs
│   ├── report_question_state.py     # ReportQuestionState: one row per report and state the record prints for a question + report_id FK
│   ├── attendance_office.py         # AttendanceOffice: the printed office of one attendance entry + attendance_id FK
│   ├── office_printed_range.py      # OfficePrintedRange: a run of sittings with one printed office + speaker_id and two attendance_office FKs
│   ├── report_put_to.py             # ReportPutTo: one office a question was put to + sprs_report_id FK
│   ├── ministry.py                  # Ministry: one name from data/ministry_names.json
│   ├── office_title_ministry.py     # OfficeTitleMinistry: one printed title under one ministry + ministry_id FK
│   ├── ministry_see_also.py         # MinistrySeeAlso: a sourced link between two ministries + two ministry FKs
│   └── speaker.py                   # Speaker: name, party, parliament number, LA flag, person_id FK
│
├── crud/                            # DB read/write helpers (one file per table)
│   ├── hansard_website_response.py
│   ├── hansard_sitting_date_response.py
│   ├── report.py
│   ├── speech.py
│   ├── sitting.py
│   ├── attendance.py
│   ├── person.py
│   ├── person_name_spelling.py
│   ├── party_affiliation.py
│   ├── bill.py
│   ├── bill_report.py
│   ├── act.py
│   ├── act_history_entry.py
│   ├── bills_supplement_capture.py
│   ├── bills_supplement_entry.py
│   ├── acts_supplement_capture.py
│   ├── acts_supplement_entry.py
│   ├── repealed_acts_capture.py
│   ├── repealed_act_entry.py
│   ├── egazette_supplement.py       # Rows, updates by id and the bill links of the eGazette Acts rows
│   ├── refresh_run.py               # Run rows, with a row lock for the finish
│   ├── report_asker.py              # Askers of a parliamentary question: add, read by report, delete by report
│   ├── report_participant.py        # Participants of a parliamentary question: add, read by report, delete by report
│   ├── report_link.py               # Report links: add, read, delete by source or target report
│   ├── report_question_state.py     # Question states of a parliamentary question: add, read by report, delete by report
│   ├── attendance_office.py         # Printed offices of attendance entries: add, read by sitting, distinct titles, check rows, delete
│   ├── office_printed_range.py      # Printed office ranges: add, read by speaker, extend, delete
│   ├── report_put_to.py             # Offices a question was put to: add, read by report, distinct titles, check rows, delete
│   ├── ministry.py                  # Ministry names: add, read, delete by id
│   ├── office_title_ministry.py     # Ministries under each printed title: add, read, distinct titles, delete
│   ├── ministry_see_also.py         # Ministry see-also links: add, read, delete
│   ├── vacuum.py                    # vacuum_count and VACUUM (ANALYZE) for a table named by the caller
│   └── speaker.py
│
├── populate/                        # Pipeline stages — fetch + persist each entity type
│   ├── hansard_responses.py        # Stage 2: async fetch + store HansardWebsiteResponse
│   ├── hansard_response_contents.py # Fill: fetch text for newer-system raw rows stored without it
│   ├── report_contents.py           # Fill: copy raw text and markdown onto reports stored without it
│   ├── reports.py                   # Stage 3: HansardWebsiteResponse → Report
│   ├── speeches.py                  # Stage 4: Report → Speech (batches of 1000)
│   ├── hansard_sitting_dates.py    # Stage 5: fetch + store HansardSittingDateResponse
│   ├── sitting_details.py           # Fill: metadata and lists for sittings stored without them
│   ├── sittings.py                  # Stage 6: HansardSittingDateResponse → Sitting
│   ├── attendances.py               # Stage 7: Sitting → Attendance
│   ├── speaker_links.py             # Stage 8: resolve names → set speaker_id on Speech + Attendance
│   ├── persons.py                   # Stage 9: cluster Speaker rows into Person rows and load the spelling notes
│   ├── attribution_figures.py       # Reads report and speech rows into the attribution figures
│   ├── column_numbers.py            # Plans and writes report column ranges and speech start columns and notes, checked by Parliament
│   ├── act_links.py                 # Plans and writes bills, Acts, Legislative History entries and bill links from the reports and a harvest directory; reads the Supplement entries and eGazette rows for the bill numbers and the eGazette links
│   ├── bills_supplements.py         # Plans and writes the Bills Supplement captures and entries from a captures directory
│   ├── acts_supplements.py          # Plans and writes the Acts Supplement captures and entries from a captures directory
│   ├── repealed_acts.py             # Plans and writes the Repealed Acts captures and entries from a captures directory
│   ├── egazette_supplements.py      # Plans and writes one row per eGazette PDF of a fetch directory, from the fields its text prints
│   ├── report_askers.py             # Plans and writes the askers of parliamentary question reports, checked by Parliament group and source
│   ├── report_participants.py       # Plans and writes the participants and states of parliamentary question reports, checked by Parliament group and against report_asker
│   ├── attendance_offices.py        # Plans and writes the printed office of each attendance entry, checked by decade
│   ├── office_printed_ranges.py     # Plans and writes the printed office ranges from the stored offices; the daily extension leaves a late sitting's month alone
│   ├── report_put_to.py             # Plans and writes the office each parliamentary question report was put to, checked by decade and source
│   ├── office_title_ministries.py   # Plans and writes the ministry names and the ministries under each printed title; the daily step only inserts
│   ├── report_links.py              # Plans report links from speech rows and report rows, writes the plan, and inserts the links the daily refresh lacks
│   ├── refresh_runs.py              # Daily refresh: fetch, check, add rows, link, record the run, alert
│   ├── written_tables.py            # VACUUM (ANALYZE) the tables a supervised write script wrote, and check the count rose
│   └── speakers.py                  # Out-of-band: persist scraped Speaker records
│
├── utils/                           # Shared pure utilities (no DB, no HTTP)
│   ├── act_link_update.py           # BillUpdate / ActUpdate / ActHistoryEntryUpdate: one row's changed columns, for a bulk update
│   ├── asker_candidate.py           # AskerCandidate: one asker found in a question's speech rows, before it is resolved or stored
│   ├── column_numbers.py            # A report's column range and each speech row's start column and note, from the column markers in its raw HTML
│   ├── data_files.py                # The only module outside its own test that opens data/: one get_ function per file, each on model_validate_json
│   ├── database_label.py            # get_database_label: the host, port and database name of a database URL, never the user or password
│   ├── hand_check_text.py           # normalize_hand_check_text and get_word_differences: the text rules of the human hand check, and the taught kinds of difference that flag no row
│   ├── json_columns.py              # Serialises a nested list to the JSON text stored in a column
│   ├── markdown_header.py           # Reads a number such as Sitting No from a stored header table
│   ├── markdown_parser.py           # HTML → clean markdown; merges split bold lines
│   ├── names.py                     # Pure name helpers shared by services/attendance.py and services/person.py
│   ├── office.py                    # A member's office as the record prints it: label office and "for" bracket, header entries, office class
│   ├── office_printed_range_update.py # OfficePrintedRangeUpdate: one range row's extended end, for a bulk update
│   ├── parliament_numbers.py        # VOLUME_TO_PARLIAMENT and infer_parliament: the Parliament number of a volume
│   ├── row_counts.py                # format_row_counts: a Counter as sorted "key count" text for a script's log line
│   ├── printed_citation.py          # PrintedCitation and ResumptionHeading: the records report_citation hands to report_link
│   ├── sitting_dates.py             # Sitting-date parsing, the sitting-date key, the month windows and the old/new format cutoff test
│   ├── speaker_resolution.py        # Name resolution: build SpeakerLookups, resolve_canonical_name and the OCR and name tables behind it
│   ├── speaker_resolution_constants.py  # Reference tables for stage 8 (role terms, office holders)
│   ├── speaker_terms.py             # SPEAKER_TERMS: who presided as Speaker on which dates (stages 7 and 8)
│   ├── speech_update.py             # SpeechUpdate: one speech row's ordinal, label, text, kind and link, for a bulk update
│   ├── sso_listing.py               # parse_sso_listing and parse_sso_act_listing: the rows of an SSO Browse listing page (Bills or Acts Supplement, or Repealed Acts), as the page prints them
│   ├── title_key.py                 # get_title_key, get_bill_title_key and get_loose_title_key: the keys that match a bill title to an Act or Supplement title
│   ├── bill_number.py               # normalize_bill_number: a printed N/YY or N/YYYY bill number as N/YYYY
│   ├── egazette_supplement_update.py  # EgazetteSupplementUpdate and EgazetteLinkUpdate: one eGazette row's changed fields or bill link, for a bulk update
│   ├── text.py                      # Mojibake fix (cp1252 → UTF-8, titles and markdown), NUL stripping and TextChange, the before/after record of a bulk text write
│   └── write_target.py              # validate_can_write: the guard every write script calls before --commit
│
└── scripts/                         # One-off diagnostics (not part of pipeline)
    ├── diagnose.py
    ├── inspect_failures.py
    ├── find_unmatched_attendees.py
    ├── check_link_plausibility.py
    ├── run_sanity_check.py
    ├── run_no_speech_validation.py
    ├── run_single_speaker_check.py
    ├── run_exclusion_sanity_check.py
    ├── attribution_text_share.py
    ├── speech_speaker_match_rate.py
    ├── find_presiding_officers.py
    ├── trace_speaker_links.py
    ├── expand_sample.py
    ├── validate_api_field_mapping.py
    ├── load_colonial_la_speakers.py
    ├── load_heads_of_state.py
    ├── scrape_speakers_by_parliament.py
    ├── apply_coverage_refill.py
    ├── apply_speech_sitting_date.py
    ├── apply_speech_report_type.py
    ├── remove_excluded_reports.py
    ├── fill_sitting_numbers.py
    ├── apply_report_titles.py
    ├── apply_source_characters.py
    ├── apply_language_note_close_marks.py
    ├── apply_footnote_markers.py
    ├── audit_characters.py
    ├── count_column_coverage.py
    ├── apply_column_numbers.py
    ├── apply_report_askers.py
    ├── apply_report_participants.py
    ├── apply_attendance_offices.py
    ├── apply_report_put_to.py
    ├── apply_ministries.py
    ├── check_office_ranges_against_ministers.py
    ├── draw_office_check_sample.py
    ├── list_office_check_flags.py

    ├── apply_report_links.py
    ├── build_report_link_check.py
    ├── list_report_link_flags.py
    ├── apply_speaker_overrides.py
    ├── complete_truncated_attendance.py
    ├── attendance_fresh_vs_stored.py
    ├── apply_constituency_names.py
    ├── apply_attendance_names.py
    ├── clean_attendance.py
    ├── apply_speaker_parliaments.py
    ├── fresh_vs_stored.py
    ├── apply_fresh_parse.py
    ├── apply_speaker_links.py
    ├── load_party_affiliations.py
    ├── apply_act_links.py
    ├── fetch_egazette_supplements.py
    ├── apply_bills_supplement.py
    ├── apply_acts_supplement.py
    ├── apply_repealed_acts.py
    ├── apply_egazette_supplements.py
    ├── list_bill_review_items.py
    ├── draw_hand_check_sample.py
    ├── build_hand_check_plants.py
    ├── build_hand_check_packets.py
    ├── compare_hand_check_text.py
    ├── list_hand_check_flags.py
    └── load_parliament_speakers.py
```

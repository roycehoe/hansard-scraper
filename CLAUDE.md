# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@STYLE.md

Prose in `docs/`, this file, `STYLE.md`, `README.md` and `CONTRIBUTING.md` follows `docs/WRITING.md`.

## Goal and how progress is measured

The goal is in `docs/vision.md`. Its "Measuring progress" section holds the current verdict per objective, the open gaps, and where more work stops paying. Read it before planning work or reporting results.

- Run `python scripts/attribution_text_share.py` before and after any change to parsing or linking, and quote all three numbers it logs: the ADR 0001 rate, the all-rows rate, and text share. The ADR 0001 rate alone rises when the parser sets rows to NULL, so it can hide a regression.
- Every write to the speech table, and every round of links, ends with `python scripts/attribution_text_share.py --output docs/figures/YYYY-MM-DD-<write>.txt`, run on the replica after the write, and the file is committed. The file holds the same lines with the figures by report type and Parliament, the zero-row count and the single-speaker collapse share. To prove a rehearsal copy or the production database holds what the replica holds, run `python -m scripts.compare_table_hashes URL_A URL_B`: it reads both databases read only and prints each table's row count and content hash, so a table that differs is named.
- Before any write to the speech table, run the shared-link check (rule D1). A shared paragraph link carries the row's ordinal and first 8 words (`?s=&q=`). Read only, resolve the link of every stored row in the reports the write touches against the rows the plan leaves, with the site's own `get_speech_anchor` and `get_linked_speech_ordinal` (hansard `api/utils/speech_link.py`). Count the links that land on a paragraph with different opening words, on a different row with the same words, and on no paragraph (the site's "no longer in this report" note). The write goes ahead when the first two counts are zero or close to it. No script in this repo runs the check yet.
- Run every `apply_fresh_parse --commit` and `apply_speaker_links --commit` from a clean worktree of committed master (`git worktree add <dir> <commit>`, with `.env` symlinked and `PYTHONPATH=<dir>`), never from the shared working tree. The commit rebuilds its plan with whatever parser it imports, so another agent's uncommitted edits change the plan, and the first write #12 attempt refused with "The plan differs from the reviewed plan" for that reason.
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

A push to master deploys the refresh job to production: the `refresh` job of the `hansard` DigitalOcean app has `deploy_on_push: true`. The Docker build imports `refresh`, so an import error fails the deploy. Run `poetry run pytest` before every push.

## Architecture

This is a scraper for Singapore Parliament Hansard records (sprs.parl.gov.sg). The pipeline runs in stages, and each stage's output feeds the next. `script.py` is the orchestration file that runs stages 5 to 9 (sitting dates, sittings, attendance, speaker links, persons) in order, with the sitting details fill (`populate/sitting_details.py`) after stage 6, so stage 8's Deputy Speaker rule can read `sitting.sections`. Stages 2 to 4 (`populate/hansard_responses.py`, `populate/reports.py`, `populate/speeches.py`) are not part of `script.py`; the daily refresh below adds their rows.

### Layer rules

Each folder has a strict responsibility boundary. `populate/` is the only layer that may combine gateway calls, service transforms, and DB writes.

| Layer | Responsibility | Forbidden |
|---|---|---|
| `schemas/` | Pydantic models for external data shapes: API bodies and `data/` files | DB access, logic |
| `gateway/` | HTTP calls; return parsed Pydantic models from `schemas/` | Business logic, DB writes, interpreting a missing field |
| `services/` | Pure transforms: input data → output entity | HTTP calls, DB access |
| `database/` | SQLModel table class definitions | Logic of any kind |
| `crud/` | DB read/write helpers, one file per table | Business logic, HTTP |
| `populate/` | Pipeline stages: orchestrate gateway + services + crud | Nothing |
| `utils/` | Shared pure functions | DB access, HTTP |
| `scripts/` | One-off diagnostics: use Session + crud + services, and may call gateways | Raw SQL, direct `select()`/`session.add()` bypassing crud |

Every request to SPRS or parliament.gov.sg goes through `paced_request()` or `paced_request_async()` in `gateway/http.py` and sends `CRAWL_HEADERS`.

### Data flow

1. **Fetch search index** (`gateway/hansard_search.py`): POST to the Hansard search API, paginate through all results, return `list[HansardSearchResult]` (Pydantic model in `schemas/hansard_search_result.py`); a non-list body is an empty page.

2. **Fetch report HTML** (`populate/hansard_responses.py` + `gateway/hansard_topic.py` + `services/hansard_website.py`): for each search result, `populate` calls `gateway` to POST to `getHansardTopic` with a JSON body, which returns a `HansardTopicResponse` (`schemas/hansard_topic_response.py`). The fetch picks the id and the field by system (`services/hansard_website.py::get_topic_id` and `get_topic_html_content`): an older-system hit (`report_version` sprs2, sittings before 10 September 2012) is fetched by `html_file_name` and read from `htmlContent`; a newer-system hit (sprs3) is fetched by `report_id` without its trailing `#` and read from `resultHTML.content`. Both land in `HansardWebsiteResponse.content` through `build_hansard_website_response` (see `docs/adr/0003-newer-system-raw-mapping.md`). Newer-system atbp reports return no text and keep `content` null. Hits listed in `data/excluded_report_ids.json` (a stored report returned again under another id, with the id of the copy kept) are never inserted, and stage 3 builds no report from their raw rows. `populate/hansard_response_contents.py` and `populate/report_contents.py` fill `content` and `markdown_content` in place on rows stored without text.

3. **Parse into Report** (`services/report.py`): converts `HansardWebsiteResponse` → `Report`. Parses the `title` field to split off a `subtitle` (the trailing parenthetical, when it holds a lowercase letter; brackets elsewhere stay in the title). The title is trimmed, loses HTML tags, and a title repeated around commas outside brackets keeps one copy; `original_title` keeps the source form. Also converts HTML content to cleaned markdown via `utils/markdown_parser.py`. An older-system hit of 2003 to 2011 carries no sitting number, so it is read from the `Sitting No` line of the report's header table (`utils/markdown_header.py`).

4. **Parse into Speeches** (`services/speech.py`): walks the markdown line-by-line to find where speeches begin (by matching the report title in bold), then splits the transcript into `Speech` records by detecting bold speaker names (`**Name:**`). `build_speeches` numbers the records and gives each its report's sitting date and report type. Newer-system reports (sprs3) start at the top of the body, because their text never repeats the title; `utils/markdown_parser.py` also cleans their HTML differently (empty emphasis tags and `(proc text)` markers go). Every such branch is guarded by `report_version`, so older-system output is unchanged. `data/unlabelled_speech.json` lists ten ranges whose rows the parser inherited a wrong label for or read as text before the first speaker: `apply_unlabelled_speech_range` gives the rows of a listed range that carry the listed label no label and kind SPEECH, and raises if a locator is gone. The record prints no label there, so the rows keep none (ADR 0013). Each entry also names `credited_speaker_name`, which stage 8 reads.

5. **Fetch sitting dates** (`gateway/hansard_report.py` + `populate/hansard_sitting_dates.py`): for each unique sitting date seen in the search results, POST to `getHansardReport/` with a JSON body (`{"sittingDate": "DD-MM-YYYY"}`, zero padded) to retrieve full sitting metadata. The gateway picks the schema by the shape of the body (a `metadata` key means the nested format) and the stage dispatches on the model type. Stores the result in `HansardSittingDateResponse`; the attendance, PTBA, sections, annexure, vernacular and a2b lists are stored as raw JSON strings on that table (the last four are null for an older-format sitting). `populate/sitting_details.py` fills null columns in place on sittings stored without their details.

6. **Parse into Sittings** (`services/sitting.py` + `populate/sittings.py`): converts `HansardSittingDateResponse` → `Sitting`, adding a `markdown_content` field parsed from `html_full_content`. The nested JSON columns (sections, annexures, vernaculars, a2b) are copied from the raw row with every other column (ADR 0003, item 3); a sitting whose raw row lacks them keeps them NULL, and `populate/sitting_details.py` fetches them into both tables when `script.py` runs. The daily refresh writes them to both tables from the response it fetched. An older-system response has no session number and sometimes no sitting number; both are read from the header table of the sitting's HTML.

7. **Extract attendance** (`services/attendance.py` + `populate/attendances.py`): for each `Sitting`, parses the PRESENT/ABSENT sections from `markdown_content` and writes one `Attendance` row per name found. Sittings with no markdown (every sitting from 10 September 2012) take their rows from the structured `attendance_list` instead, with the same name cleaning and resolution. The constituency in each row's bracket goes through `data/constituency_names.json`, which turns typos and variant spellings into the Elections Department's name and leaves seat types printed in place of a constituency ("Nominated Member", "ex-officio") and other text as printed. A "GRC" suffix is dropped, since the Elections Department leaves it out of the division's name. A list ends at the first line that is not a name entry (a heading, a table row, a line that opens with bold or an asterisk, a date line, or an entry that carries a heading glued to its end). A line in the list with neither a title nor a bracketed constituency is skipped, a name that holds markup is never kept, and a member listed twice in a sitting keeps one row, the present one. Skips sittings already processed.

8. **Wire Speaker foreign keys** (`services/speaker_link.py` + `populate/speaker_links.py`): resolves speaker/attendee names against the `Speaker` table and sets `speaker_id` on `Attendance` and `Speech` rows. `services/speaker_link.py` holds the resolver (`resolve_speech_rows`, `resolve_attendance_rows` and their helpers); `populate/speaker_links.py` keeps the session-taking passes and entry points. A fourth pass, `get_credited_speech_speaker_ids`, reads `data/unlabelled_speech.json` and gives the rows of each listed range that have no label, kind SPEECH and no link the Speaker row named by `credited_speaker_name` in the report's Parliament (`get_unlabelled_range_speaker_ids` in `services/speaker_link.py`; a stray leading `_` on a stored transcript is ignored when matching the locators). It raises `HansardUnlabelledSpeechError` when the name has no Speaker row in that Parliament or a locator matches no row, and it leaves a CHAMBER_EVENT row inside the range alone. A row with `speaker_id` set and no `speaker` is a hand-kept credit, our reading and not a printed fact; report 42017 is not in the file. Depends on the `Speaker` table being populated first (see out-of-band step below). The printed office of each attendance entry follows stage 7 and stage 8: `populate/attendance_offices.py` stores it in `attendance_office` against the attendance row stage 7 wrote, and `populate/office_printed_ranges.py` builds `office_printed_range` from the rows whose attendance row stage 8 has linked.

**Out-of-band:** `scripts/scrape_speakers_by_parliament.py` scrapes `parliament.gov.sg` for the full list of speakers per parliament and stores them in the `Speaker` table. This must be run before step 8; it is not part of `script.py`. The source gives one party and one Assembly flag per person, so `data/speaker_overrides.json` corrects the flag and the party per Parliament row, both at scrape time (`services/speaker.py`) and on stored rows (`scripts/apply_speaker_overrides.py`). For colonial-era Legislative Assembly members, run `scripts/load_colonial_la_speakers.py` first. A member who sat only in the Assembly is a Parliament 0 row, and one who sat in both bodies has one row in Parliament 1; `scripts/apply_speaker_parliaments.py` moves stored rows to the Parliament the two colonial data files give them, and runs before the loaders and `apply_speaker_overrides.py` read the changed files. `data/unscraped_members.json` holds the Parliament 13 row of Lee Li Lian, who declined the seat the Hansard still lists her for, so the scrape omits her; `scripts/load_colonial_la_speakers.py` reads it with the colonial file and inserts it after the Parliament moves, and `scripts/clean_attendance.py` needs it to link her six attendance rows. A few members changed party inside one Parliament while a `Speaker` row holds only the ballot party, so `data/party_affiliations.json` records their dated party history; run `python -m scripts.load_party_affiliations` once the `Speaker` table is final (after `apply_speaker_parliaments.py`, the loaders and `apply_speaker_overrides.py`), because it finds each Membership by name and Parliament and refuses unless the stored party is one of the spans' parties.

### Daily refresh

`refresh.py` runs `populate/refresh_runs.py` once a day. It adds rows: new raw report and sitting rows, their reports, speech rows, sittings and attendance, with stage 8 run on the new rows only and, after it, the askers of the new parliamentary question reports stored in `report_asker` and their participants and states stored in `report_participant` and `report_question_state`, then the printed office of each new attendance entry in `attendance_office`, the office each new question report was put to in `report_put_to`, the ministries of each new printed title in `office_title_ministry` (inserts only; it never writes `ministry` or `ministry_see_also`), and the new sittings' extension of `office_printed_range`, then the bills of the new bill reports, their `billreport` rows, a `billkey` row for each new bill, and the member and stage rows of the new reports in `billreportspeaker` and `billstageline`, and the attached files of the new sittings and the pointers of the new reports in `attached_file` and `attached_file_pointer`, with their ties, then the leave period printings of the new sittings stored in `leave_period_printing` (with a `leave_period` row for each period no stored row holds) and the `seat_holding` rows of the Members in the new sittings' attendance, whose `first_sitting_date`, `last_sitting_date` and `sitting_count` it widens on a stored row, and last the divisions of the new reports stored in `division`. The minutes step adds the divisions of each minutes file it stores in `minutes_division`, a minutes-only `division` row for a division no Hansard division pairs with, their vote rows in `division_vote` and, for each division of that sitting date that has none, its party breakdown in `division_party_count` (inserts only). When a new report joins a stored bill, it updates that bill's `title`, `last_sitting_date` and `is_passed` and nothing else of it. It never re-parses a stored report or rewrites any other stored row, except that extending `office_printed_range` updates a Member's latest range, widening a `seat_holding` row updates those three columns, and the minutes step updates named columns of the `minutes` rows it lists or reads, and it deletes nothing. It commits one month at a time and halts on a new Parliament number, on a field the mapping loses, or when more than 5% of a month's new named speech rows have no registry link; a halt keeps the months before it. A run also ends `FAILED` when every topic answer it fetched has no text (new non-atbp hits plus rechecks); earlier months stay committed. After the last month it runs the minutes step (`populate/minutes.py`), which reads the live index page and fetches the files of listed sittings, and then `VACUUM (ANALYZE)` on `speech`, `report` and `attendance` before it marks the run `SUCCEEDED`, and a VACUUM that fails or is skipped fails the run. After the VACUUM the run stores the report links of the full corpus that the table lacks, inserting only, and sends one alert with the count of stored links that differ from the plan; a failure there fails the run. A failure on the minutes index page is held until the figures, the VACUUM and the report links have run, then raised. A listed minutes file the step cannot fetch (a network failure or a non-200 answer) stays `LISTED` and goes to one alert for the run naming each sitting date and reason; it never halts the run or changes its status. Each run is one `refresh_run` row with its counts and status. A scheduled run cannot commit a `docs/figures/` file, so every run stores the figures in `refresh_run.figures` instead, including a run that adds nothing, so the figures catch up with a supervised write by the next morning; supervised writes still commit theirs. A run sends two alerts about offices: one when a new sitting is dated earlier than the latest sitting with an office row, in which case it writes no range for that month, and one for printed titles with no ministry, which repeats on each run that prints them until they are on the hand-kept list. See `docs/refresh.md`.

### Sitting date API: two formats

The `getHansardReport/` endpoint returns two distinct formats depending on the sitting date:

- **Old format** (sittings before 10 September 2012): flat body, all fields at top level, parsed as `HansardReportOldResponse`.
- **New format** (sittings from 10 September 2012): nested body with a `metadata` object plus child lists (`attendanceList`, `ptbaList`, `takesSectionVOList`, `annexureList`, `vernacularList`, `a2bList`), parsed as `HansardReportNewResponse`. It carries no full-sitting HTML.

Both schemas live in `schemas/hansard_report_response.py`; every field is `Optional` because the endpoint also answers with `{errorCode, description}`. `gateway/hansard_report.py` strips NUL bytes and picks the schema by the presence of the `metadata` key, and `services/hansard_sitting_date_response.py` exposes `build_old_hansard_sitting_date_response` and `build_new_hansard_sitting_date_response`, which `populate/hansard_sitting_dates.py` dispatches on the model type. `settings.sitting_date_format_change` (`datetime(2015, 8, 18)`) is read only by `scripts/validate_api_field_mapping.py`.

### Database models

Two-tier design: every data source has a **raw response table** and an **entity table**.

**Raw response tables** store API responses exactly as received. No type casting, no field dropping. The only transformation allowed is what storage requires (e.g. serialising list fields to JSON strings so they fit in a column).

**Entity tables** are pure extensions of their raw counterparts: every field from the raw response is preserved with the same value and structure. They exist to provide a stable, first-class DB schema ready for relationships and future enrichment, not to transform or interpret the source data. The one exception: where the raw response leaves a sitting or session number NULL, `Report` and `Sitting` fill it from the header table of the stored text, so those columns can differ from the raw row (see `docs/data-loss-register.md`).

[docs/data-dictionary.md](docs/data-dictionary.md) describes every table and its columns.

### Key parsing logic

`utils/markdown_parser.py` is the HTML → clean markdown pipeline. It turns `&nbsp;` into a space (an emphasis tag holding only `&nbsp;` becomes one space), strips column/page markers, then merges consecutive bold-only lines that were split across page breaks. This merged form is required for speaker detection to work correctly. Also has `get_cleaned_sitting_markdown` for sitting HTML.

`services/speech.py::get_start_of_speech_line`: locates the line in the markdown that marks where speeches begin (the report's own title appears in bold as the first "heading" before actual speeches). Returns `None` if the title can't be matched.

`services/attendance.py`: extracts names from sitting markdown and from the structured attendance list. `build_speaker_lookups(speakers: list[Speaker]) -> SpeakerLookups` builds all six in-memory lookup dicts from a pre-loaded Speaker list (no DB access). Callers must load Speakers via `crud/speaker.py` and pass the resulting `SpeakerLookups` to `resolve_canonical_name` and `build_sitting_attendances`, the dispatcher that calls `build_sitting_attendances_from_markdown` and `build_sitting_attendances_from_list`. `resolve_canonical_name`, `SpeakerLookups` and the reference tables behind them live in `utils/speaker_resolution.py`. The resolution cascade: manual overrides → inverted-name lookup → direct lookup → bin-free lookup → word-set lookup → prefix lookup → spelling normalisation → Haji-prefix stripping → surname-only fallback. The pure name helpers (`strip_title`, which removes 25+ title prefixes such as Dr, BG, RAdm and Tuan Haji before matching, plus `normalize_name`, `period_normalize`, `strip_bin`, `invert_to_natural`, `strip_middle_haji` and `spelling_normalize`) live in `utils/names.py`, because `services/attendance.py` and `services/person.py` both need them. `infer_parliament(parlement_no, volume_no)` and `VOLUME_TO_PARLIAMENT` live in `utils/parliament_numbers.py`. CRUD projections come back as dataclasses declared beside their method (`SpeechRow`, `SpeechSpeakerRow`, `AttendanceSpeakerRow`), never tuples, and CRUD lookups are named for the columns they filter on (`get_speaker_rows_by_speaker_id_null`, `get_by_markdown_content_not_null`).

### Environment

Requires a `DATABASE_URL` env var (or `.env` file). Falls back to `postgresql://user:password@localhost:5432/postgres`.

All configurable URLs and search date bounds live in `settings.py` (`AppSettings`).

### `scripts/` directory

One-off diagnostic and analysis scripts, not part of the main pipeline.

Every write script calls `validate_can_write` (`utils/write_target.py`) before `--commit`. A new script that must not write opens the database with `build_read_only_engine` (`database/init.py`), which refuses writes at the connection. Older diagnostics open it with `engine` and write nothing only because their code holds no write call. Every script that calls `validate_can_write` ends a `--commit` run with `vacuum_analyze_written_tables` (`populate/written_tables.py`) on the tables it wrote, so search does not wait for the 04:00 refresh to get a vacuumed table. It raises `HansardWriteCheckError` when a table's `vacuum_count` did not rise, which is what Postgres leaves behind when the role lacks `MAINTAIN` or ownership. A new write script adds the call in the same change.

A write that adds, rewrites or deletes speech rows of an older-system report (Parliaments 0 to 11) also sets their column numbers again, so `speech.column_start` and its note never go stale: `apply_coverage_refill.py`, `apply_language_note_close_marks.py` and `apply_footnote_markers.py` run the column pass inside their own write, and any other such write, the speech fidelity loop's ship tools included, ends with `python -m scripts.apply_column_numbers --commit --report-id ...` for the reports it touched.

A write that adds, rewrites, deletes or relinks speech rows of a parliamentary question report (oral-answer, written-answer, written-answer-na) ends with `python -m scripts.apply_report_askers --commit --report-id ...` and then `python -m scripts.apply_report_participants --commit --report-id ...` for the reports it touched.

A write that adds, rewrites, deletes or relinks attendance rows (`apply_attendance_names.py`, `apply_constituency_names.py`, `apply_speaker_links.py`, `clean_attendance.py`, `complete_truncated_attendance.py`) ends with `python -m scripts.apply_attendance_offices --commit`, `python -m scripts.apply_seat_holdings --commit` and `python -m scripts.apply_leave_periods --commit`. A write that rewrites speech rows of a parliamentary question report also ends with `python -m scripts.apply_report_put_to --commit --report-id ...` for the reports it touched.

A write that adds or changes speaker rows (`scrape_speakers_by_parliament.py`, `load_parliament_speakers.py`, `load_colonial_la_speakers.py`, `load_heads_of_state.py`, `apply_speaker_parliaments.py`, `apply_speaker_overrides.py`) or rewrites sitting markdown (`apply_source_characters.py`), or a change to `data/leave_date_misprints.json`, ends with `python -m scripts.apply_leave_periods --commit`, because the speaker links of leave printings read the roster and the older sections read the markdown.

A write that adds, rewrites or deletes speech rows of any report ends with `python -m scripts.apply_report_links --commit`.

A run of `python -m scripts.apply_bill_speakers --commit` without `--report-id` follows each `apply_act_links.py --commit`, because a regroup gives new bills no key row and moves reports between bills. A run with `--report-id` (the integer `report.id`) follows any write that adds, rewrites, deletes or relinks speech rows of a report in `billreport`, and may list every report the write touched, joined to a bill or not.

A write that adds, rewrites or deletes speech rows of a report whose raw text holds a download link ends with `python -m scripts.apply_attached_files --commit --report-id ...` for the reports it touched. `apply_fresh_parse.py` does this inside its own write.

A write that adds, rewrites, deletes or relinks speech rows of a report ends with `python -m scripts.apply_divisions --plan-file ... --commit --report-id ...` for the reports it touched, as the askers' write does, because a moved speech ordinal moves a division's number. Then it runs `python -m scripts.apply_minutes_divisions --plan-file ... --commit --minutes-id ...` for the minutes of the sittings it touched, because a Hansard division the write adds can leave a stored pairing the rule would no longer make, and last `python -m scripts.apply_division_party_counts --plan-file ... --commit --division-id ...`, because the party breakdown counts the vote rows those two writes replace.

[docs/scripts.md](docs/scripts.md) lists the scripts and what each one reads, writes and refuses.

The speech fidelity loop has its own tools for rewriting stored speech rows. They live outside the repo's tracked tree, in the gitignored `plans/speech-fidelity-loop/bin/`. Run them only for a planned write, and follow a ship that touches Parliaments 0 to 11 with `apply_column_numbers.py --commit --report-id` for its reports.

Scripts log through `logs.logger`; the one script whose stdout is data (`find_presiding_officers.py`, paste-ready `SPEAKER_TERMS` and `DEPUTY_SPEAKER_TERMS` tuple literals) prints that output under `# noqa: T201`. `find_unmatched_attendees.py` writes its JSON template to the path given by `--json`.

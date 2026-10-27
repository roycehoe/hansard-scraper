# Daily refresh

`refresh.py` adds the sittings, reports and speech rows SPRS has published since the last stored sitting. It runs once a day as a scheduled job and records each run in the `refresh_run` table. The code is `populate/refresh_runs.py`, with its rules and alert text in `services/refresh.py`.

---

## What a run does

A run only adds rows. It never re-parses a stored report and never rewrites a stored row, so a fix to the parser reaches stored rows only through a supervised write. New reports go through the parser on `master` as it stood when the image was built.

In order, a run:

1. Marks any `RUNNING` row older than 12 hours as `FAILED` ("Run ended without finishing"), then inserts its own `RUNNING` row and commits it.
2. Fails if another `RUNNING` row started less than 12 hours ago.
3. Reads the stored sitting dates, report ids and the highest stored Parliament number, and the stored text of every report whose sitting falls in the last 14 days. It then commits, so no transaction stays open during the crawl.
4. Fetches the topic text of each stored report in the 14-day window again, and halts if any field of a re-fetched body is lost on its way to a row. It compares each re-fetched text with the stored one. A changed report gets an alert and keeps its stored text.
5. Splits the probe range into calendar months. The range runs from the day after the last stored sitting to today, or from 14 days ago if that is earlier. Dates are Singapore dates. A rerun works out its start the same way from what is stored by then, so it does not request the months an earlier run committed again, apart from the dates after the last stored sitting.

Then, for each month in order, the run:

6. Searches SPRS over the month. It drops hits already stored and hits listed in `data/excluded_report_ids.json`.
7. Halts if a new hit carries a Parliament number above the highest stored one.
8. Fetches the topic text of each new hit, then asks for the sitting of every date in the month that has no stored sitting.
9. Halts if any field of a fetched body is lost on its way to a row, or if a fetched sitting carries a new Parliament number.
10. Writes the raw report rows, the reports, their speech rows, the raw sitting rows, the sittings and their attendance rows. A hit whose topic has no text is not stored (see "Halts and how to clear each").
11. Runs stage 8, the speaker links, on the new speech and attendance rows only.
12. Halts if more than 5% of the month's new named speech rows have no registry link. A named row is one the attribution figures count as linked or named unlinked.
13. Commits the month. A halt or a failure rolls back only the month in progress.

After the last month, the run:

14. Computes the attribution figures, on every run, so a supervised write's links reach them by the next run.
15. Runs `VACUUM (ANALYZE)` on `speech`, `report` and `attendance`, including on a run that added no rows. VACUUM marks the pages whose rows every transaction can see, and an index-only scan reads the table for each row on a page that is not marked. It then checks that each table's `vacuum_count` in `pg_stat_user_tables` rose (see "Halts and how to clear each").
16. Records the counts and marks the row `SUCCEEDED`.
17. Sends the alerts, then the healthchecks.io ping: the plain URL on success, `/fail` on a halt or a failure.

`refresh.py` exits 0 on success, 2 on a halt and 1 on a failure, after the failure's error propagates.

## Schedule

The run is an App Platform scheduled job, daily at 04:00 Singapore time (`0 4 * * *` in `Asia/Singapore`, which is `0 20 * * *` UTC). Batch E adds the component to `hansard/.do/app.yaml`. The image is built from `Dockerfile` at the repo root, and the command is `sh refresh.sh`, which runs `python refresh.py`.

A push to master deploys the refresh job to production: the `refresh` job of the `hansard` DigitalOcean app has `deploy_on_push: true`. Run `poetry run pytest` before every push.

Enable the schedule only after the Parliament 15 backfill (see "The Parliament 15 backfill"). The backfill ran on 19 October 2026, and a plain run after it succeeded, so the stored data no longer blocks the schedule.

## Crawl rate

Every request to SPRS goes through the crawl pacer in `gateway/http.py`. It sends one request at a time, at least 2 seconds apart, retries included, with the user agent `hansard-scraper (+royceinbox@hotmail.com)`.

The gap is the `CRAWL_GAP_SECONDS` setting, 2 by default, which is the crawl rate the project commits to. The scheduled job keeps the default. The Parliament 15 backfill of 19 October 2026 ran at 2 seconds until September 2025 was stored, then at 1 second on Royce's instruction (`CRAWL_GAP_SECONDS=1`).

A daily run sends:

- the search pages for its date range
- one topic request per new hit
- one topic request per stored report whose sitting falls in the last 14 days
- one sitting request per date in the range with no stored sitting

## Env vars and accounts

| Variable | Holds |
|---|---|
| `DATABASE_URL` | The connection string of the write role `hansard_refresh` (see "Write role SQL") |
| `TELEGRAM_BOT_TOKEN` | The bot token for alerts |
| `TELEGRAM_CHAT_ID` | The chat the bot posts to |
| `HEALTHCHECKS_PING_URL` | The ping URL of the healthchecks.io check |

Each alert target does nothing while its variables are unset. The Telegram alert needs both the token and the chat id.

Setup:

1. Create a bot with @BotFather and keep its token. Send the bot a message, then read the chat id from the bot's `getUpdates` response.
2. Create a healthchecks.io check with period 1 day and grace 2 hours, so it reports a missed run 26 hours after the last ping. Add its Telegram integration.

The run sends the plain ping on success and the `/fail` ping on a halt, a failure, or a run that cannot start. `refresh.sh` then pings with refresh.py's exit code, so a crash before the run's own alert code, such as an import error or a bad `DATABASE_URL`, also sends a failure ping. The check goes down at once on a `/fail` ping or a nonzero exit code, and after 26 hours with no ping. A halt or a failure also shows up as a Telegram alert.

## Halts and how to clear each

A halt keeps the months committed before it and writes nothing of the month in progress. The run's row is `HALTED`, `refresh_run.halt_reason` holds the reason, and the halt alert repeats it.

- **New Parliament number.** A new hit or a fetched sitting carries a Parliament number above the highest stored one. Load its members with `scripts/load_parliament_speakers.py --parliament N` (a dry run, then `--commit`), then run `python refresh.py --allow-parliament N` once, supervised, as in the backfill below. The flag accepts that one number for that one run.
- **Field mapping.** A field present in a fetched body is missing from the row built from it, which means SPRS changed a field. Run `scripts/validate_api_field_mapping.py` by hand to see the field, fix the schema or the mapping, then run again.
- **Unlinked share.** More than 5% of the month's new named speech rows have no registry link. The halt message and `halt_reason` list the unmatched labels with their row counts. Add those members to the registry, then run again.

On the first supervised run, read the log's "No sitting response" lines. Each one is a probed date with no sitting, and SPRS should answer it in a shape the run reads as nothing published. If a line shows an answer that looks like a real sitting, stop and check the gateway.

A failure is any other error. The row is `FAILED` and `failure_reason` holds the error type and message. A failure keeps the months committed before it, and their rows stay stored; once a month has committed rows, `failure_reason` starts with "After the data commit". The next run retries. A run also ends `FAILED` when every topic answer it fetched has no text (the new non-atbp hits plus the rechecks), and the months it committed earlier stay committed.

A VACUUM that fails, or that Postgres skips, is a failure too. Postgres skips a table the role cannot `MAINTAIN` with only a warning, which the run never sees, so the run compares each table's `vacuum_count` before and after, and raises `HansardRefreshRunError` naming the table when it did not rise. A skip means the `MAINTAIN` grant in "Write role SQL" is missing on that table. The new rows are committed by then and stay, and the next run vacuums again.

Two cases are known and accepted:

- A run swept as stale by another run keeps committing its months. Each month only adds rows, and the swept run cannot overwrite its `FAILED` status when it ends.
- A killed supervised run leaves its row `RUNNING`, which blocks the next run for 12 hours. Mark it failed by hand:

  ```sql
  UPDATE refresh_run SET status = 'FAILED', failure_reason = 'Run ended without finishing', finished_at = now() WHERE id = <id> AND status = 'RUNNING';
  ```

  The write role's `UPDATE` grant on `refresh_run` covers it.

A hit whose topic has no text yet is not stored, because a raw row cannot be filled in later. Each run fetches it again while its sitting is within the 14-day window. An atbp report is the exception. SPRS serves no text for one, so the run stores it without text, as stage 2 does.

## Alerts

Every alert goes to the one Telegram chat, cut to 4,000 characters.

| Alert | Text | Sent |
|---|---|---|
| Summary | `2 sittings, 14 reports, 1,203 rows, 98.9% linked` | After a successful run, or a halted or failed run that committed rows, that stored at least one raw report row or raw sitting row. The linked share is over the new named rows, and the message leaves it off when the run added none. |
| Changed report | `Report {report id} of {sitting date} changed on SPRS since it was stored. The stored text was kept.` | After a successful run, or a halted or failed run that committed rows, once per stored report in the 14-day window whose text changed. |
| Unlinked labels | `Speaker labels with no registry match: {labels}. Add the members to the registry, then link them with scripts/apply_speaker_links.py.` | After a successful run, or a halted or failed run that committed rows, whose new rows hold labels with no registry link, at or under the 5% limit. Up to 20 labels, most rows first, then "and N more". |
| Held report | `Report {report id} of {sitting date} still has no text after 14 days and will not be fetched again.` | After a successful run, or a halted or failed run that committed rows, for a held hit whose sitting date is 13 or 14 days before the run's date. The two-day span keeps one missed run from losing the alert, so a hit can alert twice. |
| Many held reports | `{n} new reports came back with no text, above the limit of 5. SPRS may have changed its format.` | After a successful run, or a halted or failed run that committed rows, that holds more than 5 new hits without text. It repeats each day while those hits stay held in the 14-day window. |
| Halt | `Hansard refresh halted. {reason}` | On every halt. |
| Failure | `Hansard refresh failed. {error}` | On every failure, including a run that cannot start. For an error the code raises on purpose, `{error}` is its type and message. For any other error it is the type alone, so a database host or user name never reaches the chat. |

## `refresh_run` columns

One row per run. Every count column is `integer NOT NULL` and counts only what that run did. A halted or failed run's counts hold what its committed months stored.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Primary key |
| `website_responses_added` | integer | Raw report rows stored |
| `sitting_date_responses_added` | integer | Raw sitting rows stored |
| `sittings_added` | integer | Sitting rows stored |
| `reports_added` | integer | Report rows stored |
| `speeches_added` | integer | Speech rows stored |
| `speeches_linked` | integer | New speech rows linked to a speaker |
| `speeches_named_unlinked` | integer | New speech rows with a speaker label and no link |
| `attendances_added` | integer | Attendance rows stored |
| `attendances_linked` | integer | New attendance rows linked to a speaker |
| `reports_held_without_text` | integer | New hits not stored because their topic had no text |
| `reports_without_speech_rows` | integer | New reports the parser built no speech row for |
| `reports_rechecked` | integer | Stored reports in the 14-day window fetched again |
| `reports_changed` | integer | Re-fetched reports whose text differs from the stored text |
| `latest_sitting_date_with_text` | date, NULL | The latest sitting date of any stored report with text, after the run |
| `figures` | jsonb, NULL | The attribution figures, on every run that reaches the end (see "For batch E") |
| `halt_reason` | text, NULL | Why the run halted |
| `failure_reason` | text, NULL | The error type and message, up to 1,000 characters |
| `started_at` | timestamptz | When the run started |
| `finished_at` | timestamptz, NULL | When the run ended. NULL while it runs |
| `status` | text | One of the four statuses below |

| Status | Meaning |
|---|---|
| `RUNNING` | The run has started and not ended. The next run marks a row still `RUNNING` after 12 hours as `FAILED` |
| `SUCCEEDED` | The data is committed, the three tables are vacuumed and the counts are recorded |
| `HALTED` | A halt check stopped the run. Months committed before it stay stored |
| `FAILED` | An error stopped the run |

## Figures and the register

`CLAUDE.md` asks every write to the speech table to end with a `docs/figures/` file. A scheduled job cannot commit one, so every run stores the same figures as `scripts/attribution_text_share.py` in `refresh_run.figures`. Supervised writes still commit their file.

The register (`docs/data-loss-register.md`) has rows for what the refresh keeps or skips. Their counts grow run by run in `reports_held_without_text`, `reports_without_speech_rows`, `speeches_named_unlinked` and `reports_changed`, and a supervised update of the register reads them from there.

## Running it locally

Run it only against the scratch database:

```bash
DATABASE_URL=postgresql://user:password@localhost:5435/hansard_launch python refresh.py
```

A local run sends live requests to SPRS at the crawl rate, so start one only when that is the point. Unset `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and `HEALTHCHECKS_PING_URL` first, so it sends no alert and no ping. The tests (`poetry run pytest`) send no request.

## The Parliament 15 backfill

The backfill runs as a separate, later step, not as part of the scheduled refresh. All of it runs supervised with the owner role, not `hansard_refresh`. The member load inserts into `speaker`, and stage 9 inserts into `person` and sets `speaker.person_id`, and the write role has no grant for any of that.

1. `python scripts/load_parliament_speakers.py --parliament 15`, a dry run. Review the members it lists, then run it again with `--commit`.
2. `python -m scripts.load_heads_of_state --commit`, supervised. It adds the President's Parliament 15 row, and stage 9 then gives that row its `person_id`.
3. Stage 9 for the new speakers: `populate_persons` in `populate/persons.py`.
4. `python refresh.py --allow-parliament 15`, supervised.
5. `python scripts/attribution_text_share.py --output docs/figures/YYYY-MM-DD-backfill-15.txt` on the replica, and a register row, as `CLAUDE.md` requires.

Two things affect the backfill run. The Prime Minister and President terms run to the present. A bare "The Prime Minister" row in Parliament 15 links, and a "The President" row in the Parliament 15 President's Address links once `scripts/load_heads_of_state.py` has run. And the sitting probe covers every date from 9 April 2025, about 560 requests at the crawl rate, plus the topic requests.

It ran on the remote database on 19 October 2026. Before it, `scripts/load_heads_of_state.py` inserted one `speaker` row, Tharman Shanmugaratnam for Parliament 15, and stage 9 set its `person_id`. `refresh.py --allow-parliament 15` then took four runs, `refresh_run` ids 1 to 4. Runs 1 and 2 stored nothing. Run 2 lost its database connection, and `191bd3b` added TCP keepalives and pooled-connection pings before run 3. Run 3 committed September 2025 and was then stopped. Its row is `FAILED` with zero counts, because the orchestrator closed it by hand, so its rows are counted in no `refresh_run` row. Run 4 stored October 2025 to October 2026 and `SUCCEEDED`. Across the four runs `hansardwebsiteresponse` went from 47,439 to 52,250 rows, `hansardsittingdateresponse` from 1,719 to 1,758 and `speech` from 1,051,922 to 1,115,831. The 63,909 speech rows dated from 1 September 2025 are all new, and 62,050 of them are linked. Run 5, a plain `python refresh.py`, `SUCCEEDED` with 0 rows added and 300 reports re-checked.

Step 5 ran on the remote, not on the replica. `hansard_replica` holds no Parliament 15 rows and the backfill leaves it alone, and `scripts/attribution_text_share.py` only reads. The file is `docs/figures/2026-10-19-backfill-15.txt`, and the entry in `docs/vision.md` ("Measuring progress") gives its figures.

## Write role SQL

Royce runs this. The build never does.

```sql
CREATE ROLE hansard_refresh LOGIN PASSWORD '<set by Royce>';
GRANT CONNECT ON DATABASE <database> TO hansard_refresh;
GRANT USAGE ON SCHEMA public TO hansard_refresh;
GRANT SELECT ON hansardwebsiteresponse, hansardsittingdateresponse, report, speech, sitting, attendance, speaker, refresh_run TO hansard_refresh;
GRANT INSERT ON hansardwebsiteresponse, hansardsittingdateresponse, report, speech, sitting, attendance, refresh_run TO hansard_refresh;
GRANT UPDATE (speaker_id) ON speech, attendance TO hansard_refresh;
GRANT UPDATE ON refresh_run TO hansard_refresh;
GRANT MAINTAIN ON speech, report, attendance TO hansard_refresh;
GRANT USAGE ON SEQUENCE hansardwebsiteresponse_id_seq, hansardsittingdateresponse_id_seq, report_id_seq, speech_id_seq, sitting_id_seq, sittingattendance_id_seq, refresh_run_id_seq TO hansard_refresh;
GRANT SELECT (id, website_responses_added, sitting_date_responses_added, sittings_added, reports_added, speeches_added, speeches_linked, speeches_named_unlinked, attendances_added, attendances_linked, reports_held_without_text, reports_without_speech_rows, reports_rechecked, reports_changed, latest_sitting_date_with_text, figures, started_at, finished_at, status) ON refresh_run TO <the API's read-only role>;
```

The table and sequence names are those on the scratch copy. `attendance` owns `sittingattendance_id_seq`, a name kept from an older table name. Confirm each name on the remote with `\d <table>` first.

The role gets no DELETE or TRUNCATE on any table. It gets no `UPDATE` on `hansardwebsiteresponse`, `hansardsittingdateresponse` or `speaker`, and no `CREATE`, so it cannot run migrations. Migrations stay supervised, with the owner role. `SELECT ... FOR UPDATE` on `refresh_run` needs the `UPDATE` grant the role has. `MAINTAIN` lets the role run `VACUUM` and `ANALYZE` on the three tables, and also `REINDEX` and `CLUSTER`, which the refresh never runs. Royce granted it on the remote on 21 October 2026, as `doadmin`, the tables' owner. The figures pass reads every report and speech row, which the `SELECT` grants cover.

The API's role gets a column grant that leaves out `halt_reason` and `failure_reason`, because a failure reason can carry database host and user names. Batch E's reader never selects those two columns.

## For batch E

The contract the API reads, with the read grant of "Write role SQL".

- **Columns.** As in "`refresh_run` columns": `id` integer primary key; the count columns, each `integer NOT NULL`: `website_responses_added`, `sitting_date_responses_added`, `sittings_added`, `reports_added`, `speeches_added`, `speeches_linked`, `speeches_named_unlinked`, `attendances_added`, `attendances_linked`, `reports_held_without_text`, `reports_without_speech_rows`, `reports_rechecked`, `reports_changed`; `latest_sitting_date_with_text` `date` NULL; `figures` `jsonb` NULL; `halt_reason` `text` NULL; `failure_reason` `text` NULL; `started_at` `timestamptz NOT NULL`; `finished_at` `timestamptz` NULL; `status` `text NOT NULL`, with the check `status IN ('RUNNING', 'SUCCEEDED', 'HALTED', 'FAILED')`; index `ix_refresh_run_started_at`.
- **Revision.** `b8e2f4a61c03`, down revision `c93f77e499cc`.
- **`figures` shape.** `{"measured_at": "<ISO 8601 UTC>", "groups": [{"group", "report_count", "reports_with_rows_count", "zero_row_report_count", "linked_row_count", "named_unlinked_row_count", "adr_excluded_row_count", "no_speaker_row_count", "row_count", "linked_character_count", "body_character_count", "body_in_zero_row_reports", "report_types": [{"report_type", "report_count", "zero_row_report_count", "collapse_report_count", "collapse_character_count", "body_total", "category_to_row_count", "category_to_character_count"}]}]}`. The groups are "Parliaments 0 to 11", then every Parliament above 11 present in the data. The group fields are the stable contract. Per group, named linked is `linked_row_count / (linked_row_count + named_unlinked_row_count)`, all linked is `linked_row_count / row_count`, and text share is `linked_character_count / body_character_count`.
- **Footer rules.** "Includes sittings up to {date}" is `latest_sitting_date_with_text` of the latest `SUCCEEDED` row. "Last checked {date}" is that row's `finished_at` as a Singapore date. Halted and failed runs move neither. Figures come from the latest `SUCCEEDED` row whose `figures` is not null. While no `SUCCEEDED` row exists, the API shows no footer line and keeps its current figures.
- **Read grant.** The column grant on `refresh_run` in "Write role SQL", which leaves out `halt_reason` and `failure_reason`. Royce runs it.
- **Image.** Repo `roycehoe/hansard-scraper`, `Dockerfile` at the root, branch `master`, command `sh refresh.sh`.
- **Schedule.** Daily at 04:00 Singapore time (`0 4 * * *` in `Asia/Singapore`, or `0 20 * * *` UTC).
- **Env vars.** `DATABASE_URL` (the write role), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `HEALTHCHECKS_PING_URL`. Each alert target does nothing while unset.

An example `figures` value, from a test run on saved fixtures, cut to one group and one of that group's four report types:

```json
{
  "measured_at": "2026-10-18T16:26:45.710325+00:00",
  "groups": [
    {
      "group": "Parliament 14",
      "report_count": 30,
      "reports_with_rows_count": 30,
      "zero_row_report_count": 0,
      "linked_row_count": 55,
      "named_unlinked_row_count": 11,
      "adr_excluded_row_count": 0,
      "no_speaker_row_count": 9,
      "row_count": 75,
      "linked_character_count": 14525,
      "body_character_count": 16489,
      "body_in_zero_row_reports": 0,
      "report_types": [
        {
          "report_type": "written-answer",
          "report_count": 14,
          "zero_row_report_count": 0,
          "collapse_report_count": 0,
          "collapse_character_count": 0,
          "body_total": 9375,
          "category_to_row_count": {"linked": 33, "named_unlinked": 2},
          "category_to_character_count": {"linked": 8976, "named_unlinked": 399}
        }
      ]
    }
  ]
}
```

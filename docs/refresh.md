# Daily refresh

`refresh.py` adds the sittings, reports and speech rows SPRS has published since the last stored sitting. It runs once a day as a scheduled job and records each run in the `refresh_run` table. The code is `populate/refresh_runs.py`, with its rules and alert text in `services/refresh.py`.

---

## What a run does

A run only adds rows. It never re-parses a stored report and never rewrites a stored row, so a fix to the parser reaches stored rows only through a supervised write. New reports go through the parser on `master` as it stood when the image was built.

In order, a run:

1. Marks any `RUNNING` row older than 12 hours as `FAILED` ("Run ended without finishing"), then inserts its own `RUNNING` row and commits it.
2. Fails if another `RUNNING` row started less than 12 hours ago.
3. Reads the stored sitting dates, report ids and the highest stored Parliament number, and the stored text of every report whose sitting falls in the last 14 days. It then commits, so no transaction stays open during the crawl.
4. Searches SPRS from the day after the last stored sitting to today, or from 14 days ago if that is earlier. Dates are Singapore dates. It drops hits already stored and hits listed in `data/excluded_report_ids.json`.
5. Halts if a new hit carries a Parliament number above the highest stored one.
6. Fetches the topic text of each new hit, then asks for the sitting of every date in the search range that has no stored sitting, then fetches the topic text of each stored report in the 14-day window again.
7. Halts if any field of a fetched body is lost on its way to a row, or if a fetched sitting carries a new Parliament number.
8. Compares each re-fetched text with the stored one. A changed report gets an alert and keeps its stored text.
9. Writes the raw report rows, the reports, their speech rows, the raw sitting rows, the sittings and their attendance rows. A hit whose topic has no text is not stored (see "Halts and how to clear each").
10. Runs stage 8, the speaker links, on the new speech and attendance rows only.
11. Halts if more than 5% of the new named speech rows have no registry link. A named row is one the attribution figures count as linked or named unlinked.
12. Commits every data row in one transaction. A halt or a failure before this point rolls all of them back.
13. Computes the attribution figures when the run added speech rows, records the counts and marks the row `SUCCEEDED`.
14. Sends the alerts, then pings healthchecks.io.

`refresh.py` exits 0 on success, 2 on a halt and 1 on a failure, after the failure's error propagates.

## Schedule

The run is an App Platform scheduled job, daily at 04:00 Singapore time (`0 4 * * *` in `Asia/Singapore`, which is `0 20 * * *` UTC). Batch E adds the component to `hansard/.do/app.yaml`. The image is built from `Dockerfile` at the repo root, and the command is `python refresh.py`.

Enable the schedule only after the Parliament 15 backfill (see "The Parliament 15 backfill"). Until then the stored sittings end on 8 April 2025, so every run searches from 9 April 2025 and halts on Parliament 15.

## Crawl rate

Every request to SPRS goes through the crawl pacer in `gateway/http.py`. It sends one request at a time, at least 2 seconds apart, retries included, with the user agent `hansard-scraper (+hansard@fancybinary.sg)`.

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

The run pings on every outcome, success, halt or failure, and also when it cannot start. A healthchecks.io alert therefore means no run finished at all. A halt or a failure shows up as a Telegram alert.

## Halts and how to clear each

A halt writes no data. The run's row is `HALTED`, `refresh_run.halt_reason` holds the reason, and the halt alert repeats it.

- **New Parliament number.** A new hit or a fetched sitting carries a Parliament number above the highest stored one. Load its members with `scripts/load_parliament_speakers.py --parliament N` (a dry run, then `--commit`), then run `python refresh.py --allow-parliament N` once, supervised, as in the backfill below. The flag accepts that one number for that one run.
- **Field mapping.** A field present in a fetched body is missing from the row built from it, which means SPRS changed a field. Run `scripts/validate_api_field_mapping.py` by hand to see the field, fix the schema or the mapping, then run again.
- **Unlinked share.** More than 5% of the new named speech rows have no registry link. The halt message and `halt_reason` list the unmatched labels with their row counts. Add those members to the registry, then run again.

On the first supervised run, read the log's "No sitting response" lines. Each one is a probed date with no sitting, and SPRS should answer it in a shape the run reads as nothing published. If a line shows an answer that looks like a real sitting, stop and check the gateway.

A failure is any other error. The row is `FAILED`, `failure_reason` holds the error type and message, and the run writes no data unless the failure came after the data commit, in which case `failure_reason` starts with "After the data commit". The next run retries.

A hit whose topic has no text yet is not stored, because a raw row cannot be filled in later. Each run fetches it again while its sitting is within the 14-day window. An atbp report is the exception. SPRS serves no text for one, so the run stores it without text, as stage 2 does.

## Alerts

Every alert goes to the one Telegram chat, cut to 4,000 characters.

| Alert | Text | Sent |
|---|---|---|
| Summary | `2 sittings, 14 reports, 1,203 rows, 98.9% linked` | After a successful run that stored at least one raw report row or raw sitting row. The linked share is over the new named rows, and the message leaves it off when the run added none. |
| Changed report | `Report {report id} of {sitting date} changed on SPRS since it was stored. The stored text was kept.` | After a successful run, once per stored report in the 14-day window whose text changed. |
| Unlinked labels | `Speaker labels with no registry match: {labels}. Add the members to the registry, then link them with scripts/apply_speaker_links.py.` | After a successful run whose new rows hold labels with no registry link, at or under the 5% limit. Up to 20 labels, most rows first, then "and N more". |
| Held report | `Report {report id} of {sitting date} still has no text after 14 days and will not be fetched again.` | After a successful run, for a held hit whose sitting date is 13 or 14 days before the run's date. The two-day span keeps one missed run from losing the alert, so a hit can alert twice. |
| Halt | `Hansard refresh halted. {reason}` | On every halt. |
| Failure | `Hansard refresh failed. {error}` | On every failure, including a run that cannot start. For an error the code raises on purpose, `{error}` is its type and message. For any other error it is the type alone, so a database host or user name never reaches the chat. |

## `refresh_run` columns

One row per run. Every count column is `integer NOT NULL` and counts only what that run did. A halted run, and a run that failed before the data commit, keep every count at 0.

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
| `figures` | jsonb, NULL | The attribution figures, on a run that added speech rows (see "For batch E") |
| `halt_reason` | text, NULL | Why the run halted |
| `failure_reason` | text, NULL | The error type and message, up to 1,000 characters |
| `started_at` | timestamptz | When the run started |
| `finished_at` | timestamptz, NULL | When the run ended. NULL while it runs |
| `status` | text | One of the four statuses below |

| Status | Meaning |
|---|---|
| `RUNNING` | The run has started and not ended. The next run marks a row still `RUNNING` after 12 hours as `FAILED` |
| `SUCCEEDED` | The data is committed and the counts are recorded |
| `HALTED` | A halt check stopped the run and it wrote no data |
| `FAILED` | An error stopped the run |

## Figures and the register

`CLAUDE.md` asks every write to the speech table to end with a `docs/figures/` file. A scheduled job cannot commit one, so a run that adds speech rows stores the same figures as `scripts/attribution_text_share.py` in `refresh_run.figures`. Supervised writes still commit their file.

The register (`docs/data-loss-register.md`) has rows for what the refresh keeps or skips. Their counts grow run by run in `reports_held_without_text`, `reports_without_speech_rows`, `speeches_named_unlinked` and `reports_changed`, and a supervised update of the register reads them from there.

## Running it locally

Run it only against the scratch database:

```bash
DATABASE_URL=postgresql://user:password@localhost:5435/hansard_launch python refresh.py
```

A local run sends live requests to SPRS at the crawl rate, so start one only when that is the point. Unset `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and `HEALTHCHECKS_PING_URL` first, so it sends no alert and no ping. The tests (`poetry run pytest`) send no request.

## The Parliament 15 backfill (not yet run)

The backfill runs after the letter is sent. All of it runs supervised with the owner role, not `hansard_refresh`. The member load inserts into `speaker`, and stage 9 inserts into `person` and sets `speaker.person_id`, and the write role has no grant for any of that.

1. `python scripts/load_parliament_speakers.py --parliament 15`, a dry run. Review the members it lists, then run it again with `--commit`.
2. `python -m scripts.load_heads_of_state`, supervised. It adds the President's Parliament 15 row, and stage 9 then gives that row its `person_id`.
3. Stage 9 for the new speakers: `populate_persons` in `populate/persons.py`.
4. `python refresh.py --allow-parliament 15`, supervised.
5. `python scripts/attribution_text_share.py --output docs/figures/YYYY-MM-DD-backfill-15.txt` on the replica, and a register row, as `CLAUDE.md` requires.

Two things affect the backfill run. The Prime Minister and President terms run to the present. A bare "The Prime Minister" row in Parliament 15 links, and a "The President" row in the Parliament 15 President's Address links once `scripts/load_heads_of_state.py` has run. And the sitting probe covers every date from 9 April 2025, about 560 requests at the crawl rate, plus the topic requests.

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
GRANT USAGE ON SEQUENCE hansardwebsiteresponse_id_seq, hansardsittingdateresponse_id_seq, report_id_seq, speech_id_seq, sitting_id_seq, sittingattendance_id_seq, refresh_run_id_seq TO hansard_refresh;
GRANT SELECT (id, website_responses_added, sitting_date_responses_added, sittings_added, reports_added, speeches_added, speeches_linked, speeches_named_unlinked, attendances_added, attendances_linked, reports_held_without_text, reports_without_speech_rows, reports_rechecked, reports_changed, latest_sitting_date_with_text, figures, started_at, finished_at, status) ON refresh_run TO <the API's read-only role>;
```

The table and sequence names are those on the scratch copy. `attendance` owns `sittingattendance_id_seq`, a name kept from an older table name. Confirm each name on the remote with `\d <table>` first.

The role gets no DELETE or TRUNCATE on any table. It gets no `UPDATE` on `hansardwebsiteresponse`, `hansardsittingdateresponse` or `speaker`, and no `CREATE`, so it cannot run migrations. Migrations stay supervised, with the owner role. `SELECT ... FOR UPDATE` on `refresh_run` needs the `UPDATE` grant the role has. The figures pass reads every report and speech row, which the `SELECT` grants cover.

The API's role gets a column grant that leaves out `halt_reason` and `failure_reason`, because a failure reason can carry database host and user names. Batch E's reader never selects those two columns.

## For batch E

The contract the API reads, from "For batch E" in `plans/launch-build-d2a.md`, with the read grant of "Write role SQL".

- **Columns.** As in "`refresh_run` columns": `id` integer primary key; the count columns, each `integer NOT NULL`: `website_responses_added`, `sitting_date_responses_added`, `sittings_added`, `reports_added`, `speeches_added`, `speeches_linked`, `speeches_named_unlinked`, `attendances_added`, `attendances_linked`, `reports_held_without_text`, `reports_without_speech_rows`, `reports_rechecked`, `reports_changed`; `latest_sitting_date_with_text` `date` NULL; `figures` `jsonb` NULL; `halt_reason` `text` NULL; `failure_reason` `text` NULL; `started_at` `timestamptz NOT NULL`; `finished_at` `timestamptz` NULL; `status` `text NOT NULL`, with the check `status IN ('RUNNING', 'SUCCEEDED', 'HALTED', 'FAILED')`; index `ix_refresh_run_started_at`.
- **Revision.** `b8e2f4a61c03`, down revision `c93f77e499cc`.
- **`figures` shape.** `{"measured_at": "<ISO 8601 UTC>", "groups": [{"group", "report_count", "reports_with_rows_count", "zero_row_report_count", "linked_row_count", "named_unlinked_row_count", "adr_excluded_row_count", "no_speaker_row_count", "row_count", "linked_character_count", "body_character_count", "body_in_zero_row_reports", "report_types": [{"report_type", "report_count", "zero_row_report_count", "collapse_report_count", "collapse_character_count", "body_total", "category_to_row_count", "category_to_character_count"}]}]}`. The groups are "Parliaments 0 to 11", then every Parliament above 11 present in the data. The group fields are the stable contract. Per group, named linked is `linked_row_count / (linked_row_count + named_unlinked_row_count)`, all linked is `linked_row_count / row_count`, and text share is `linked_character_count / body_character_count`.
- **Footer rules.** "Includes sittings up to {date}" is `latest_sitting_date_with_text` of the latest `SUCCEEDED` row. "Last checked {date}" is that row's `finished_at` as a Singapore date. Halted and failed runs move neither. Figures come from the latest `SUCCEEDED` row whose `figures` is not null. While no `SUCCEEDED` row exists, the API shows no footer line and keeps its current figures.
- **Read grant.** The column grant on `refresh_run` in "Write role SQL", which leaves out `halt_reason` and `failure_reason`. Royce runs it.
- **Image.** Repo `roycehoe/hansard-scraper`, `Dockerfile` at the root, branch `master`, command `python refresh.py`.
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

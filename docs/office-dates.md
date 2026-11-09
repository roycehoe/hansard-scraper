# Office dates and ministry groups

This page says what the office tables hold and what their dates mean. It claims nothing beyond the Hansard record. The code is in `services/office_printed_range.py`, `services/office_title_ministry.py` and `populate/office_printed_ranges.py`. The decision is in [ADR 0018](adr/0018-printed-offices-and-ministry-groups.md).

## What a printed range is

A printed range is the first and last sitting of an unbroken run of sittings at which a Member's attendance entry printed the same office. `office_printed_range` holds one row per run, with `sitting_count`, `first_sitting_date` and `last_sitting_date`.

## A date is a printed date

`first_sitting_date` and `last_sitting_date` are the dates of sittings whose attendance lists print the title. They do not say when a Member was appointed or resigned. A range says nothing about the days between two sittings, or about the days before its first sitting or after its last. A Member may have held the office before the first sitting of the range, and may have held it after the last.

## What breaks a run

Three things end a run and start a new one:

- another office is printed for the Member at the next sitting;
- no office is printed for the Member at the next sitting;
- the Member is not listed at the next sitting.

Sittings are counted in the order of all stored sitting dates, not the Member's own sittings. A gap is never closed. If the Member is absent from one list, the run before the gap and the run after it are two rows, even when both print the same title.

## A new Parliament starts a new line

A range belongs to a `speaker_id`, and a `Speaker` row holds one Member in one Parliament. A Member who keeps the same title across an election has one range in each Parliament.

## Where each office comes from

`attendance_office.source` says which part of the attendance entry gave the office:

| Value | Meaning |
|---|---|
| `AFTER_CONSTITUENCY_BRACKET` | The office follows the constituency bracket. |
| `AFTER_NAME_COMMA` | The line has no bracket, and the office follows the first comma. |
| `CHAIR_FORM` | The word Speaker stands in the text before the first bracket, and that text is the office. |
| `BEFORE_EX_OFFICIO_BRACKET` | The office stands before "(ex-officio)", as for the Attorney-General, the Chief Secretary and the Financial Secretary. |

`report_put_to.source` says how the question opens:

| Value | Meaning |
|---|---|
| `ASKED_THE` | The question row reads "asked the" followed by the office. |
| `TO_ASK_THE` | The question row reads "To ask the" followed by the office. |

`report_put_to` stores the office the question names. It does not infer it from the Member who answered.

## How to trace a range to its printed lines

1. Read `first_attendance_office_id` and `last_attendance_office_id` on the `office_printed_range` row.
2. Find those rows in `attendance_office`. Each holds `entry_line_printed`, the whole line as printed, and `extracted_at`, the time the row was built.
3. Follow `attendance_id` to the `attendance` row and its sitting.

## Ministries are groups of printed titles

`ministry` holds names from a closed list in `data/ministry_names.json`. `office_title_ministry` puts an exact printed title under one or more of those names.

- A row claims no ministry of that name existed. It says the title, as printed, names that ministry.
- A ministry that was renamed stays as separate rows. "Communications and Information" and "Information, Communications and the Arts" are two ministries here.
- A `ministry_see_also` row links two ministries only when `data/ministry_see_also.json` gives an official source for the link.
- A bare "Minister" keeps no ministry. So do other titles that name a role with no portfolio.
- A title with any clause that does not resolve gets no row at all. The daily refresh sends it in an alert until it is on the hand-kept list in `data/office_title_ministries.json`.
- The Member who answers a question is never read as the office the question was put to.

## The late sitting

The daily refresh extends ranges forward only. If a new sitting is dated earlier than the latest sitting that already has an office row, the run stores the new sitting's office rows, writes no range for that month and sends an alert that lists the dates. To rebuild, run `python -m scripts.apply_attendance_offices --commit`. It deletes every range, stores the office rows again and builds the ranges from the stored rows.

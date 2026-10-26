# 0013. Store what the record prints

Status: accepted, 23 October 2026. Royce set the rule in decision 5 of the R20 column numbers decisions, which he corrected that night, and said it holds generally. The column numbers pass was its first use: commits 8d3fc92 to a6bfb6a on 24 October 2026, with migration `84f98b2550da`. This record writes it down on 27 October 2026. How the site shows these values is [hansard ADR 0006](https://github.com/roycehoe/hansard/blob/master/docs/adr/0006-display-what-the-record-prints.md).

Context. Hansard is cited by column, but the parser removes the column markers before a speech row exists (see the register row on Column and Page markers). `utils/column_numbers.py` reads them again from the raw HTML to give each older-system row the column it starts in. Sometimes the record prints a number that cannot be right. Report 21556 prints 3653 between 3562 and 3564. The marker sequence suggests 3563, so the pass has to choose between the number the record prints and the number we think it meant.

Decision. In Royce's words (decision 5):

> A marker that breaks the sequence while its neighbours agree (report 21556 prints 3653 between 3562 and 3564) is a likely misprint. Store and display the number as printed (3653), never a corrected one: the data stays as close to the record as possible. The row carries a note that the printed number is likely wrong and which number the sequence suggests (3563), so the site can show a footnote or tooltip. A detected misprint does not void the report's range under decision 1. This principle holds generally: where the record prints something, store what it prints and put our reading in a note.

The first implementation is on `speech`. `column_start` holds the column as printed. `column_note` (`ColumnNote`, Postgres type `columnnote`) and `column_suggested` hold our reading of it. `ColumnNote` has three values:

- `LIKELY_MISPRINT`: the marker breaks the sequence while its neighbours agree. `column_start` keeps the printed number and `column_suggested` holds the number the sequence suggests (21556: 3653 stored, 3563 suggested).
- `SPEAKER_NAMED_IN_COLUMN_BEFORE`: the row's own speaker label is printed just before a marker and its first words come after it. Under decision 6 the row takes the column the label is printed in, and the note marks that column as our guess.
- `PRINTED_WITH_L_FOR_1`: the record prints the marker as `Column: l79` (report 38335). Decision 4 stores 179 in the integer column and puts in the note that the record prints `l79`.

`populate/column_numbers.py` sets the three fields, run through `scripts/apply_column_numbers.py`. Every write that changes older-system speech rows reruns it for the reports it touches, so a note never goes stale. The pass has its own row in `docs/data-loss-register.md`, with the counts for each note.

Why. Royce's reason is in the rule: the data stays as close to the record as possible. If we stored 3563 in place of 3653, nobody could tell from the row that the record prints anything else. A reader checking a citation against the printed page would find a different number. With a separate note, both the printed value and our reading stay in the row, and either can be shown or dropped without touching the other.

Consequences.

- When a later change finds a printed value we read differently, it keeps the printed value and adds our reading as a note beside it. It does not rewrite the value.
- The API returns the printed value and the note as they are stored. The site shows the printed value and offers the note (hansard ADR 0006).
- Where the record does not fix a column, the pass stores NULL rather than a guess (register row). Nothing is printed there, so there is nothing for a note to sit beside.
- An integer column cannot hold a printed `l79`. In that case the stored number is our reading, and the note says what was printed (decision 4).

Alternatives.

- Store the number the sequence suggests and keep the printed one in a note. Royce's rule excludes it: "never a corrected one".

# 0014. Speech report type set by each writer

Status: accepted, 30 October 2026. Royce approved the column and the two rebuilt rum indexes on 30 October. Migration `82478ba59541` adds them by copying `speech`, and `scripts/apply_speech_report_type.py` runs it with `alembic check` in one transaction, rolled back unless `--commit`. Neither has shipped yet.

Context. Word search filtered by report type read the type through a join to `report`. To find a page of matches in a rare type, Postgres walked the word's matches in rank or date order and checked each one's report, and the planner cannot see that a word and a type go together, so it expected the walk to stop early. After the API deploy of 30 October, "housing" in written answers still took 10.1 s on production and timed out on 1 of 3 runs. A rum index can filter on a column only when the column sits on the indexed row. So `speech` needs its report's `report_type`, a second copy of a value that lives on `report`, beside the sitting date of [ADR 0010](0010-speech-sitting-date-set-by-each-writer.md). No code in this repo changes `report.report_type` after stage 3 builds the row.

Decision. `speech.report_type` has the type of `report.report_type` (`character varying`) and is NOT NULL. Each writer sets it from the report it builds rows for, as it sets the sitting date:

- stage 4, the daily refresh and `scripts/apply_coverage_refill.py` build their rows with `services/speech.py::build_speeches`;
- `scripts/apply_fresh_parse.py` builds its inserted rows from the report it has read.

No trigger fills it, for the reasons in ADR 0010. The speech-fidelity write tools under `plans/` insert with raw SQL and do not set the column, so they fail on the NOT NULL constraint at their first insert until their next copies read the type from `report`.

Both rum indexes gain the column and keep their names. `ix_speech_transcript_tsv_rum` is `rum (transcript_tsv rum_tsvector_ops, report_type rum_varchar_ops)`. `ix_speech_transcript_tsv_sitting_date_rum` is `rum (transcript_tsv rum_tsvector_addon_ops, report_type rum_varchar_ops, sitting_date) WITH (attach = 'sitting_date', to = 'transcript_tsv')`, with the type before the attached date. The migration copies the table in the six steps of ADR 0010 and checks the copy the same way: the row checksum's old side joins each row to its report's type, and the shape check expects the new column and the two rum index definitions to differ, and nothing else.

The fill. Not yet measured at full size. On a sample of 100,000 rows the median pages read fell from 3,718 to 32 for a relevance page and from 7,060 to 19 for the count, and 1,242 of 1,242 answers were identical. Parliament-only and unfiltered searches did not change. The column adds about 14 MB of heap and the two rum indexes about 6 MB. Since ADR 0010's copy, `ix_speech_speaker_id` has grown from 8 MB to about 91 MB (migrations `6b3a29f6f809` and `3733d52d31dc`), and the copy builds it again. Scaled from ADR 0010's ship, which took 29 minutes on REMOTE with a data directory peak of +1.7 GB and about 1.5 GB of WAL, expect about 30 to 35 minutes, a peak near +1.9 GB and about 1.7 GB of WAL.

Consequences. The API can filter on `speech.report_type` and join `report` only for a Parliament filter. Writers wait for the whole copy; readers wait only for the swap. A future change to a report's type has to rewrite that report's speech rows in the same transaction.

Alternatives.

- Search the 15 smallest types by their report ids, looked up through `ix_report_report_type_id` (migration `91e844f48a2d`): no write, but it helps only those types. Written answers still walk the word's matches.
- Copy `parliament_number` onto `speech` as well: on the sample it made date order and the count slower.
- A trigger, a nullable column or an update in place: turned down in ADR 0010 for the same reasons.

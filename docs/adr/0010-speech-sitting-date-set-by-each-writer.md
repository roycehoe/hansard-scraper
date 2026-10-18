# 0010. Speech sitting date set by each writer

Status: accepted, 18 October 2026. Royce approved the column and a second rum index on 18 October. Migration `c93f77e499cc` adds both by copying `speech`, and `scripts/apply_speech_sitting_date.py` runs it with `alembic check` in one transaction, rolled back unless `--commit`. Neither has shipped yet.

Context. Oldest-first word search ordered every match by its report's sitting date, read through a join. A word in more than about 11% of speeches sorted all its matches on every request: on REMOTE "government" took 34.7 s and "housing" 18.7 s, past the API's 30-second timeout. A rum index can return matches in date order only when the date sits on the indexed row, as an attached column (`rum_tsvector_addon_ops`). So `speech` needs its report's `sitting_date`, a copy of a value that lives on `report`. A copy can fall out of step with its source in two ways: a writer inserts a speech row without it, or a report's date changes and its speech rows keep the old one. No code in this repo changes `report.sitting_date` after stage 3 builds the row.

Decision. `speech.sitting_date` has the type of `report.sitting_date` (`timestamp without time zone`) and is NOT NULL. Each writer sets it from the report it builds rows for:

- stage 4 and `scripts/apply_coverage_refill.py` build their rows with `services/speech.py::build_speeches`, which takes the date from the report;
- the speech-fidelity write tools insert with raw SQL, so their next copies (`plans/speech-fidelity-loop/cycle10/bin/apply_fix10.py` and `ship_delta10.py`) read the date from `report` and carry it to the target.

No database trigger fills it. A writer that forgets the column fails on the NOT NULL constraint at its first insert, so the mistake is loud and nothing wrong is stored. Older copies of the write tools (cycle 9 and earlier) insert without the column and now fail the same way, which is the intended outcome for a tool built against the old schema.

The stored rows get their date from a copy of the table, not an update in place. In one transaction the migration:

1. locks `speech` in SHARE mode, so writers wait and readers go on;
2. creates `speech_new` like `speech` with the new column and copies every row, joined to its report's date, in the order the old table stores them (an order by id made REMOTE plan a sort of the whole table under `work_mem` 2 MB, because its rows are not stored in id order);
3. builds the seven indexes and the two foreign keys, and copies the privileges;
4. checks that the copy holds the same rows: a row count and two sums over each row's hash, one side over the old columns joined to the report's date, the other over the copy, so the recomputed `transcript_tsv` and every date are checked; then it gathers the copy's statistics;
5. takes the ACCESS EXCLUSIVE lock, moves the sequence, drops the old table and renames the new one and its indexes and constraints;
6. checks that the table's shape (columns, indexes, constraints, triggers, policies, owner, privileges, sequence) equals the old one plus the column and the new index.

Any failure rolls the whole transaction back.

The rum index `ix_speech_transcript_tsv_rum` stays. The new index `ix_speech_transcript_tsv_sitting_date_rum` stores the date in place of the word positions, so it cannot return matches by `<=>` relevance: on a test table the planner sorted every match for a relevance query against it. Relevance keeps the first index and date order uses the second.

The fill. Measured on 18 October on a server with REMOTE's memory, WAL and planner settings (`shared_buffers` 189 MB, `maintenance_work_mem` 89 MB, `work_mem` 2 MB, `max_wal_size` 481 MB, `wal_keep_size` 480 MB, `random_page_cost` 1, no parallel maintenance workers) holding a copy of the replica with 1,051,868 rows. Other work kept the host's load average near 8, so the times are high; an earlier version that copied in id order took 150 s on the idle host. WAL was measured on a clone of the replica.

| Step | Time | WAL |
|---|---|---|
| Copy the rows | 74 s | 880 MB |
| Seven indexes and two foreign keys | 174 s | 630 MB |
| Row checksums | 22 s | none |
| Statistics | 4 s | none |
| Swap and commit | 0.4 s | none |
| Total | 276 s | 1,511 MB |

The `transcript_fts` index, which computes each vector again from the text, takes 80 s of the 174.

The table grows from 1,366 MB to 1,675 MB: the new index is 411 MB, and the copied heap is 77 MB smaller than the old one. Until the commit drops the old table both copies exist. In three runs on that server the data directory (databases and WAL) peaked at most 1,736 MiB above its start, a few seconds before the commit. WAL rose at most 224 MiB, because checkpoints recycle it past `max_wal_size`, and temporary files came to 60 MB. A first version compared the two tables with a full join, which spilled 2.3 GB of temporary files under `work_mem` 2 MB and took the peak to 4,057 MiB; the checksums replaced it.

Consequences. The API orders oldest first by `sitting_date |=> '1900-01-01'` and newest first by `sitting_date <=| '2100-01-01'`, then by `speech.id`, which is the order it gave before. Both distances read the new index in order. A sitting before 1900 or after 2099 would get an infinite distance and sort last. Word search filters dates on `speech.sitting_date`. In date order without a member filter it also adds the first and last sitting dates of a Parliament to the Parliament filter, so the index reads only that range; a member's few matches are sorted instead. Writers wait for the whole copy; readers wait only for the swap. A future change to a report's date has to rewrite that report's speech rows in the same transaction.

Alternatives.

- A trigger on `speech` that copies the date on insert, plus one on `report` for a changed date. It would also cover the old write tools. It was turned down because the repo keeps derivations in `services/` and `populate/`, where a reader and a test can see them, and Alembic's autogenerate and `check` do not track triggers, so a trigger dropped or changed by hand would go unnoticed.
- A nullable column: a forgotten writer would store a row that sorts last in date order, silently.
- A generated column cannot read another table.
- Ordering by the joined report date, the shape before this record: it needs no write, and it is the cost this record removes.
- An update in place, in batches with VACUUM between them. Every updated row writes all its words into the three text indexes again, about 13 KB of WAL a row and 14 GB for the table, ten times the copy.
- Dropping the three text indexes, updating in place and rebuilding them: 2.8 GB of WAL, but search runs without its indexes for the whole update. That was 32 minutes on a clone, under load from another job.

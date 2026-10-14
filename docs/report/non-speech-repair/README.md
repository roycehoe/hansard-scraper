# Non-speech repair, 14 October 2026

The stored-row half of `be4d7dd`. The parser change gives no speaker to lines after a procedural line, whole-line editorial notes and "rose" stage directions; this repair applied the same result to the stored `speech` rows with one targeted UPDATE instead of a re-parse, because the re-parse guard of 13 October was not kept and the change only sets speakers to NULL.

The target list came from re-parsing all 41,697 reports with the parser before and after `be4d7dd`, taking every row the new parser nulls, and matching it to its stored row by report and transcript, occurrence by occurrence where a transcript repeats. 12,245 rows were set to `speaker = NULL, speaker_id = NULL`; 11,135 of them were linked. No row moved to a different speaker. Four changed rows in stale reports 26467 and 27699 could not be matched and were left alone.

Before the write, four hand-read passes covered every reset family and line kind; the only real speech found was 6 rows of a Budget statement in report 22691, resumed after a suspension, which had been credited to Mr Speaker. The `speech` table was dumped first (`plans/peer-learnings/speech_before_20261014_125220.dump`, gitignored). The transaction committed only after the loaded, still-attributed and nulled counts all read 12,245.

| File | What it holds |
|---|---|
| `target_ids.json` | The 12,245 speech ids written |
| `snapshot_before.tsv` | Each target's id, report id, speaker and speaker_id before the write; restoring these values undoes the repair |
| `apply.sql` | The transaction as run, with its count checks |
| `summary.json` | Changed, matched, targeted and linked counts by line kind, and the stale-report split |
| `target_sample.json` | 40 random targets, read by hand: all non-speech |

The build and verification scripts are in gitignored `plans/peer-learnings/`. The figures before and after are in [vision.md](../../vision.md) "Measuring progress".

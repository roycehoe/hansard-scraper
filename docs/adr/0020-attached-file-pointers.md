# 0020. Attached file pointers

Status: accepted, 9 November 2026. Migration `81ba3804b972` adds the two tables. None of it has shipped yet.

Context. [ADR 0004](0004-link-urls-dropped-from-report-markdown.md) drops link URLs from report markdown, so a reader of the speech table cannot reach the annex or vernacular-speech PDF a report points to. Two sources know about these files, and they disagree on what a file is. A sitting lists its annexures and vernacular speeches (`sitting.annexures`, `sitting.vernaculars`), with a title and a path but no report. A report's raw HTML holds the download links, with link text and an address but no list entry. The address ties them: a list entry's path and a link's `value` carry the same text.

Decision. Two tables, joined by an optional foreign key.

- `attached_file` has one row per list entry of a sitting, unique on sitting, kind and SPRS file id. The 8 entries that repeat a kind, title and printed path within a sitting are stored once. `download_value` is NULL for the placeholder path `vernacular-null`.
- `attached_file_pointer` has one row per download link in a report's raw HTML, unique on report and ordinal. Its `download_value` is the link's `value`, NULL for the placeholder. `attached_file_id` is NULL until exactly one stored file has the same address.

They are two tables because the two sources do not line up. A sitting lists files that no report links (the 11 listed files of 7 March 2025 have no pointer), and a report links to addresses that no list holds. One table of either would carry NULLs for the half it lacks.

A pointer names its speech row by `speech_ordinal`, not by a foreign key to `speech.id`. A supervised write renumbers, deletes and reinserts speech rows, and only a row paired by speaker and text keeps its id. A foreign key would block those deletes or dangle after them. An ordinal is a position in the report, so the next run of `scripts/apply_attached_files.py` sets it again from the raw HTML and the current rows. `is_paragraph_tie_stale` flags a stored tie whose row no longer holds the link's words.

The paragraph tie rule. The link's words go into three counts: how often they occur in the report's text, how often they occur across the speech rows, and how many pointers carry them. When the first two differ, the pointer gets no paragraph (10 of 4,608). Otherwise the pointer takes the row that holds its own occurrence, and `paragraph_tie_rule` records how sure that is:

- `ONLY_OCCURRENCE`: the words occur once in the report. The row is the only candidate.
- `EVERY_OCCURRENCE_A_LINK`: they occur several times and every occurrence is a link, so the pointers share them one to one in order.
- `OCCURRENCE_BESIDE_PLAIN_TEXT`: they occur several times and some occurrences are plain text, so the match rests on counting occurrences up to the link.

The tiers exist because the first is certain and the other two depend on the order of repeated words. The accuracy check samples each tier on its own.

Re-run after a speech write. Any write that adds, rewrites or deletes speech rows of a report whose raw text holds a download link ends with `python -m scripts.apply_attached_files --commit --report-id ...` for the reports it touched. `scripts/apply_fresh_parse.py` does this inside its own write. The daily refresh needs nothing, since it never rewrites a stored row.

A second file arriving at an address that a pointer already ties keeps that tie. None of the 2,901 addresses spans two sittings, and every folder equals its sitting date, so nothing is built for a second file. If one arrives, the next supervised write refuses at its tie count, and someone looks at it.

Consequences. The speech table, `report.markdown_content` and the raw HTML do not change. The refresh role needs `SELECT` and `INSERT` on both tables, `UPDATE (attached_file_id)` on the pointers and `USAGE` on both sequences ([refresh.md](../refresh.md)). The API reads the tables in a later change.

Alternatives.

- Put the address in `speech.transcript` again: undoes ADR 0004, and the link would still not say which file it names.
- One table keyed by address: loses the files with no link and the links with no file.
- A foreign key from the pointer to `speech.id`: breaks on every supervised speech write, as above.

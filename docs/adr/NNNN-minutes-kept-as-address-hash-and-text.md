# NNNN. Minutes are kept as address, hash and extracted text

Status: proposed, 9 November 2026. From gate 2 of the votes and minutes plan (`plans/votes-and-minutes.md`). Royce confirms it, or drops it by adding a column for the daily files (see Consequences).

Context. Votes and Proceedings are PDFs, and Word files up to about 2010, on parliament.gov.sg. The addresses of 2005 to 2017 no longer open, and the Internet Archive lists only 11 PDFs of 2026 under the live path, so a file the daily job reads may later exist nowhere. The job has no disk.

Decision. `minutes` holds the file's address, the Archive timestamp where one exists, the SHA-256, the size, and the uncleaned text that `pypdf` layout mode or the standard-library OLE2 piece-table reader returned. The bytes of backfill files stay on the build host, and the daily job keeps none. Every later parse reads `minutes.extracted_text`, never a file.

Why. A parser fix reruns on stored text with no request, and a `pypdf` upgrade cannot change a stored result by itself. The SHA-256 proves whether a copy found later is the same file.

Consequences. Extraction is fixed at fetch. A fault in the extractor on a daily-fetched file can only be repaired by fetching the file again, which a dead address rules out. A `bytea` column for daily files would remove that limit. It would cost about 5 MB a year, at 137 to 192 KB a PDF and about 29 sittings a year. Royce decides before the first push that deploys the daily step (the plan's "For Royce" item 3). If the column is added, drop this ADR and write one that records the column. The master numbers this file when it lands. The plan's other decisions do not qualify for an ADR, because pairing, the whole-division rule, side detection, the strict resolver, the `UPDATE` grant and the `sprs_report_id` key all rebuild from stored text or undo in one step.

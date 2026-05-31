# Sitting HTML Formatting Patterns

Structural knowledge about `html_full_content` in `HandsardSittingDateResponse`,
accumulated during the refine-loop. Use this before investigating any new artifact.

## Document eras

Three distinct HTML generation formats, distinguishable by `volume_no`:

| Era          | Volume range | Format characteristics |
|--------------|-------------|------------------------|
| Colonial/early | vol 1–33  | Clean HTML; date + attendance on single lines; no `<b>` wrapping sections; `****` appears only occasionally as section break |
| Mid-era      | vol 38–75   | Introduces empty `<em>` tags between date paragraphs (→ `__` artifact); session/volume info in markdown `* * *` separator; `<a>` appendix links begin appearing in vol 41+ |
| Modern       | vol 76–89   | Completely different HTML structure: no `##` headings; `<b>` tags wrap section titles with internal newlines (→ broken `**` blocks); `<font>` tags throughout body (→ missing spaces, corrupted metadata); part/volume info in a table cell concatenated by html2text |

## `****` (empty bold) lines

Source: empty `<b></b>` or `<strong></strong>` elements used as visual separators in the HTML.
Appear throughout all document eras.
In vol 41–75: clusters of 3–6 appear at document tail, interleaved with appendix links.
html2text renders `<b></b>` as `****` (opening + closing `**` with no content between them).

## Stray `__` line

Source: empty `<em></em>` or `<i></i>` element in the "meeting header" area.
Present in vol 38–70 era documents.
Always appears between `_Day, DDth Month, YYYY_` and `_The House met at HH:MM_` italic lines.
html2text renders `<em></em>` as `__`.

## Split adjournment time

Source: `<br>` tag or hard line break inside the adjournment paragraph.
The HTML contains something like: `Adjourned accordingly at Six<br>minutes to Eight o'clock p.m.`
Affects all eras but most common in vol 31–75.
The split always occurs within the time-of-day phrase (between the hour word and the rest).

## Broken bold blocks (modern era)

Source: Modern HTML (vol 79+) wraps section titles as `<b>\nTITLE\n</b>` with literal newlines inside the tag.
html2text places `**` at the start of the opening tag's line and `**` at the end of the closing tag's line.
Result: `**\nTITLE\n**` instead of `**TITLE**`.
Also affects the ADJOURNMENT section header in these documents.

## Missing spaces in body text (modern era)

Source: `<font size="2">` tags used throughout vol 79+ body text.
When html2text strips these tags, adjacent text runs are concatenated without a space.
Affects inter-word boundaries at font-tag boundaries throughout these documents.

## Concatenated part/volume header (modern era)

Source: Modern HTML stores `PART IV OF FIRST SESSION` and `VOLUME 85` in adjacent table cells.
html2text concatenates adjacent cell text without a separator in some configurations.
Result: `PARTIVOF FIRST SESSION |  VOLUME85`.

## Metadata table rendering

Source: Every document has a 2-column HTML `<table>` at the top with Parliament No, Session No, Volume No, Sitting No, Sitting Date.
html2text renders only the first row with `|` prefix and adds a `---|---` separator. Subsequent rows lose the leading `|`.
The `---|---` separator appears again for every other 2-column table: speaker-signature tables (end of agenda blocks), part/volume info tables (modern era), and bills/dates tables.
Fix: strip all lines matching `---|---` exactly.

## 1-column table separator

Source: Some sittings (vol 39+, 44, 51, 57, 58, 66) place the `PART X OF Y SESSION` header
in a single-cell `<table>` element. html2text renders this the same way as 2-column tables
but the separator is `---  ` (3 dashes + trailing spaces) instead of `---|---`.
Also appears at other single-cell table locations throughout the document.
Note: html2text renders `<hr>` as `* * *`, so any standalone `---` line in these docs is
always a table artefact, never an intentional horizontal rule.
Affects: vol 39, 44, 50, 51, 57, 58, 66 (mid-era and early modern documents).
Fix: strip lines matching `re.fullmatch(r'-{3}\s*', line)` in `_remove_sitting_table_separators`.

## Speaker-signature tables

Source: Appear multiple times per document, at end of each day's order-paper block.
HTML: `<table><tr><td>SPEAKER NAME</td></tr><tr><td><i>Speaker,</i></td></tr></table>`
After metadata-table fix (stripping `---|---`): renders as `| SPEAKER NAME` / `| _Speaker,_` / `| _Parliament of Singapore_`.
The `|` prefix is from html2text's first-row table rendering. These are structural noise; they can be left or stripped as part of a follow-on table-content cleanup.

## Broken italic date (modern era)

Source: `<BR>` inside `<i>` tags in vol 81+ documents.
HTML pattern: `<i>Tuesday, 7th March, 2006<BR></i>` — the `<BR>` causes html2text to close the italic on a new line.
Result: `_Tuesday, 7th March, 2006  ` + `_` (orphan closing marker).
Also appears in: suspension notices (`_Sitting accordingly suspended at  ` + `_`), bill explanations, adjournment line.
Fix: strip standalone `_` lines.

## Extended empty-bold (modern era)

Source: Multiple adjacent `<b></b>` tags or `<b></b>` adjacent to content in vol 81+ documents.
Beyond the basic `****` (single empty bold), two variants:
- `********`: two adjacent `<b></b>` at section/appendix boundaries
- `****Content`: `<b></b>` immediately before content text (e.g. `****Debate resumed.`)
- `Content****`: `<b></b>` immediately after content text
- `********Content`: vol 87 question lines have TWO consecutive `<b></b>` before the question number, producing `********6.**Speaker**`. `re.sub(r'^(\*{4})+', '', ...)` is needed (not `\*{4}`) to strip all groups.
Fix: `_remove_sitting_empty_bold` drops all-asterisk lines (`\*+`) and strips leading/trailing `(\*{4})+` groups from content lines.

## Italic adjournment (vol 81+)

Source: vol 81+ adjournment uses multiple `<p align="right"><I>...</I></p>` elements, one per phrase.
html2text renders each as a separate `_phrase_` line. The merged result ends with `._` (period + italic close).
The adjournment merge stop condition must check `endswith('._')` in addition to `endswith('.')`.
Without this, the merge continues into the following section (e.g. "WRITTEN ANSWERS TO QUESTIONS").

## Known Correct Exclusions

Artifact types confirmed as either correct output or permanently unresolvable. Do not spend iterations on these.

| Artifact | Scope | Reason excluded |
|---|---|---|
| Appendix links (`[Annex title (Cols. X-Y)](url)`) | vol 41+, document tail | Real PDF/GIF links; whether to strip is a product decision, not a cleaning failure |
| Speaker-signature table rows (`\| SPEAKER NAME`, `\| _Speaker,_`) | All eras, end of each day's order-paper block | Structural noise from html2text table rendering; low impact on attendance/speech parsing |

## Appendix links

Source: `<a href="/search/search/download?value=PDFs/...">Annex title (Cols. X-Y)</a>` elements.
Appear in document tail in vol 41+ documents, interleaved with the `****` cluster.
html2text renders these as standard markdown links: `[Annex title (Cols. X-Y)](/search/...)`.
These point to real PDF/GIF documents. Whether to strip them is a product decision.

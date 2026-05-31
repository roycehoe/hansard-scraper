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

## Appendix links

Source: `<a href="/search/search/download?value=PDFs/...">Annex title (Cols. X-Y)</a>` elements.
Appear in document tail in vol 41+ documents, interleaved with the `****` cluster.
html2text renders these as standard markdown links: `[Annex title (Cols. X-Y)](/search/...)`.
These point to real PDF/GIF documents. Whether to strip them is a product decision.

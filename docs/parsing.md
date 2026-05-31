# Parsing Internals

Notes on raw API quirks and how they're handled. Most of this was learned the hard way.

---

## Report HTML (`HandsardWebsiteResponse.content`)

### Two document format generations

The HTML structure changed between Parliament 11 and Parliament 12 (~2012):

| | Old format (Parl ≤ 11) | New format (Parl 12+, ~2012+) |
|---|---|---|
| Header | Single pipe-delimited row: `Section:| X | Title:| Y | MPs Speaking:| Z` | Markdown table, one field per row |
| Title location | Italic (`_Title_`), open bold (`**TITLE  ` with no closing `**`), or plain text between `**` lines | Markdown heading: `# Title` |
| Subtitle | Open bold on its own line: `**(Subtitle)  ` | `## (Subtitle)` heading |

The title-detection logic in `get_start_of_speech_line` must handle all three old-format variants plus the new heading format. Use `_strip_md()` (strips `*` and `_`) and compare case-insensitively.

### Mojibake in stored titles

Some titles contain Windows-1252 mojibake of UTF-8 characters. The markdown content has correct Unicode; the `title` field in the DB does not. Fix: `s.encode('cp1252').decode('utf-8')` (no-op for plain ASCII; safe to call unconditionally).

Common patterns:
- `â€™` → `'` (curly apostrophe) — affects ~382 `president-address` titles
- `âˆ'` → `−` (minus sign) — affects ~2,153 `budget` titles like `"Committee of Supply âˆ' Head X"`

### HTML entity artifact in markdown headings

html2text treats `&WORD;` as an HTML entity and preserves the `;` even when the entity is unrecognised. Example: `"Government Subsidies for A&E Patients"` becomes `# Government Subsidies for A&E; Patients` (the semicolon after `&E` is the artifact). The stored `title` field has the semicolon stripped. Strip via `_strip_md()` before comparing.

### Context-prefix lines in old-format titles

In old-format docs, the title often appears at the END of a line that has a context prefix:
- `**[Mr Speaker in the Chair] HEAD X - MINISTRY OF Y**`
- `**<Head N - Ministry of Foreign Affairs**`

After stripping markdown markers and whitespace-normalising, check `line_norm.endswith(title_norm)` (not just equality). Require `len(title_norm) >= 10` to avoid false positives.

### Speech segmentation — preamble and artifact lines

`get_speeches` starts at the `start_of_speech_line` index. The lines immediately following in new-format docs are metadata rows, markdown headings, time markers, and procedural text — all before the first real speaker. Skip lines when `current_speaker is None`.

Artifact lines that must be filtered before speaker-regex matching:
- `**` — standalone asterisks (visual separator)
- `** **` — matches the speaker regex (content = single space), sets `current_speaker = ""`
- `****`, `********` — empty bold pairs
- `**(Subtitle)  ` — open-bold subtitle, not a speaker

Skip any line where `line.strip("* ")` is empty (all characters are `*` or space).

Also filter empty-transcript speeches at return — speaker-intro lines with no inline text produce `Speech(speaker=name, transcript="")`.

### Structurally no-speech document types

~1,449 docs yield no speeches even after correct segmentation. Zero speeches is correct for them — they contain no bold speaker markup. Excluding these from success-rate denominators is intentional:

| `report_type` | Example content |
|---|---|
| `bill` | First/third readings: "presented by X; read the First time…" |
| `motion` | Adjournment resolutions: "Resolved, That Parliament do now adjourn." |
| `budget` | Procedural headers, estimates tables |
| `atbp` | "Assent to Bills Passed" — list of bills |
| `oral-answer` | ANNEX records — PDF/chart link indexes |
| `bill-intro` | Bill introduction notices |
| `speaker` | Speaker procedural statements |

### Single-speaker attribution fallback

For the 1,193 no-speech docs that have exactly one name in the `MPs Speaking:| Name` header, the entire body is attributable to that member (adjournment motions, bill first readings, procedural resolutions). The `MPs Speaking` header line is preserved in the markdown as `MPs Speaking:| Name1; Name2; ...`.

Do not apply this fallback when there are 2+ names — those are ANNEX/appendix documents where the names are session participants, not authors.

---

## Sitting HTML (`HandsardSittingDateResponse.html_full_content`)

### Three document eras

html2text artifacts vary by volume number:

| Era | Volume range | Key characteristics |
|---|---|---|
| Colonial/early | vol 1–33 | Clean HTML; no empty-bold artifacts; date and attendance on single lines |
| Mid-era | vol 38–75 | Empty `<em>` tags → `__` artifact; appendix links begin at vol 41+ |
| Modern | vol 76–89 | `<b>` tags with internal newlines → broken bold; `<font>` tags → missing spaces; different table structure |

### html2text artifacts and their fixes

| Artifact | Source | Affected eras | Fix |
|---|---|---|---|
| `---|---` lines | html2text renders every 2-column `<table>` header with this separator | All | Strip lines where `stripped == "---|---"` |
| `---  ` lines (3 dashes + spaces) | html2text renders 1-column `<table>` rows the same way | Mid-era (vol 39, 44, 50, 51, 57, 58, 66) | Strip lines matching `re.fullmatch(r'-{3}\s*', line)` — safe because html2text renders `<hr>` as `* * *`, never `---` |
| `****` (empty bold) | `<b></b>` used as visual separator | All | Strip all-asterisk lines; strip leading/trailing `(\*{4})+` groups from content lines |
| `________` (orphan italic marker) | `<BR>` inside `<i>` tag; closing `_` lands on a new line | Modern (vol 81+) | Strip lines where `stripped == "_"` |
| Broken bold blocks | `<b>\nTITLE\n</b>` with internal newlines | Modern (vol 79+) | Merging required; use the existing `_merge_consecutive_bold_only_lines` approach |
| Concatenated part/volume header | Adjacent table cells concatenated without separator | Modern (vol 76+) | Example: `PARTIVOF FIRST SESSION |  VOLUME85` — handle in downstream parsing, not stripping |

### Source defects (unfixable)

- `"The House met at3.00 pm"` — space missing before the time in the raw HTML. Affects ~3% of modern-era documents. Not fixable without NLP or source correction.
- Appendix links — `[Annex title (Cols. X-Y)](/search/...)` in document tail (vol 41+). Currently left in the markdown.

### Adjournment merge edge case (vol 81+)

The adjournment line in vol 81+ uses multiple italic spans that must be merged. The merged line ends with `._` (period + italic close), not `.`. The merge stop condition must check `endswith("._")` in addition to `endswith(".")` — otherwise the merge runs into the next section.

---

## Sitting Date API (`getHansardReport/`)

Two response formats depending on date:

| Format | Parliaments | Date cutoff | Structure |
|---|---|---|---|
| Old | 9–12 | Before 18 Aug 2015 | Flat dict; all fields at top level |
| New | 13+ | From 18 Aug 2015 | Nested: `metadata` object + child lists (`attendanceList`, `ptbaList`, `takesSectionVOList`, `annexureList`, `vernacularList`, `a2bList`) |

`writtenAnswersVOList` and `writtenAnsNAVOList` are always empty in new-format responses — no tables needed.

The API has a typo: `parlimentNO` (not `parliamentNO`). Mapped as `parlement_no` in the database to preserve it faithfully.

---

## MP Attendance (`Sitting.markdown_content`)

### Three attendance section formats

| Era | Volume range | `PRESENT` header | Entry spacing |
|---|---|---|---|
| Colonial/early | vol 1–33 | `PRESENT:` (plain) | One entry per line, trailing spaces |
| Mid-era | vol 38–75 | `PRESENT:` (plain) with blank line after | One entry per line |
| Modern | vol 76+ | `**PRESENT:**` (bold) | One entry per blank-line-separated paragraph |

The `ABSENT` section follows the same format. The section ends when `#### PERMISSION` or another `####` heading is encountered.

### Attendance line format

```
[Title] [Name] [(Constituency)][, Portfolio/role].   
```

Title prefixes to strip: `Mr`, `Mrs`, `Dr`, `Inche`, `Encik`, `Madam`, `Mdm`, `Ms`, `Prof.`, `Assoc. Prof.`, `BG`, `RAdm`, `The Honourable`. Compound titles occur (`The Honourable Mr`, `Assoc. Prof.`).

Constituency is an optional parenthetical: `(Tanjong Pagar)`, `(Nominated Member)`, `(Non-Constituency Member)`, `(ex-officio)`.

Speaker entries appear at the top: `Mr SPEAKER (Mr Name (Constituency)).` — include them.

### Name matching against `Mp` table

`Mp.name` stores names without title prefixes. Known variations:
- Honorific suffixes in attendance not in `Mp.name` — e.g. `C.B.E.`, `J.P.`
- `Mp.name` sometimes stores `Surname, Firstname` (e.g. `Barker, E.W.`) while the attendance line uses natural order
- Colonial-era prefix titles (`Inche`, `The Honourable`) absent from `Mp.name`
- Parliament number join key: `Sitting.parlement_no` (note the spelling) → `Mp.parliament_number`

# Parsing internals

This page describes quirks in the raw application programming interface (API) responses and how the parser handles them.

---

## Report HTML (`HansardWebsiteResponse.content`)

### Two document format generations

Report HTML has two formats, divided between Parliament 11 and Parliament 12 (~2012):

| | Old format (Parl ≤ 11) | New format (Parl 12+, ~2012+) |
|---|---|---|
| Header | Single pipe-delimited row: `Section:| X | Title:| Y | MPs Speaking:| Z` | Markdown table, one field per row |
| Title location | Italic (`_Title_`), open bold (`**TITLE  ` with no closing `**`), or plain text between `**` lines | Markdown heading: `# Title` |
| Subtitle | Open bold on its own line: `**(Subtitle)  ` | `## (Subtitle)` heading |

`get_start_of_speech_line` must handle all three old-format title variants and the new heading. Compare case-insensitively after `_strip_md()` strips `*` and `_`.

### Mojibake in stored titles

Some raw titles contain mojibake, garbled UTF-8 characters read as Windows-1252. The markdown has correct Unicode. In `utils/text.py`, `fix_mojibake` encodes each non-ASCII run as cp1252, decodes it as UTF-8, and keeps runs that fail. A title can hold a correct `’` beside a garbled run, as in "Committee of Supply âˆ’ Head U (Prime Minister’s Office)", so a whole-string decode fails.

Two common patterns:

- `â€™` → `’` (curly apostrophe), in `president-address` titles
- `âˆ’` → `−` (minus sign), in `budget` titles like `"Committee of Supply âˆ’ Head X"`

### HTML entity artifact in markdown headings

html2text preserves the `;` in `&WORD;` even for unrecognised HTML entities. For example, `"Government Subsidies for A&E Patients"` becomes `# Government Subsidies for A&E; Patients` (the `&E` semicolon is the artifact). The stored `title` field has the semicolon stripped. Strip via `_strip_md()` before comparing.

### Context-prefix lines in old-format titles

In old-format documents, the title often appears at the end of a line that has a context prefix. Two examples:

- `**[Mr Speaker in the Chair] HEAD X - MINISTRY OF Y**`
- `**<Head N - Ministry of Foreign Affairs**`

Strip markdown markers, normalise whitespace, and check `line_norm.endswith(title_norm)` (not just equality). Require `len(title_norm) >= 10` to avoid false positives.

### Speech segmentation: preamble and artifact lines

`get_speeches` starts at the `start_of_speech_line` index. In new-format documents, the lines immediately following are metadata rows, markdown headings, time markers, and procedural text, all before the first real speaker. Skip lines when `current_speaker is None`.

Filter four kinds of artifact line before matching speaker names with a regular expression:

- `**`: standalone asterisks (visual separator)
- `** **`: matches the speaker regex (content = single space), sets `current_speaker = ""`
- `****`, `********`: empty bold pairs
- `**(Subtitle)  `: open-bold subtitle, not a speaker

Skip any line where `line.strip("* ")` is empty (all characters are `*` or space).

Filter empty transcripts at return. Speaker introductions without inline text produce `Speech(speaker=name, transcript="")`.

### Structurally no-speech document types

~1,449 documents yield no speeches even after correct segmentation. Zero speeches is correct for them because they contain no bold speaker markup. Excluding these from success-rate denominators is intentional:

| `report_type` | Example content |
|---|---|
| `bill` | First/third readings: "presented by X; read the First time…" |
| `motion` | Adjournment resolutions: "Resolved, That Parliament do now adjourn." |
| `budget` | Procedural headers, estimates tables |
| `atbp` | "Assent to Bills Passed": list of bills |
| `oral-answer` | ANNEX records: PDF/chart link indexes |
| `bill-intro` | Bill introduction notices |
| `speaker` | Speaker procedural statements |

### Single-speaker attribution fallback

For the 1,193 no-speech documents that have exactly one name in the `MPs Speaking:| Name` header, the entire body is attributable to that member (adjournment motions, bill first readings, and procedural resolutions). The `MPs Speaking` header line is preserved in the markdown as `MPs Speaking:| Name1; Name2; ...`.

Do not apply this fallback when there are 2+ names. Those are ANNEX/appendix documents where the names are session participants, not authors.

---

## Divisions in speech rows

`services/division.py` reads the divisions of one report from its speech rows. A division counts only where the record prints the House or the Committee dividing, or the Chair giving a number for the Ayes and a number for at least one other side.

### Count labels

A printed count line and a spoken total name their sides with "Ayes", "Noes", "No", "Abstentions", "Absent" and "Paired", and with the misprints listed in `_LABEL_TO_SIDE`. The record prints a lone Member's vote in the singular, so "Aye" reads as "Ayes", in the count line and as a heading of the name list (`services/division_list.py`). Report 32776 (31 August 1983, row 54) prints "The House divided: Aye, 1; Noes, 56; Abstention, 1."

### Opening lines

A printed count line opens with "The House divided", "The Committee divided", "Division taken" or "On question put, the House divided". One stray backtick before the opening is read past, and `printed_counts` keeps it, because the record prints it. Report 38784 (17 April 1962, row 5) prints "`The House divided: Ayes, 29; Noes, 17; Absent, 5; Abstentions, Nil."

### Openings without counts

An opening that prints no counts ("The House divided:", or "The House divided and the Clerk proceeded to call out the names of hon. Members -") makes no division of its own. When the next count line after it is the Chair's spoken total, with no other opening between, that total is the division and the opening is not listed as unread. Otherwise the opening is listed as `OPENING_WITHOUT_COUNTS`. In report 39235 (24 May 1961) the opening is row 172 and the Chair's total, "The result of the voting is Ayes, 6; No, 1; Abstentions, 40; Absent, 3.", is row 226.

### Counts of voices or hands

A count of voices or hands by the Chair is not a division. The record prints no division opening and no list of names for it. In report 33022 (31 August 1982) Mr Jeyaretnam says "Division, Sir.", the Chairman asks "Do you really want a Division to be taken, or a show of hands?", he answers "A show of hands.", and the Chairman then says "One against. The Ayes have it." (row 63). The row gives no count for a second side, so it stays on the review list as `TOTAL_WITHOUT_SECOND_COUNT` and no division is stored.

---

## Sitting HTML (`HansardSittingDateResponse.html_full_content`)

### Three document eras

The HTML-to-markdown converter html2text produces different artifacts in three volume ranges:

| Era | Volume range | Key characteristics |
|---|---|---|
| Colonial/early | vol 1 to 33 | Clean HTML; no empty-bold artifacts; date and attendance on single lines |
| Mid-era | vol 38 to 75 | Empty `<em>` tags → `__` artifact; appendix links begin at vol 41+ |
| Modern | vol 76 to 89 | `<b>` tags with internal newlines → broken bold; `<font>` tags → missing spaces; different table structure |

### html2text artifacts and their fixes

| Artifact | Source | Affected eras | Fix |
|---|---|---|---|
| `---|---` lines | html2text renders every 2-column `<table>` header with this separator | All | Strip lines where `stripped == "---|---"` |
| `---  ` lines (3 dashes + spaces) | html2text renders 1-column `<table>` rows the same way | Mid-era (vol 39, 44, 50, 51, 57, 58, 66) | Strip lines matching `re.fullmatch(r'-{3}\s*', line)`: safe because html2text renders `<hr>` as `* * *`, never `---` |
| `****` (empty bold) | `<b></b>` used as visual separator | All | Strip all-asterisk lines; strip leading/trailing `(\*{4})+` groups from content lines |
| `________` (orphan italic marker) | `<BR>` inside `<i>` tag; closing `_` lands on a new line | Modern (vol 81+) | Strip lines where `stripped == "_"` |
| Broken bold blocks | `<b>\nTITLE\n</b>` with internal newlines | Modern (vol 79+) | Merging required; use the existing `_merge_consecutive_bold_only_lines` approach |
| Concatenated part/volume header | Adjacent table cells concatenated without separator | Modern (vol 76+) | Example: `PARTIVOF FIRST SESSION |  VOLUME85`: handle in downstream parsing, not stripping |

### Source defects (unfixable)

Two source defects remain in the markdown:

- `"The House met at3.00 pm"`: space missing before the time in the raw HTML. Affects ~3% of modern-era documents. Not fixable without natural language processing (NLP) or source correction.
- Appendix links: `[Annex title (Cols. X-Y)](/search/...)` in document tail (vol 41+). Currently left in the markdown.

### Adjournment merge edge case (vol 81+)

Merge the multiple italic spans in vol 81+ adjournment lines. The result ends with `._` (period + italic close), not `.`. The merge stop condition must check `endswith("._")` in addition to `endswith(".")`: otherwise the merge runs into the next section.

---

## Sitting date API (`getHansardReport/`)

The sitting date API has two response formats, depending on the date:

| Format | Parliaments | Date cutoff | Structure |
|---|---|---|---|
| Old | 9 to 12 | Before 18 Aug 2015 | Flat dict; all fields at top level |
| New | 13+ | From 18 Aug 2015 | Nested: `metadata` object + child lists (`attendanceList`, `ptbaList`, `takesSectionVOList`, `annexureList`, `vernacularList`, `a2bList`) |

`writtenAnswersVOList` and `writtenAnsNAVOList` are always empty in new-format responses: no tables needed.

The database maps the API typo `parlimentNO` (not `parliamentNO`) to `parlement_no` to preserve it faithfully.

---

## MP attendance (`Sitting.markdown_content`)

### Three attendance section formats

Attendance lists use three formats:

| Era | Volume range | `PRESENT` header | Entry spacing |
|---|---|---|---|
| Colonial/early | vol 1 to 33 | `PRESENT:` (plain) | One entry per line, trailing spaces |
| Mid-era | vol 38 to 75 | `PRESENT:` (plain) with blank line after | One entry per line |
| Modern | vol 76+ | `**PRESENT:**` (bold) | One entry per blank-line-separated paragraph |

`ABSENT` follows the same format. Sections end at `#### PERMISSION` or another `####` heading.

### Attendance line format

```
[Title] [Name] [(Constituency)][, Portfolio/role].   
```

Title prefixes to strip: `Mr`, `Mrs`, `Dr`, `Inche`, `Encik`, `Madam`, `Mdm`, `Ms`, `Prof.`, `Assoc. Prof.`, `BG`, `RAdm`, `The Honourable`. Compound titles occur (`The Honourable Mr`, `Assoc. Prof.`).

Constituency is an optional parenthetical: `(Tanjong Pagar)`, `(Nominated Member)`, `(Non-Constituency Member)`, or `(ex-officio)`.

Speaker entries appear at the top: `Mr SPEAKER (Mr Name (Constituency)).`: include them.

### Name matching against `Speaker` table

`Speaker.name` stores names without title prefixes. Known variations:

- Honorific suffixes in attendance not in `Speaker.name`: e.g. `C.B.E.`, `J.P.`
- `Speaker.name` sometimes stores `Surname, Firstname` (e.g. `Barker, E.W.`) while the attendance line uses natural order
- Colonial-era prefix titles (`Inche`, `The Honourable`) absent from `Speaker.name`
- Parliament number join key: `Sitting.parlement_no` (note the spelling) → `Speaker.parliament_number`

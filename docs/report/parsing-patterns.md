# Parsing Patterns

Reusable structural knowledge about Hansard markdown format and report types.

## Document Format Generations

### New Format (Parliament 12+, ~2012 onwards)
- Header block is a markdown table (pipe-delimited), one field per line
- Title appears as a markdown heading: `# Title`
- Subtitle (if any) appears as `## (Subtitle)`
- Currently handled correctly

### Old Format (Parliament 11 and earlier)
- Header block has ALL fields on a single pipe-delimited row: `Section Name:| X | Title:| Y | MPs Speaking:| Z`
- Document starts with `---` separator
- Title appears in one of these bold patterns (none of which are handled by `_merge_consecutive_bold_only_lines`):

#### Old Format Variant A — Open bold (bill, motion, speaker, ministerial-statement, oral-answer)
```
**
**TITLE TEXT  
**

**(Subtitle Text)  
**
```
The title line starts with `**` but has NO closing `**`. The merge function requires `**text**` pattern and ignores these.

#### Old Format Variant B — Plain text between `**` markers (written-answer, written-answer-na)
```
**
TITLE TEXT
**
```
The title line has NO `**` markers at all. The title is plain text sandwiched between standalone `**` lines.

## Mojibake in Stored Titles

Some reports (budget, president-address, others) have titles stored with Windows-1252 mojibake of UTF-8-encoded Unicode characters:
- `â€™` → `'` (U+2019, RIGHT SINGLE QUOTATION MARK) — UTF-8 bytes E2 80 99 read as cp1252
- `âˆ'` → `−` (U+2212, MINUS SIGN) — UTF-8 bytes E2 88 92 read as cp1252

The markdown content contains the correct Unicode. The stored title has mojibake. Fix: encode as cp1252, decode as UTF-8.

Affected patterns:
- budget: "Committee of Supply âˆ' Head X" titles (~2153 docs)
- president-address: "Debate on Presidentâ€™s Address" titles (~382 docs)

## Speech Segmentation: Document Structure

### Start-line position

`get_start_of_speech_line` returns the index of the title match, which for new-format docs is the `Title:| ...` metadata row (row 7–8 of the markdown). `get_speeches` starts at `start_of_speech_line + 1`, so the lines immediately following are:
- `MPs Speaking:| ...` (metadata)
- Blank lines
- `# Title` (markdown heading)
- `## (Subtitle)` (markdown subheading)
- Time marker: `4.28 pm`
- Procedural text: `Order for Second Reading read.`

All of these precede the first real speaker and must be skipped. Guard: skip non-speaker lines when `current_speaker is None`.

### Artifact lines in old-format docs

Old-format docs use open-bold for section headers and separators:
- `**` — standalone asterisks (page break / separator)
- `** **` — two asterisk pairs with a space (formatting artifact)
- `****` — four asterisks
- `**(Subtitle Text)  ` — open bold with content (subtitle, not a speaker)

The `** **` pattern is dangerous: the speaker regex `((?:\*\*[^*]+?\*\*\s*)+)` matches it (content = single space), producing `speaker = ""`. Subsequent lines then get attributed to this empty speaker.

Guard: skip any line where `parsed_line.strip("* ")` is empty (all characters are `*` or space).

### Empty-transcript speeches

When a speaker is introduced on a line with no trailing text (`**Mr Smith:**\n`), or mid-sentence (`"The question stood in the name of **Mr Smith:**"`), the speaker-change Speech gets `transcript = ""`. These are not content — filter them out at the return.

### Structurally no-speech documents

~1,449 docs have no bold speaker markup after the start line. These are procedural records:
- **Adjournment motions** (`motion`): "Resolved, That Parliament do now adjourn..."
- **Bill first/third readings** (`bill`): procedural passing records with no debate
- **Budget procedural entries** (`budget`): "Order read for consideration in Committee of Supply [7th Allotted Day]"
- **Assent to Bills Passed** (`atbp`): lists of bills the President assented to
- **ANNEX records** (`oral-answer`): charts/tables referenced during oral answers
- **Bill introductions** (`bill-intro`): "presented by X; read the First time..."
- **Speaker announcements** (`speaker`): Speaker procedural statements with no speaker markup

**Requirement: every speech must have a speaker.** `get_speeches` applies fallback attribution in two stages:

1. **`MPs Speaking` header**: if exactly one name is present and `_parse_speeches` returns `[]`, the body is attributed to that name. Covers the 1,193 single-speaker docs in this group.
2. **Body-content patterns** (for zero-speaker docs where `MPs Speaking` is absent or empty):

| `report_type` | Pattern | Where author appears |
|---|---|---|
| `atbp` | Speaker signature at foot of notice | `\| FULL NAME\n---|---\n\| _Speaker_` |
| `president-address` (addendum) | Ministry heading + plain-text name | `**MINISTRY OF X**\nMR NAME\nMinister for...` |
| `president-address` (actual speech) | No ministry heading present | Returns `"The President"` — the President is not an MP |
| `motion` (adjournment) | Mover named in resolved clause | `- [Dr Name]` or `− [Mr Name]` |
| `bill` (First Reading) | Presenter named in bill text | `presented by ... (Mrs Name)` |

Additionally: old-format president-address docs (Parliament 10 and earlier) use bold section headers (`**EXTERNAL ENVIRONMENT**`, `**HOUSING**`, etc.) which `_parse_speeches` misidentifies as speakers. When `MPs Speaking` is empty and `parsed[0].speaker` looks like a section header (all-caps, no honorific), `get_speeches` collapses everything to a single correctly-attributed speech.

True exclusions (~490 docs total):
- `MPs Speaking` absent or empty AND no body-content pattern matched (~237 docs) — genuinely no attributable author (e.g. budget procedural orders, annex appendices with empty `MPs Speaking`)
- `MPs Speaking` lists 2+ speakers and body is a PDF/table link index (~253 docs) — attribution would be fabrication

## HTML Entity Artifacts

Some titles have `&WORD;` where html2text preserves the `;` from unrecognized HTML entities:
- DB title: `Government Subsidies for A&E Patients`
- Markdown heading: `# Government Subsidies for A&E; Patients`

The `;` after `&E` is an artifact of html2text treating `&E;` as an (invalid) HTML entity name. The stored title had the semicolon stripped when originally parsed.

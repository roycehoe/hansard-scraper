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

## HTML Entity Artifacts

Some titles have `&WORD;` where html2text preserves the `;` from unrecognized HTML entities:
- DB title: `Government Subsidies for A&E Patients`
- Markdown heading: `# Government Subsidies for A&E; Patients`

The `;` after `&E` is an artifact of html2text treating `&E;` as an (invalid) HTML entity name. The stored title had the semicolon stripped when originally parsed.

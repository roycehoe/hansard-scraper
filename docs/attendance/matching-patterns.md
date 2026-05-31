# Attendance Name Matching Patterns

Accumulated knowledge about how MP names appear in `markdown_content` vs how they are
stored in the `Mp` table. Used by `services/sitting_attendance.py`.

---

## Volume → Parliament mapping

Derived from the `Parliament No:| N` header embedded in every sitting's markdown_content.

| Volume range | Parliament | Notes |
|---|---|---|
| 1–11 | 1 | Colonial Legislative Assembly (1955–1959). **DATA GAP: these MPs are NOT in the Mp table.** The Mp table's parliament 1 contains post-independence MPs (1965+). Exclude from match-rate denominator. |
| 12–23 | 0 | State of Singapore Assembly (~1960–1963). No Mp rows for parliament 0. Exclude from denominator. |
| 24–26 | 1 | Post-independence Parliament 1 (~1965–1968). MPs ARE in table. |
| 27–31 | 2 | |
| 32–35 | 3 | |
| 36–39 | 4 | |
| 40–44 | 5 | |
| 45–51 | 6 | |
| 52–58 | 7 | |
| 59–66 | 8 | |
| 67–73 | 9 | |
| 74–81 | 10 | |
| 82–87 | 11 | |
| 88–89 | 12 | Uses `## Present:` bullet-list format rather than plain `PRESENT:` |

---

## Attendance section formats

### Colonial / mid-era (vol 1–87)

Three sub-formats:

1. **Plain colonial** (vol 1–37): `PRESENT:   ` on its own line (trailing spaces), entries on
   separate lines ending with `. ` (period + trailing spaces). Section ends at `ABSENT:` or
   `#### ` heading or `* * *`.

2. **Mid-era** (vol 38–75): same as plain colonial but has a blank line after the `PRESENT:`
   header before entries begin.

3. **Bold modern** (vol 76–87): `**PRESENT:**` (bold-wrapped). Entries separated by blank
   lines (paragraph-per-entry). Section ends at `**ABSENT:**` or `* * *`.

### Modern (vol 88–89)

`## Present:` / `## Absent:` (markdown headings). Entries as `  * Name (Constituency).`
bullet list. Section ends at `# Permission` or next `#` heading.

---

## Name format in markdown

Standard entry line:

```
[Title] [Name][, Honorifics] [(Constituency)][, Portfolio [possibly (sub-part)]].   
```

Key rules:
- **Constituency** is the FIRST parenthetical after the name (not the last — portfolio can
  have additional parentheticals, e.g. `(Foreign Affairs)` after `(Kampong Glam)`).
- **Title prefixes** to strip (see `_TITLE_PREFIXES` in the service). Includes Islamic
  honorifics `Tuan Haji`, `Haji`, `Hj.`.
- **Honorific suffixes** appear before the constituency paren, comma-separated:
  `, C.B.E.`, `, PBM`, `, B.B.M., J. P.` (can include spaces within a token, e.g. `J. P.`).
- **Islamic suffix** `Al-Haj` / `Al-Hajj` can trail the name after a space.
- **SPEAKER** entries: `[Title] SPEAKER ([Title] Name [(Constituency)])`. Parse the
  inner parenthetical as a regular entry.

---

## Name format in Mp table

### Standard cases (no comma)

Most names: natural order, `Firstname Surname` or full name. Direct exact match.

### Inverted format (`Surname, Firstname`)

152 MPs (out of 1348) are stored as `Surname, Firstname` or `Surname, Firstname, TitleSuffix`.
Examples: `Barker, E.W.`, `Chandra Das, S.`, `Conceicao, J.F.`, `Jayakumar, S.`.

The extraction service builds a reverse-lookup from the natural markdown form back to the
canonical inverted Mp.name.

**Variant: title suffix in inverted name** (`Surname, Firstname, Dr`):
The trailing title suffix is stripped when computing the natural form.
Examples: `Chen Seow Phun, John, Dr` → natural `John Chen Seow Phun`.
         `Chiang See Ngoh, Claire, Mdm` → natural `Claire Chiang See Ngoh`.

**Variant: multi-word surname** (`Cheong Yuen Chee, Eric`):
Markdown sometimes uses only the surname part without the given name
(`Mr Cheong Yuen Chee` instead of `Mr Eric Cheong Yuen Chee`). The service adds a
surname-only lookup key for multi-word surnames that are unique within a parliament.

### Non-standard inverted (no comma, surname-first)

Some MPs are stored surname-first without a comma: `Tan H.H. Augustine`.
The service handles 3-word names by trying the rearrangement
`words[-1] words[1:-1] words[0]` → `Augustine H.H. Tan`.

---

## Normalisation applied before lookup

1. **Consecutive initial collapsing**: `E. W. Barker` → `E.W. Barker` (spaces between
   consecutive single-letter initials are removed).
2. **Malay abbreviation**: `Mohd.` → `Mohd` (trailing period after `Mohd` is stripped).
3. **Lone leading initial** (lookup only, NOT stored): `S. Rajaratnam` → `S Rajaratnam`
   for lookup purposes only, matching `Rajaratnam, S` whose natural form has no period.
   The stored `mp_name` retains the period where present (e.g. `A. Rahim Ishak`).

---

## Known data gaps

Names that appear in the markdown but have NO corresponding Mp row:

| Name | Parliament(s) | Notes |
|---|---|---|
| `Lai Tha Chai` | 3 | Not in Mp table |
| `Ya'acob Bin Mohamed` / `Tuan Haji Ya'acob Bin Mohamed` | 2, 3 | Not in Mp table |
| `Mohd Ghazali Bin Ismail` (with period: `Mohd.`) | 2 | May appear with OCR variation |

OCR errors observed (corrected in the source document but un-matchable):
- `Hwang Soo un` → should be `Hwang Soo Jin`
- `Wong Lm Ken` → OCR corruption
- `P. Seivadurai` → OCR variant of `P. Selvadurai` (itself a mp-name variation)

---

## Special cases

### Speaker election sittings

Sitting id=1465 (vol=27, parliament=2) is a Speaker election sitting. The `PRESENT`
section contains procedural text after the MP list ends (lines like
`"That Mr Punchardsheram Coomaraswamy do take the Chair..."`). These are incorrectly
extracted as MP entries because the section has no `ABSENT:` marker to terminate it.
Affects 5 extracted "names" — all unmatched, lowering this sitting's match rate.
The sitting still passes the 80% threshold (89.1% with the procedural noise).

### Vol 1–11 colonial assembly

The markdown uses parliament number 1 for both:
- Colonial Legislative Assembly sittings (vol 1–11, 1955–1959): DIFFERENT set of MPs
- Post-independence parliament 1 (vol 24–26, 1965–1968): MPs ARE in table

Only the latter set can be matched. Vol 1–11 sittings are excluded from the
match-rate denominator.

# No-Speech Doc Attribution

## Background

The speech parsing pipeline (`services/speech.py::get_speeches`) identifies 1,449 docs as
"no-speech" — docs where a start line was found but `get_speeches` returns an empty list.
These were excluded from the speaker/transcript quality target (see `docs/report/progress.txt` Iteration 6).

The refine-loop exclusion rationale was: "zero speeches is correct for these — they have no
speaker markup." This is technically true but misses the point: **every entry in the Hansard
was authored by a parliamentary member**, and the Hansard records who that member is.

The goal of the pipeline is to map every word recorded in the Hansard back to the member who
spoke or wrote it. That goal is not met for these 1,449 docs.

---

## Where the Attribution Lives

Every `HandsardWebsiteResponse.content` HTML document contains an `MPs Speaking` / `MP_Speak`
field — either as an HTML `<meta>` tag (old format) or as a table row (new format). This field
is already carried through to the markdown header by `get_cleaned_handsard_markdown` as:

```
MPs Speaking:| Name1; Name2; ...
```

This is the Hansard's own attribution for the record. It names the member(s) who moved,
presented, or authored the item.

---

## Population Breakdown

Total no-speech docs: **1,449**

| `MPs Speaking` count | Total | Notes |
|----------------------|-------|-------|
| 0 (empty) | 3 | Nothing to attribute |
| 1 (single) | 1,193 | Attributable — see below |
| 2+ (multi) | 253 | Not attributable — see below |

### By `report_type`

| type | zero | single | multi |
|------|------|--------|-------|
| `motion` | 0 | 334 | 15 |
| `bill` | 1 | 335 | 9 |
| `budget` | 0 | 218 | 69 |
| `atbp` | 2 | 143 | 0 |
| `oral-answer` | 0 | 8 | 76 |
| `speaker` | 0 | 63 | 1 |
| `president-address` | 0 | 44 | 4 |
| `written-answer` | 0 | 2 | 46 |
| `ministerial-statement` | 0 | 13 | 30 |
| `bill-intro` | 0 | 26 | 0 |
| `misc` | 0 | 7 | 0 |
| `written-answer-na` | 0 | 0 | 2 |
| `yang-di-message` | 0 | 0 | 1 |

---

## Single-Speaker Docs (1,193) — Attributable

Body text is short procedural content authored by the single named member:

- **Adjournment motions** — `"That Parliament do now adjourn." − [Mr Gan Kim Yong]`
- **Bill First Readings** — `"presented by the Minister for Home Affairs (Mr Wong Kan Seng); read the First time…"`
- **Procedural resolutions** — President's concurrences, oaths, etc.

The `MPs Speaking` name IS the author. The body text IS their contribution.

**Example** (`motion`, parl 12, `id=20452`):
```
MPs Speaking:| Mr Gan Kim Yong
...
# Adjournment
Resolved, "That Parliament do now adjourn." − [Mr Gan Kim Yong].
_Adjourned accordingly at 6.59 pm._
```

---

## Multi-Speaker Docs (253) — Not Attributable

Body text is a PDF annex/table link index with no prose. The multiple names in `MPs Speaking`
are session participants, not authors of the annex document itself.

**Example** (`oral-answer`, parl 10, `id=25173`):
```
MPs Speaking:| Mr Lee Hsien Loong; Dr Amy Khor; Dr Lily Neo; Mr Gan Kim Yong; ...
Title: ANNEX - ECONOMIC RESTRUCTURING SHARES
---
[Annex - Singaporeans who did not qualify for ERS (Cols. 2273-2274)](url)
```

**Example** (`budget`, parl 10, `id=25152`):
```
MPs Speaking:| Mr Lee Hsien Loong; Mr Abdullah Tarmugi (Mr Speaker);
Title: APPENDIXES - ANNUAL BUDGET STATEMENT
---
[ANNEX A - CHANGES TO EXCISE DUTIES FOR PETROL (Cols. 117-118)](url)
[ANNEX B - UTILITIES SAVE REBATES (Cols. 117-118)](url)
...
```

All four multi-speaker types (`oral-answer`, `budget`, `written-answer`,
`ministerial-statement`) follow this pattern: the body is an index of PDF links, not speech.
Attributing these to any individual would be fabrication.

---

## Requirement

Every record in the target set must produce at least one speech with a non-None, non-empty speaker. Records with exactly one name in `MPs Speaking` are **always in the target** — the pipeline must attribute the body text to that person.

Exclusions (zero speeches is genuinely correct):
- `MPs Speaking` absent or empty (0 speakers)
- `MPs Speaking` lists 2+ speakers **and** no bold speaker markup — these are annex/appendix index documents

## Status: Implemented (`51cdd99`)

`services/speech.py::get_speeches` applies the fallback: when `_parse_speeches` returns `[]`, it checks `MPs Speaking` for exactly one name and, if found, returns a single `ParsedSpeech` covering all non-empty, non-decorative body lines joined.

**Actual outcome:**
- No-speech docs dropped from 1,449 to ~256 (253 multi-speaker annex + 3 zero-speaker).
- 1,193 previously-unattributed records now produce a correct speaker attribution.
- Multi-speaker docs (2+ names) still return `[]`.
- Zero-speaker docs still return `[]`.

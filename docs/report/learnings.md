# Parsing Refinement Learnings

## Remaining zero-speech docs (~490) — as of post-body-attribution commit

After both attribution stages (MPs Speaking fallback + body-content patterns), ~490 docs still return no speech. Catalogued below to avoid re-running the analysis.

### Multi-speaker annex/index docs (~253) — correct exclusion

Body is a list of PDF/table links. Attribution would be fabrication. Spread across:

| type | count | pattern |
|---|---|---|
| `oral-answer` | 76 | `APPENDIX - ...` titles; MPs Speaking has 2–20+ names; body is `[table/chart - ...](url)` links |
| `written-answer` | 46 | Same pattern |
| `ministerial-statement` | 30 | Same pattern |
| `motion` | 15 | Same pattern |
| `bill` | 9 | `APPENDIX - ... BILL` titles; PDF link body |
| `budget` | 69 | `APPENDIX - BUDGET, MINISTRY OF ...` titles; PDF link body |
| `president-address` | 4 | `APPENDIX - DEBATE ON PRESIDENT'S ADDRESS`; PDF link body |
| `speaker` | 1 | `APPENDIX - UNPARLIAMENTARY LANGUAGE`; PDF link body |
| `written-answer-na` | 2 | `APPENDIX - CONSTITUTION ...`; PDF link body |
| `yang-di-message` | 1 | `APPENDIX - YANG DI-PERTUAN NEGARA'S SPEECH`; PDF link body |

Sample IDs: 31065 (oral-answer), 27859 (written-answer), 27394 (ministerial-statement), 30213 (budget), 29793 (president-address).

### Zero-speaker docs with no extractable attribution (~237) — by type

#### `budget` (193) — procedural orders, no named author

Two sub-patterns:
1. **Committee of Supply procedural orders** — `Order read for consideration in Committee of Supply [Nth Allotted Day]. [Mr Speaker in the Chair]`. No individual author. Sample IDs: 23568, 22094.
2. **Very old records (1955–1961, parliament 0)** — single-line entries like `Head 3-` or `The sum of $X for Head Y ordered to stand part of the Schedule.` No MPs Speaking field exists for these parliaments. Sample IDs: 40090, 41477.

#### `atbp` (24) — Assents to Bills Passed without Speaker signature

These differ from the 118 that were fixed: they have no Speaker signature table at the foot (the `| NAME\n---|---\n| _Speaker_` pattern is absent). Body content varies:
- Some have only `Appendix I` or `#### ASSENTS TO BILLS PASSED` with no bill list after start_line.
- Very old records (parliament 3–6) where the signature may use a different format.
Sample IDs: 32052, 33287, 34839.

#### `president-address` (4) — addenda where minister name regex didn't match

Content follows the `**MINISTRY OF X**\nNAME\nTitle` pattern but the regex failed. Likely cause: ministry name doesn't contain "MINISTRY" or "PRIME MINISTER" (e.g. "ISTANA" or an unusual office title), or the minister title line uses an unexpected word. Sample IDs: 21394, 23494.

Note: `id=21394` has "RADM LUI TUCK YEW / Acting Minister for..." — "Acting Minister" IS in the regex alternation; likely the bold heading uses a non-standard ministry name. `id=23494` has "MR LEE HSIEN LOONG / Prime Minister and Minister for Finance" — the heading is `**MINISTRY OF FINANCE**` which should match. May be a whitespace or encoding issue worth inspecting.

#### `misc` (4) — varied procedural records

- `id=21695`: President's concurrence with a parliamentary resolution — no bold speaker, body is the resolution text. Could be attributed to "The President" by a future rule.
- `id=38101`, `id=38383`: Attendance records (lists of members at sittings). Not attributable speech.
- One further id to identify.

#### `bill` (3) — mislabelled or appendix

- `id=24271`, `id=24287`: Adjournment resolutions tagged as `bill` type. Body has `- [Mr Mah Bow Tan]` attribution but `_extract_body_attribution` only fires the bracket pattern for `report_type == "motion"`. Fixable: extend the adjournment mover regex to cover `bill` type too, or fix the type label.
- `id=26002`: `APPENDIX - REPLY BY MINISTER FOR EDUCATION ON COMPULSORY EDUCATION BILL`. PDF link body with empty MPs Speaking. Minister identity is in the title but not in a parseable body pattern.

#### `speaker` (4) — Speaker appendices and committee of supply

All are `APPENDIX - COMMITTEE OF SUPPLY` or similar with PDF link bodies and empty MPs Speaking. Sample IDs: 36881, 25526.

#### `ministerial-statement` (2) / `oral-answer` (2) / `written-answer` (1) — appendices with empty MPs Speaking

Zero-speaker appendix docs where the body is a PDF link table. No individual attribution possible. Sample IDs: 25635 (ministerial-statement).

## Setup

- **Baseline:** 15272/21826 (70.0%) pass rate across all report types with markdown, excluding `bill-intro`
- **No-speech types excluded:** `bill-intro` (28 docs with markdown, 0 speeches — these are formal bill-reading notices, not speech transcripts)
- **Only failure stage:** `has_start_line` (6554 failures). `can_get_speeches` failures = 0.
- **Failure breakdown by type:**
  - `budget`: 2186 failing / 2370 with markdown (92.2% fail rate)
  - `president-address`: 424 / 438 (96.8%)
  - `atbp`: 338 / 403 (83.9%)
  - `speaker`: 243 / 335 (72.5%)
  - `motion`: 680 / 2077 (32.7%)
  - `written-answer`: 578 / 2059 (28.1%)
  - `oral-answer`: 382 / 7572 (5.0%)
  - others: small counts

---

## Iteration 1

### has_start_line — oral-answer, written-answer, motion, budget, president-address — title appears as markdown `# heading` in Parliament 12+ (2012+) documents

**Affected report IDs (sample):** 19984, 20002, 20027 (oral-answer); 19975, 19985, 19986 (written-answer); 20475, 20067 (motion); 20362, 20363, 20366 (budget); 20826, 20847, 20851 (president-address)

**Markdown snippet (failing — oral-answer, 2012):**
```
| Parliament No:| 12  
...
# Update on National Research Foundation's Work
1 **Dr Lim Wee Kiak** asked the Prime Minister ...
**The Deputy Prime Minister ... (Mr Teo Chee Hean) (for the Prime Minister)** : ...
```

**Markdown snippet (failing — oral-answer with italic in heading, 2012):**
```
# Impact of Livestock Export Rule Changes on the Annual Observance of _Korban_ in Singapore
6 **Assoc Prof Fatimah Lateef** asked the Minister ...
```

**Markdown snippet (passing — oral-answer, 2009):**
```
****
**ILLEGAL MONEYLENDERS AND RUNNERS**

12\. **Mdm Cynthia Phua** asked the Deputy Prime Minister ...
```

**Why it fails:**
`get_start_of_speech_line` checks for `{title}**` (bold marker at end) in each line. New-format documents (Parliament 12+, 2012 onwards) have the title as a markdown h1 heading (`# Title`), which contains no `**` markers. The function scans the entire document and finds nothing.

**Proposed fix:**
After the existing bold-title checks, add a check: if the line starts with `#`, strip the `#` prefix and markdown emphasis markers (`_`, `*`), then compare case-insensitively against `title`, `f"{title} {subtitle}"`, and `original_title` (with newlines replaced by spaces). Return that line index if matched.

This is purely additive — old-format documents never have a bare `# Title` line that matches the document title (their title is in bold), so no regressions are expected.

**Net outcome:** Applied in iteration 1. See post-patch statistics below.

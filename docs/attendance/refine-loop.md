# Environment Note

All Python scripts in this project must be run via `poetry run python3` (not bare `python3`).
The project uses a remote PostgreSQL database; the `DATABASE_URL` is loaded from `.env` automatically
when the script is invoked from the project root inside the poetry environment.

---

# Before Starting — Resume Check

Before beginning Setup or any loop iteration, scan the working directory for existing artifacts and load them:

- `docs/attendance/sample.json` — the fixed strata drawn at Setup Step 2; if present, use it as-is.
- `docs/attendance/progress.txt` — iteration log; if present, read it to determine which iteration the loop is on and what was last attempted.
- `docs/attendance/matching-patterns.md` — accumulated knowledge about name formats and matching strategies; if present, read it before investigating any failures.

**Do not regenerate any of the above files if they already exist.** If all artifacts are present, skip Setup and resume from the last incomplete step recorded in `docs/attendance/progress.txt`.

**Prerequisite: sitting loop completion.** The attendance loop reads `Sitting.markdown_content`, which is produced by `get_cleaned_sitting_markdown` from the sitting loop. Do not start this loop until the sitting loop has reached its completion criterion (≥95% of sitting documents artifact-free). Running attendance against unsettled sitting markdown means some extraction failures are actually cleaning failures — they will be misdiagnosed and won't be fixable here.

# Goal

Produce a `get_sitting_attendance` function that takes a `Sitting` row and returns a list of `Attendance` records — one per MP entry in the `PRESENT` and `ABSENT` sections of `markdown_content` — with:

- `sitting_id` set to the `Sitting.id`
- `speaker_name` set to the normalised name string (prefix and constituency stripped)
- `attendance` set to `True` for PRESENT entries, `False` for ABSENT entries
- `location_name` set to the constituency extracted from the parenthetical

**Primary focus: colonial-era sittings (volume 1–33).** Mid-era (vol 38–75) and modern (vol 76+) coverage is a secondary concern; failing to handle newer formats is acceptable if colonial sittings are well-covered.

Success: ≥95% of extracted attendance entries across the colonial-era target sample are matched to an `Mp` record by name and parliament number, tracked in `docs/attendance/progress.txt`.

"Matched" means a unique `Speaker` row exists where `Speaker.name` equals the normalised `speaker_name` and `Speaker.parliament_number` equals the sitting's parliament number. A sitting with no `parlement_no` (and no inferred parliament number) is excluded from the match-rate denominator. Track total excluded count separately.

**Secondary metric:** also track `total names matched / total names extracted` across the sample. This surface unmatched names that are hidden within "successful" sittings (a sitting counts as matched at ≥80% name-level accuracy, so up to 20% of its names may still be unmatched).

# Context

## Source field

`Sitting.markdown_content` — the cleaned markdown produced by `get_cleaned_sitting_markdown`. The attendance section lives near the top of this field, before the agenda begins.

## Target table

`Attendance` (already defined in `database/attendance.py`):
- `sitting_id` — FK to `sitting.id`
- `speaker_name` — normalised name (no title prefix, no constituency)
- `attendance` — `True` = present, `False` = absent
- `location_name` — constituency extracted from the parenthetical

**Note:** `Attendance` does not currently have an `mp_id` FK column. Matching to `Mp` is validated during the loop but the FK column is added only once matching is stable (a separate migration step, not part of the loop).

## Document eras and section formats

Three distinct formats exist, driven by volume number (see `docs/sitting/formatting-patterns.md` for full details):

| Era | Volume range | PRESENT header | Entry spacing | Priority |
|-----|-------------|----------------|---------------|----------|
| Colonial | vol 1–33 | `PRESENT:` (plain) | One entry per line, trailing `   ` | **Primary** |
| Mid-era | vol 38–75 | `PRESENT:` (plain) with blank line after | One entry per line | Secondary |
| Modern | vol 76+ | `**PRESENT:**` (bold) | One entry per blank-line-separated paragraph | Secondary |

**Note:** Volumes 34–37 are not currently mapped to an era. If they appear in the DB, treat them as Colonial until the actual format is confirmed and record the finding in `docs/attendance/matching-patterns.md`.

The ABSENT section follows the same format as PRESENT within each era. The section ends when `#### PERMISSION` or another `####` heading is encountered.

## Parliament number — prerequisite

`Speaker.parliament_number` is the join key alongside name. The `Sitting` table has `parlement_no` (note the spelling) which maps to `Speaker.parliament_number`.

When `Sitting.parlement_no` is `None`, parliament number must be inferred from `volume_no`. **Establishing this volume→parliament mapping is a prerequisite for measuring the match rate on affected sittings.** Before drawing the sample, query the DB for the set of distinct `(volume_no, parlement_no)` pairs where `parlement_no` is not None, and use that to fill in the gaps. Record the completed mapping in `docs/attendance/matching-patterns.md`. Any volume that cannot be mapped remains excluded from the match-rate denominator — log the count.

## Name format in markdown

Each attendance line has the form:

```
[Title] [Name] [(Constituency)][, Portfolio/role].   
```

Where:
- **Title** (optional): `Mr`, `Mrs`, `Dr`, `Inche`, `Encik`, `Madam`, `Mdm`, `Ms`, `Prof.`, `Assoc. Prof.`, `BG`, `RAdm`, `The Honourable`, etc. Compound titles occur (`The Honourable Mr`, `Assoc. Prof.`).
- **Name**: the MP name, matching (with some variation) `Speaker.name`.
- **Constituency** (optional parenthetical): e.g., `(Tanjong Pagar)`, `(Nominated Member)`, `(Non-Constituency Member)`, `(ex-officio)`.
- **Portfolio** (optional, after comma): e.g., `, Prime Minister`.
- `SPEAKER` entries appear at the top (`Mr SPEAKER (Mr Name (Constituency)).`) — include them.

## MP table join

`Speaker.name` stores names without title prefixes. Variations to watch for:
- Honorifics appended to markdown names but absent from `Speaker.name` (e.g., `C.B.E.`, `J.P.`)
- Ordering: `Speaker.name` sometimes stores `Surname, Firstname` (e.g., `Bani, S.T.`, `Barker, E.W.`) while markdown uses natural order
- Colonial-era prefix titles (`Inche`, `The Honourable`) absent from `Speaker.name`
- Modern-era name changes between parliaments (same person, different name spelling)

# Method

Iteratively refine name extraction and MP matching until the success threshold is met.

## Setup

The setup is not bookkeeping. Steps 1–2 validate that the goal is correctly scoped before iteration begins.

**Step 1 — Validate the target set.**
Query `Sitting` rows where `markdown_content` contains no `PRESENT` text. For a random sample of 5–10 of these, inspect the raw markdown: are they genuinely attendance-free (e.g. committee sittings, procedural sittings, Supply sittings), or is `PRESENT` missing due to a parsing failure in `get_cleaned_sitting_markdown`?

If a meaningful fraction are parsing failures, stop here — fix `get_cleaned_sitting_markdown` first; the attendance loop cannot proceed on broken input. If they are genuinely attendance-free, record the sitting types / structural signals that distinguish them, then exclude them from the target set. Write findings to `docs/attendance/progress.txt` under `## Setup — Target set validation`.

**Step 2 — Draw a stratified sample.**
Query `Sitting` rows where `markdown_content` is not None and the sitting is in the target set (has PRESENT text). Stratify by `(era, failure_stage)` — where era is derived from `volume_no` and failure_stage is assessed against the baseline function to be written in Step 3. On the first draw (before baseline exists), stratify by era only and add failure_stage breakdown after Step 4.

Era derivation:
- Colonial: vol 1–33 (and vol 34–37 until format confirmed)
- Mid-era: vol 38–75
- Modern: vol 76+

Within each `(era, failure_stage)` group, draw three sets:

- **Pilot** (up to K=5 per group): used for diagnosis and inspection. Weight toward colonial — draw K=5 colonial and K=3 mid/modern.
- **Held-out** (up to K=3 per group): not inspected during diagnosis; used only in Loop Step 5. If a group has fewer than 4 sittings total, draw all into pilot and mark as having no held-out set.
- **Regression** (~15 total, drawn from sittings already producing clean extraction): checked after every fix. Draw at least 5 colonial, at least 3 mid-era, at least 3 modern (or all available if fewer).

Write all three to `docs/attendance/sample.json`:

```json
{
  "pilot": [1, 2, 3, ...],
  "held_out": [10, 11, ...],
  "regression": [20, 21, ...]
}
```

Do not re-sample in later iterations.

**Step 3 — Implement the baseline extraction function.**
Write `get_sitting_attendance(sitting: Sitting) -> list[Attendance]` in `services/sitting_attendance.py`. The initial implementation should handle at minimum the colonial-era plain `PRESENT:` / `ABSENT:` format. Do not attempt to handle all eras at once — the loop will add coverage iteratively.

The function signature:

```python
def get_sitting_attendance(sitting: Sitting) -> list[Attendance]:
    ...
```

Returns one `Attendance` per parsed MP line. `speaker_name` should be the name after stripping the title prefix and constituency parenthetical. `location_name` should be the constituency text (without parentheses). `attendance` should be `True` for PRESENT entries, `False` for ABSENT entries.

**Step 4 — Define the two failure stages and run the baseline.**
A sitting fails at:

- `can_extract=False` — the PRESENT section cannot be located in `markdown_content`, or zero names are returned (when the sitting demonstrably has attendees — check for `PRESENT` text in the raw markdown). Sittings where `markdown_content` has no `PRESENT` text at all are excluded from the target set; record the count.
- `can_match=False` — names are extracted but fewer than 80% match an `Speaker` row (by `speaker_name` + inferred parliament number → `Speaker.name` + `Speaker.parliament_number`). Sittings with no resolvable parliament number are excluded from the match-rate denominator.

Run the baseline against the pilot sample. Record:
- Count of sittings excluded (no PRESENT text in markdown)
- Extraction success rate: sittings where `can_extract=True`, broken down by era
- Match success rate: of sittings with a resolvable parliament number, the fraction where ≥80% of extracted names match an `Speaker` row, broken down by era
- Total individual names matched vs. unmatched (the secondary metric)

Write to `docs/attendance/progress.txt` under `## Setup — Baseline`.

**Step 5 — Catalogue failure modes.**
For each failing pilot sitting, record which failure stage it falls into and why. Group failures by root cause (not by individual sitting). Write to `docs/attendance/progress.txt` under `## Setup — Failure catalogue`. Common failure modes to expect:

- Extraction: modern-era bold `**PRESENT:**` not matched by a regex expecting plain `PRESENT:`
- Extraction: SPEAKER line parsed incorrectly (nested parentheses)
- Matching: title prefix not fully stripped (`Inche`, `The Honourable`, compound titles)
- Matching: honorific suffix not stripped (`, C.B.E.`)
- Matching: inverted name format in `Speaker.name` (`Barker, E.W.`)
- Matching: parliament number not resolvable — excluded from denominator, log

If a generalizable pattern is discovered, also record it in `docs/attendance/matching-patterns.md`.

## Loop

The authoritative iteration count is the number of `## Iteration N` headings in `docs/attendance/progress.txt`.

**Step 1 — Identify the highest-impact unresolved failure group.**
From the current catalogue in `docs/attendance/progress.txt`, pick the failure mode affecting the most sample entries. Prioritise:
1. `can_extract=False` failures in colonial-era sittings
2. `can_match=False` failures in colonial-era sittings
3. `can_extract=False` failures in other eras (optional — skip if colonial target is met)
4. `can_match=False` failures in other eras (optional)

Extraction must succeed before matching is meaningful.

**Step 2 — Investigate.**
Open `markdown_content` for 2–3 sittings exhibiting the failure. Compare against 1–2 sittings **from the same era** where the same stage succeeds. For matching failures, also compare the extracted name string against the actual `Speaker.name` values for that parliament. Determine the root cause precisely.

**Step 3 — Log findings.**
Append to `docs/attendance/progress.txt` under a `## Iteration N — YYYY-MM-DD` heading:

```
## Iteration N — YYYY-MM-DD

### <failure_stage> — <era> — <short description of root cause>

**Affected sitting IDs:**
<list>

**Markdown snippet (failing):**
<representative lines from a failing sitting>

**Markdown snippet (passing, same era):**
<comparable lines from a passing sitting in the same era — required for can_extract failures>

**Extracted name (before fix) vs. Speaker.name (expected):**
<side-by-side comparison for can_match failures>

**Root cause:**
<what the current logic does wrong>

**Proposed fix:**
<the regex or logic change>

**Backward-compatibility reasoning:**
<which currently-passing sittings could be affected, and why they won't be>

**Outcome:** (filled in after Step 5)
<kept / reverted — net change>
```

If the finding reveals a generalizable pattern about name formats or era attendance structure, also record it in `docs/attendance/matching-patterns.md`.

**Step 4 — Apply one fix.**
Modify `services/sitting_attendance.py` only. Apply one fix per iteration. Prefer a **condition-gated branch** — gate on era (derived from `volume_no`) or on a structural signal in the markdown — rather than modifying the general path. This limits regression blast radius by leaving the existing path untouched.

**Step 5 — Validate.**
Re-run `get_sitting_attendance` across the full sample. Print a table covering pilot, held-out, and regression sets:

```
Failure stage     | Era      | Before | After
can_extract       | Colonial |  1/5   |  0/5
can_extract       | Modern   |  3/5   |  0/5
can_match (name)  | Mid-era  |  2/5   |  1/5
---
Regression set regressions: 0/15
Secondary metric: names matched / names extracted: 312/340 (91.8%)
```

Decision rule:
- **Keep** if: the target failure count decreased AND the regression set shows no new failures AND (where a held-out set exists) at least 2 sittings flipped from failing to passing, or >50% of the held-out group if it has fewer than 4 sittings.
- **Revert** if: new failures appeared in the regression set, the target failure count did not decrease, or the held-out bar was not met.

Log the outcome in `docs/attendance/progress.txt`.

**Step 6 — Widen the sample (every 3 iterations).**
Add more sittings to the sample from `(era, failure_stage)` groups that are underrepresented or not yet in the pilot. K=5 colonial, K=3 mid/modern per group still applies to new groups. Draw a fresh held-out set for the new groups only. Expand the regression set proportionally, maintaining the era distribution floor (≥5 colonial, ≥3 mid-era, ≥3 modern).

**Step 7 — Check completion.**
Compute the current colonial-era match rate across the full pilot sample (sittings with resolvable parliament numbers only). If ≥95% of those sittings pass (≥80% of their extracted names matched), stop and report success.

If the rate has plateaued below 95% and the only remaining failures are sittings with known data gaps (parliament numbers that cannot be resolved, MPs not in the `Mp` table due to data coverage), also stop — record the ceiling and the reason. Do not iterate against permanently unresolvable cases; see `docs/attendance/matching-patterns.md` → Known Correct Exclusions.

Otherwise continue.

If this is iteration 10 (or a multiple of 10), stop and go to Step 8.

**Step 8 — Ask for approval to continue.**
Present:
- Current extraction and match success rates vs. target, broken down by era
- Marginal gain this iteration (how many sittings flipped from failing to passing)
- Resolved failure groups (with before/after counts)
- Remaining unresolved groups and their current counts
- Any failure modes that appear structurally unfixable (e.g., name not present in `Mp` table at all due to data gaps)
- Secondary metric: total names matched / total names extracted

Ask: "Should I continue iterating?"

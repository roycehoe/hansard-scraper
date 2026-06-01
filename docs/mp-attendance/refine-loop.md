# Environment Note

All Python scripts in this project must be run via `poetry run python` (not bare `python`). Set `DATABASE_URL` explicitly for localhost:

```
DATABASE_URL="postgresql://user:password@localhost:5432/postgres" poetry run python -c "..."
```

---

# Before Starting — Resume Check

Before beginning Setup or any loop iteration, load existing artifacts:

- `docs/mp-attendance/sample.json` — the fixed sample drawn at Setup Step 3; if present, use it as-is.
- `docs/mp-attendance/progress.txt` — iteration log; read it to determine which iteration the loop is on and what was last attempted.
- `docs/mp-attendance/matching-patterns.md` — accumulated knowledge about mp_name formats and failure modes; read before investigating any failures.

**Do not regenerate any of the above files if they already exist.** Handle partial artifact states as follows:
- All three present → skip Setup entirely; resume from the last incomplete step in `progress.txt`.
- `sample.json` present but `progress.txt` absent → treat as iteration 0; go directly to Loop Step 1 without re-running Setup.
- `progress.txt` present but `sample.json` absent → flag as an integrity issue before proceeding.

---

# Goal

Improve `_populate_attendance_mp_ids` in `populate/mp_links.py` so that ≥95% of `SittingAttendance` rows in the matchable target set receive a non-null `mp_id`.

**Target set definition** — exclude from the denominator:
1. **Rows with null `mp_name`**: already excluded by the matching code.
2. **Genuinely absent names**: colonial-era Legislative Assembly members (pre-1965) not scraped into the `Mp` table, and non-MP attendees (ministers, civil servants, foreign dignitaries). These are structurally absent — do not attempt to match.

A row is in the **`can_match` failure stage** when `mp_name` is non-null, is not excluded by the above, and `mp_id` remains null after `_populate_attendance_mp_ids` runs.

"Matched" means `SittingAttendance.mp_id` is non-null. Track the match rate as `matched / denominator`.

**Secondary metric**: also track `matched / total non-null-mp_name rows` to make the exclusion count visible.

---

# Context

## What `SittingAttendance.mp_name` contains

Set by `services/sitting_attendance.py` from parsing the PRESENT/ABSENT sections of sitting markdown. The name is extracted with minimal normalisation — titles are NOT stripped at parse time. The raw attendance list entry becomes `mp_name` directly.

## Current matching logic

`_populate_attendance_mp_ids` in `populate/mp_links.py`:
1. Loads all `SittingAttendance` rows with `mp_id IS NULL` in batches of 1000
2. For each record: calls `infer_parliament(sitting)` to get the parliament number
3. Does a raw dict lookup: `mp_id_lookup.get((record.mp_name, parliament))`
4. **No name normalisation is applied** — the lookup is exact-case, exact-string

The `mp_id_lookup` dict is keyed by `(mp.name, mp.parliament_number)` using the canonical `Mp.name` value as stored in the DB.

## Where fixes go

All matching logic lives in `_populate_attendance_mp_ids` in `populate/mp_links.py`. The helper `resolve_canonical_name` (in `services/sitting_attendance.py`) provides the full resolution cascade (inverted-name, bin-free, word-set, prefix, spelling, Haji-stripping) and should be reused here — add pre-processing steps and plug into the cascade before falling back to the raw dict lookup.

## How parliament is derived

`infer_parliament(sitting)` maps `sitting.volume_no` (or `sitting.parlement_no`) via `VOLUME_TO_PARLIAMENT`. Volumes 12–23 map to parliament 0 — no `Mp` rows exist for `parliament_number = 0`. The speech pipeline already falls back to parliaments 1, 2, 3 for parliament 0 records; apply the same fallback here.

## Known failure categories (from full-corpus analysis, 2026-06-01)

| Root cause | Rows | Fix |
|---|---|---|
| Parliament 0 — no Mp rows for those volumes | 7,751 | Add fallback to parliaments 1, 2, 3 (same as speech pipeline) |
| Case mismatch (`bin` vs `Bin`) | 1,457 | Normalise case before lookup, or run through resolve_canonical_name |
| No name normalisation — person IS in Mp but surface form differs | ~12,089 | Apply strip_title + normalize_name + resolve_canonical_name before lookup |
| Colonial-era MPs not scraped | ~3,945 | Structurally absent — not fixable |
| Other absent names (non-MP attendees, etc.) | ~5,390 | Structurally absent — not fixable |

---

# Baseline

From full-corpus run after `populate_mp_links` (2026-06-01):

| Table | Matched | Total | Rate |
|---|---|---|---|
| `sittingattendance` | 65,695 | 96,327 | 68.2% |

Top unmatched `mp_name` values (full corpus):
- `Abdullah Tarmugi` ×679 — missing Bin
- `Tony Tan Keng Yam` ×648 — inverted format
- `George Yong-Boon Yeo` ×581 — inverted format
- `Sidek bin Saniff` ×552 — bin vs Bin
- `S. Jayakumar` ×539 — period initial, no normalisation

---

# Method

## Setup

**Step 1 — Define the denominator.**
Query the DB to count:
- Total `sittingattendance` rows with non-null `mp_name`
- Rows where `mp_name` is from a known non-MP / colonial-era bucket (investigate empirically)
- Denominator = total − structurally absent

Record under `## Setup — Denominator` in `docs/mp-attendance/progress.txt`.

**Step 2 — Draw a stratified sample.**
Query `SittingAttendance` rows with non-null `mp_name` and `mp_id IS NULL`, stratified by **parliament number**. Use parliament buckets: colonial (parliament ≤ 3 or = 0), mid (4–8), modern (9–15). Draw K=10 pilot and K=5 held-out per bucket. Draw ~30 regression speeches from rows that already have `mp_id` non-null (already matched), distributed across parliaments.

Write all IDs to `docs/mp-attendance/sample.json`:
```json
{
  "pilot": [123, 456, ...],
  "held_out": [789, 101, ...],
  "regression": [202, 303, ...]
}
```

Do not re-sample in later iterations.

**Step 3 — Record the baseline.**
For each pilot record, run the current matching logic and record matched/unmatched. Group failures by root cause. Record under `## Setup — Baseline` in `docs/mp-attendance/progress.txt`.

**Step 4 — Catalogue failure modes.**
For each failing pilot record classify root cause. Record under `## Setup — Failure catalogue`.

## Loop

The authoritative iteration count is the number of `## Iteration N` headings in `docs/mp-attendance/progress.txt`.

**Step 1 — Run the sample.**
Apply the current `_populate_attendance_mp_ids` logic to every ID in the pilot, held-out, and regression sets. Record matched/unmatched per record.

**Step 2 — Identify the highest-impact unresolved failure.**
From the failure catalogue, pick the pattern affecting the most pilot records.

Priority order:
1. Pre-processing failures (case, period-stripping, missing Bin) — fix in `_populate_attendance_mp_ids`
2. Missing normalisation pipeline — plug in `resolve_canonical_name`
3. Parliament 0 fallback — add fallback loop over parliaments 1–3
4. Manual overrides — add to `_MANUAL_OVERRIDES` in `services/sitting_attendance.py`

**Step 3 — Investigate.**
Open 2–3 failing records exhibiting the target pattern. Note exact `mp_name`, `parliament`, and expected `Mp.name`. Also open 1–2 passing records from the same parliament for contrast.

**Step 4 — Log findings.**
Append to `docs/mp-attendance/progress.txt` under `## Iteration N`:

```
## Iteration N

### can_match — parliament <N> — <short description>

**Affected IDs (pilot):** <list>
**mp_name (failing):** <exact string>
**mp_name (passing, same parliament):** <example>
**Expected Mp.name:** <canonical form>
**Root cause:** <what goes wrong>
**Proposed fix:** <code change in populate/mp_links.py>
**Backward-compatibility:** <reasoning>
**Outcome:** (filled after Step 5)
```

If the finding reveals a generalizable pattern, also update `docs/mp-attendance/matching-patterns.md`.

**Step 5 — Apply one fix.**
Modify `populate/mp_links.py` only (or `services/sitting_attendance.py` for `_MANUAL_OVERRIDES`). One fix per iteration.

**Step 6 — Validate.**
Re-run matching on all three sets. Print a table:

```
Pattern          | Parliament | Before | After
-----------------|------------|--------|------
bin vs Bin       | 4–8        |  3/10  |  9/10
---
Held-out improvement: N records flipped
Regression set failures: 0/30
Secondary metric (incl. absent): X/total
```

Decision rule:
- **Keep** if: matched count in pilot increased AND regression set shows no new failures AND held-out shows improvement (≥2 flipped, or >50% of held-out group if fewer than 4)
- **Revert** if: regressions appear or held-out bar not met.

**Step 7 — Check completion.**
Compute `matched / denominator` across the pilot. If ≥95%, stop. If all remaining failures are permanently unresolvable (structurally absent MPs), stop and record the ceiling.

If this is iteration 10 or a multiple of 10, stop and ask for approval to continue.

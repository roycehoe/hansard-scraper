# Environment Note

All Python scripts in this project must be run via `poetry run python3` (not bare `python3`), with `PYTHONPATH` set to the project root:

```
PYTHONPATH=/path/to/handsard-scraper poetry run python3 scripts/speech_speaker_match_rate.py
```

The project uses a remote PostgreSQL database; `DATABASE_URL` is loaded from `.env` automatically.

---

# Before Starting — Resume Check

Before beginning Setup or any loop iteration, load existing artifacts:

- `docs/speech-speaker/sample.json` — the fixed sample drawn at Setup Step 3; if present, use it as-is.
- `docs/speech-speaker/progress.txt` — iteration log; read it to determine which iteration the loop is on and what was last attempted.
- `docs/speech-speaker/matching-patterns.md` — accumulated knowledge about speaker string formats and failure modes; read before investigating any failures.

**Do not regenerate any of the above files if they already exist.** Handle partial artifact states as follows:
- All three present → skip Setup entirely; resume from the last incomplete step in `progress.txt`.
- `sample.json` present but `progress.txt` absent → treat as iteration 0; go directly to Loop Step 1 without re-running Setup.
- `progress.txt` present but `sample.json` absent → flag as an integrity issue before proceeding. Re-sampling at this point would draw from a smaller failing population and break before/after comparability. Investigate why `sample.json` is missing before continuing.

---

# Goal

Improve `_populate_speech_speaker_ids` in `populate/speaker_links.py` so that ≥95% of Speech rows in the matchable target set receive a non-null `speaker_id`.

**Target set definition** — exclude from the denominator:
1. **Structural non-MPs**: `Mr Speaker`, `Mr Deputy Speaker`, `The Clerk`, `Hon. Members`, and similar presiding officers or collective references. These are never in the `Speaker` table by design.
2. **Section headers misidentified as speakers**: all-caps strings with no name structure (e.g. `LIQUEFIED PETROLEUM GAS (Conditions of a Licence)`, `PART I INTRODUCTION`). These are speech parsing failures — do not fix them here.
3. **Speeches where `speaker` is None**: already excluded.

A Speech row is in the **`can_match` failure stage** when its `speaker` is non-null, is not excluded by the above, and `speaker_id` remains null after `_populate_speech_speaker_ids` runs. This is the only failure stage in this loop.

"Matched" means `Speech.speaker_id` is non-null. Track the match rate as `matched / denominator`.

**Secondary metric**: also track `matched / total non-null-speaker speeches` (including excluded) to make the exclusion count visible.

---

# Context

## What `Speech.speaker` contains

The field is set by `services/speech.py` `_parse_speeches`. It is the raw bold text from the transcript with `*` and `:` stripped — e.g. `**Mr Lee Kuan Yew:**` becomes `Mr Lee Kuan Yew`. It is NOT further normalised at parse time.

Several speaker string formats appear in the corpus:

| Format | Example | Fix |
|--------|---------|-----|
| Title + name | `Mr Lee Kuan Yew` | Strip title prefix (already done) |
| Title + name + (constituency) | `Dr Tan Cheng Bock (Ayer Rajah)` | Strip constituency parenthetical |
| Role + (name) | `The Prime Minister (Mr Lee Kuan Yew)` | Extract name from inner parens |
| Role only | `The Prime Minister` | Unresolvable without a role→MP mapping |
| Short name | `Mr Jeyaretnam` | Falls through to prefix lookup in some cases |
| Presiding officer | `Mr Speaker`, `Mr Deputy Speaker` | Exclude from denominator |
| Section header | `PART I INTRODUCTION` | Exclude from denominator (parsing failure) |

## Where fixes go

All matching logic lives in `_populate_speech_speaker_ids` in `populate/speaker_links.py`. The helper `resolve_canonical_name` (in `services/attendance.py`) handles the existing cascade and should not be modified here — add pre-processing steps before calling it.

## How parliament is derived

`Speech.report_id → Report.parliament_number` (directly stored). No derivation needed.

---

# Baseline

From `scripts/speech_speaker_match_rate.py` (seed=42, K=10 per report_type):

**Overall: 45/170 = 26.5%**

| Report type | Matched | Total | Rate |
|---|---|---|---|
| admin-oaths | 0 | 10 | 0.0% |
| bill | 2 | 10 | 20.0% |
| budget | 4 | 10 | 40.0% |
| deputy-speaker | 0 | 10 | 0.0% |
| matter-adj | 5 | 10 | 50.0% |
| ministerial-statement | 6 | 10 | 60.0% |
| misc | 1 | 10 | 10.0% |
| motion | 1 | 10 | 10.0% |
| obituary-speech | 2 | 10 | 20.0% |
| oral-answer | 4 | 10 | 40.0% |
| personal-explanation | 0 | 10 | 0.0% |
| president-address | 1 | 10 | 10.0% |
| speaker | 0 | 10 | 0.0% |
| tribute | 2 | 10 | 20.0% |
| written-answer | 8 | 10 | 80.0% |
| written-answer-na | 9 | 10 | 90.0% |
| yang-di-message | 0 | 10 | 0.0% |

**Top unmatched strings (sample):**
- `Mr Speaker` ×31 → structural non-MP, exclude
- `Mr Deputy Speaker` ×4 → structural non-MP, exclude
- `Hon. Members` ×3 → collective reference, exclude
- `Dr Tan Cheng Bock (Ayer Rajah)` ×3 → constituency in string, strip it
- `Dr Jennifer Lee (Nominated Member)` ×3 → constituency in string, strip it
- `The Prime Minister (Mr Lee Kuan Yew)` ×4 → role+name, extract inner name
- `The Financial Secretary (Mr T. M. Hart)` ×2 → role+name, extract inner name
- `The Minister for Health (Dr Toh Chin Chye)` ×2 → role+name, extract inner name
- `Mr Jeyaretnam` ×5 → short name, may fall through to prefix lookup
- `Mr Lee Kuan Yew` ×5 → full name not matching (parliament scope issue?)
- Section headers (×5 total) → parsing failures, exclude

**Known failure categories ranked by estimated global impact:**
1. Constituency suffix in speaker string — affects most eras, all report types
2. Role+name pattern (`The X (Name)`) — common in older parliamentary records
3. Structural non-MPs (`Mr Speaker`, `Hon. Members`) — exclude from denominator
4. Section headers — exclude from denominator
5. Short names / parliament scoping for known MPs

---

# Method

**The setup is not bookkeeping.** Its outputs determine whether the goal as written is correct before any iteration begins. Do not start iterating against a wrong target.

## Setup

**Step 1 — Validate the exclusion definitions.**
Before counting the denominator, verify empirically that the two exclusion categories are correctly defined. For each category, inspect 5–10 candidate excluded strings drawn from the actual DB:

- *Structural non-MPs*: query for `speaker` values matching known exclusion strings (`Mr Speaker`, `Mr Deputy Speaker`, `Hon. Members`, etc.) and read the surrounding transcript for a sample of matches. Confirm none are genuine MPs whose name happens to start with a presiding-officer prefix.
- *Section headers*: query for all-caps `speaker` values and inspect a sample. Confirm that no colonial-era speaker names are captured — all-caps formatting was common in old transcripts and some genuine MPs may appear in all-caps.

If the pattern is too broad (catching real MPs) or too narrow (missing exclusions), revise the exclusion definition before proceeding. Record findings in `docs/speech-speaker/progress.txt` under `## Setup — Exclusion validation`. If the definition needs changing, revise the Goal section of this document too.

**Step 2 — Establish the target set denominator.**
Query the DB directly to count:
- Total `Speech` rows with non-null `speaker`
- Rows matching the validated structural-non-MP exclusion pattern
- Rows matching the validated section-header exclusion pattern
- Denominator = total − excluded

Record all counts in `docs/speech-speaker/progress.txt` under `## Setup — Target set`.

**Step 3 — Draw a stratified sample.**
Query `Speech` rows with non-null, non-excluded `speaker`, stratified by **both `report_type` and parliament era**. Era derivation: colonial = `parliament_number` ≤ 3 (roughly vol 1–35), mid-era = 4–11, modern = 12+. Draw K=5 pilot and K=3 held-out per `(report_type, era)` group where enough rows exist; collapse era strata if a type has too few rows across eras to fill both.

Three sets:

- **Pilot** (K=5 per group): used for diagnosis and inspection
- **Held-out** (K=3 per group): not inspected during diagnosis; used only in Loop Step 6 for validation. If a group has fewer than 4 speeches total, draw all into pilot and mark as having no held-out set.
- **Regression** (~30 total, from speeches that already resolve to a non-null `speaker_id` at baseline): checked after every fix to catch regressions. Maintain era balance: ≥5 colonial, ≥5 mid-era, ≥10 modern.

Write all three sets of Speech IDs to `docs/speech-speaker/sample.json`:
```json
{
  "pilot": [123, 456, ...],
  "held_out": [789, 101, ...],
  "regression": [202, 303, ...]
}
```

Do not re-sample in later iterations. The same IDs must be tracked throughout so before/after comparisons are valid.

Note: K=5 pilot sizes are too small for reliable coverage estimates of the full corpus. Early pass rates should be treated as directional, not precise — estimates stabilise as the sample is widened in later iterations.

**Step 4 — Record the baseline.**
Run `scripts/speech_speaker_match_rate.py` restricted to the pilot IDs. Record per-type match rates under `## Setup — Baseline` in `docs/speech-speaker/progress.txt`. This is the reference point for all iterations.

**Step 5 — Catalogue failure modes.**
Walk through every failing pilot speech and classify its root cause. Group by shared pattern — do not write one entry per speech. For each group record: the failure pattern, representative `speaker` strings, affected `report_type` and era, and estimated count in the pilot. Write the catalogue to `docs/speech-speaker/progress.txt` under `## Setup — Failure catalogue`. This catalogue is the direct input to Loop Step 2.

## Loop

The authoritative iteration count is the number of `## Iteration N` headings in `docs/speech-speaker/progress.txt`.

**Step 1 — Run the sample.**
Apply the current `_populate_speech_speaker_ids` logic to every Speech ID in the pilot, held-out, and regression sets. Record for each: `speech_id`, `report_type`, `speaker`, `parliament_number`, matched (`speaker_id` non-null) or not.

**Step 2 — Identify the highest-impact unresolved `can_match` failure.**
From the current failure catalogue (Setup Step 5, or the previous iteration's updated catalogue), pick the pattern affecting the most pilot speeches.

Before selecting a target, first **group all current failures by root cause** — look across all failing speeches of the same `(report_type, era)` and identify shared structural patterns. A fix written against a pattern covers all instances; a fix written against one speech may not generalise.

Priority order within the catalogue:
1. Pre-processing failures (constituency suffix, role+name extraction) — fix in `_populate_speech_speaker_ids` before calling `resolve_canonical_name`
2. Cascade misses for known MPs — add to `_MANUAL_OVERRIDES` in `services/attendance.py`
3. Structural exclusions — add to the exclusion list in `_populate_speech_speaker_ids`

**Step 3 — Investigate.**
Open 2–3 failing Speech rows exhibiting the target pattern. Note the exact `speaker` string, the `parliament_number`, and the expected `Speaker.name`. Also open 1–2 **passing** Speech rows from the **same `report_type` and era** — understanding what a passing case looks like is required to write a correct fix without regressing it.

**Step 4 — Log findings.**
Append to `docs/speech-speaker/progress.txt` under a `## Iteration N — YYYY-MM-DD` heading:

```
## Iteration N — YYYY-MM-DD

### can_match — <report_type> — <short description of root cause>

**Affected Speech IDs (pilot):**
<list>

**Speaker string (failing):**
<exact string from Speech.speaker>

**Speaker string (passing, same report_type):**
<a passing example for contrast>

**Expected Speaker.name:**
<canonical form from Mp table>

**Root cause:**
<what the current logic does wrong>

**Proposed fix:**
<the code change in populate/speaker_links.py or services/attendance.py>

**Backward-compatibility:**
<which currently-passing speeches could be affected and why they won't be>

**Outcome:** (filled in after Step 5)
<kept / reverted — net change on pilot, held-out, regression>
```

If the finding reveals a generalizable pattern, also record it in `docs/speech-speaker/matching-patterns.md`.

**Step 5 — Apply one fix.**
Modify `populate/speaker_links.py` only (or `services/attendance.py` for `_MANUAL_OVERRIDES`). One fix per iteration — do not batch multiple changes even if several are ready.

Prefer a **pre-processing step before calling `resolve_canonical_name`** over modifying the cascade itself. State your backward-compatibility reasoning before applying.

**Step 6 — Validate.**
Re-run the matching logic across all three sets. Print a table:

```
can_match        | report_type          | Before | After
-----------------|----------------------|--------|------
constituency     | oral-answer          |  3/5   |  5/5
role+name        | ministerial-statement|  2/5   |  4/5
---
Held-out improvement: N sittings flipped
Regression set failures: 0/30
Secondary metric (incl. excluded): X/total
```

Decision rule:
- **Keep** if: matched count in pilot increased AND regression set shows no new failures AND held-out set shows improvement (≥2 speeches flipped, or >50% of the held-out group if fewer than 4)
- **Revert** if: regression failures appear, or the held-out bar was not met. Log the reason.

**Step 7 — Widen the sample (every 3 iterations).**
After every third iteration, add more speeches to the sample from `report_type` groups that are underrepresented or have newly-surfaced failure patterns. K=5 pilot and K=3 held-out still apply to new groups. Draw a fresh held-out set for new groups only. Expand the regression set proportionally to maintain coverage.

**Step 8 — Check completion.**
Compute `matched / denominator` across the pilot. If ≥95%, stop and report success. If all remaining failures are permanently unresolvable (role-only strings, MPs genuinely absent from the `Speaker` table), also stop — record the ceiling and the reason. Do not iterate against unresolvable cases.

If this is iteration 10 (or a multiple of 10), stop regardless and go to Step 9.

Otherwise continue to Step 1.

**Step 9 — Ask for approval to continue.**
Present:
- Current `matched / denominator` vs. 95% target, and vs. baseline
- Progress table across all `report_type` groups (before/after counts for each)
- Marginal gain this iteration (speeches newly matched)
- Resolved failure patterns (with before/after counts)
- Remaining unresolved patterns and estimated counts
- Any patterns that appear permanently unresolvable (role-only, missing `Mp` data)
- Secondary metric: `matched / total non-null-speaker speeches`

Ask: "Should I continue iterating?"

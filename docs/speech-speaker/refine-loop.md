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
2. **Speeches where `speaker` is None**: already excluded.

Two failure stages:

- **`can_extract`**: `speaker` is non-null but does not look like a name. Diagnostic heuristic — looks like a name: mixed case, 1–4 words, optional title prefix, optional constituency parenthetical. Does not look like a name: all-caps with no lowercase, sentence-length text, starts with a numeral, contains a colon mid-string. Fix location: `services/speech.py`. After applying a fix, repopulate Speech rows for affected reports, then re-run `_populate_speech_speaker_ids`, then measure.
- **`can_match`**: `speaker` looks like a name, is not a structural non-MP, and `speaker_id` remains null after `_populate_speech_speaker_ids` runs. Fix location: `populate/speaker_links.py` (or `services/attendance.py` for `_MANUAL_OVERRIDES`).

"Matched" means `Speech.speaker_id` is non-null. Track the match rate as `matched / denominator`.

**Note on baseline**: Section headers were previously excluded from the denominator. They are now `can_extract` failures and remain in the denominator. Recompute the denominator and baseline before starting the first iteration under this definition.

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
| Section header | `PART I INTRODUCTION` | `can_extract` — fix in `services/speech.py` |

## Where fixes go

| Failure stage | Fix location | Notes |
|---|---|---|
| `can_extract` | `services/speech.py` (`_parse_speeches`) | Prevents junk strings from being written to `Speech.speaker`; requires repopulating Speech rows after fix |
| `can_match` | `populate/speaker_links.py` (`_populate_speech_speaker_ids`) | Add pre-processing before calling `resolve_canonical_name`; do not modify the cascade itself |
| `can_match` (known MPs) | `services/attendance.py` (`_MANUAL_OVERRIDES`) | For names the cascade cannot reach |

Do not compensate for extraction failures in `speaker_links.py` — fix at the source.

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
- Section headers (×5 total) → `can_extract` failure, fix in `services/speech.py`

**Known failure categories ranked by estimated global impact:**
1. Constituency suffix in speaker string — affects most eras, all report types (`can_match`)
2. Role+name pattern (`The X (Name)`) — common in older parliamentary records (`can_match`)
3. Structural non-MPs (`Mr Speaker`, `Hon. Members`) — exclude from denominator
4. Section headers misidentified as speakers — `can_extract`, fix in `services/speech.py`
5. Short names / parliament scoping for known MPs (`can_match`)

**Note**: The baseline above was computed under the old denominator (section headers excluded). Recompute before starting iterations.

---

# Method

**The setup is not bookkeeping.** Its outputs determine whether the goal as written is correct before any iteration begins. Do not start iterating against a wrong target.

## Setup

**Step 1 — Validate the exclusion definitions.**
Before counting the denominator, verify empirically that the exclusion category is correctly defined. Inspect 5–10 candidate excluded strings drawn from the actual DB:

- *Structural non-MPs*: query for `speaker` values matching known exclusion strings (`Mr Speaker`, `Mr Deputy Speaker`, `Hon. Members`, etc.) and read the surrounding transcript for a sample of matches. Confirm none are genuine MPs whose name happens to start with a presiding-officer prefix.

Also validate the `can_extract` boundary: query for all-caps `speaker` values and inspect a sample. Confirm that no colonial-era speaker names are misclassified — all-caps formatting was common in old transcripts and some genuine MPs may appear in all-caps. Record which patterns are confirmed `can_extract` failures vs. which need manual review.

If an exclusion pattern is too broad or too narrow, revise before proceeding. Record findings in `docs/speech-speaker/progress.txt` under `## Setup — Exclusion validation`. If the definition needs changing, revise the Goal section of this document too.

**Step 2 — Establish the target set denominator.**
Query the DB directly to count:
- Total `Speech` rows with non-null `speaker`
- Rows matching the validated structural-non-MP exclusion pattern
- Rows matching the `can_extract` pattern (all-caps section headers; these remain in the denominator as a fixable failure)
- Denominator = total − structural-non-MP exclusions

Also record: `can_extract` count and `can_match` count (denominator − `can_extract`). These are the two pools of fixable failures.

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
Walk through every failing pilot speech and classify its root cause into one of two stages:

- **`can_extract`**: `speaker` does not look like a name (use the heuristic in the Goal section). Record the exact string, which bold line in the markdown produced it, and what `_parse_speeches` did wrong.
- **`can_match`**: `speaker` looks like a name but `speaker_id` is null. Record the exact string, the expected `Speaker.name`, and why the cascade missed it.

Group by shared pattern — do not write one entry per speech. For each group record: the failure stage, the failure pattern, representative `speaker` strings, affected `report_type` and era, and estimated count in the pilot. Write the catalogue to `docs/speech-speaker/progress.txt` under `## Setup — Failure catalogue`. This catalogue is the direct input to Loop Step 2.

## Loop

The authoritative iteration count is the number of `## Iteration N` headings in `docs/speech-speaker/progress.txt`.

**Step 1 — Run the sample.**
Apply the current `_populate_speech_speaker_ids` logic to every Speech ID in the pilot, held-out, and regression sets. Record for each: `speech_id`, `report_type`, `speaker`, `parliament_number`, matched (`speaker_id` non-null) or not.

**Step 2 — Identify the highest-impact unresolved failure.**
From the current failure catalogue (Setup Step 5, or the previous iteration's updated catalogue), pick the pattern affecting the most pilot speeches.

Before selecting a target, first **group all current failures by root cause** — look across all failing speeches of the same `(report_type, era)` and identify shared structural patterns. A fix written against a pattern covers all instances; a fix written against one speech may not generalise.

Priority order within the catalogue:
0. **`can_extract` failures** — fix first, in `services/speech.py`. The resolution cascade cannot compensate for a wrong input value. After applying the fix, repopulate Speech rows for affected reports, then re-run `_populate_speech_speaker_ids`, then measure (see Step 6).
1. `can_match`: Pre-processing failures (constituency suffix, role+name extraction) — fix in `_populate_speech_speaker_ids` before calling `resolve_canonical_name`
2. `can_match`: Cascade misses for known MPs — add to `_MANUAL_OVERRIDES` in `services/attendance.py`
3. `can_match`: Structural exclusions — add to the exclusion list in `_populate_speech_speaker_ids`

**Step 3 — Investigate.**
Open 2–3 failing Speech rows exhibiting the target pattern. Note the exact `speaker` string, the `parliament_number`, and the expected `Speaker.name`. Also open 1–2 **passing** Speech rows from the **same `report_type` and era** — understanding what a passing case looks like is required to write a correct fix without regressing it.

**Step 4 — Log findings.**
Append to `docs/speech-speaker/progress.txt` under a `## Iteration N — YYYY-MM-DD` heading. Use the appropriate template for the failure stage.

**For `can_extract` failures:**
```
## Iteration N — YYYY-MM-DD

### can_extract — <report_type> — <short description of root cause>

**Affected Speech IDs (pilot):**
<list>

**Speaker string (bad extraction):**
<exact string from Speech.speaker>

**Source bold line in markdown:**
<the line in Report.markdown_content that produced it>

**Root cause:**
<what _parse_speeches did wrong>

**Proposed fix:**
<the code change in services/speech.py>

**Backward-compatibility:**
<which currently-passing speeches could be affected and why they won't be>

**Outcome:** (filled in after Step 5)
<kept / reverted — net change on pilot after repopulate + re-run speaker_links>
```

**For `can_match` failures:**
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
<canonical form from Speaker table>

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
One fix per iteration — do not batch multiple changes even if several are ready.

- For `can_extract` failures: modify `services/speech.py` (`_parse_speeches`). After applying, repopulate Speech rows for affected reports by re-running the speeches pipeline stage, then proceed to Step 6.
- For `can_match` failures: modify `populate/speaker_links.py` (or `services/attendance.py` for `_MANUAL_OVERRIDES`). Prefer a **pre-processing step before calling `resolve_canonical_name`** over modifying the cascade itself.

In both cases, state backward-compatibility reasoning before applying.

**Step 6 — Validate.**
For `can_extract` fixes: repopulate Speech rows for affected reports, then re-run `_populate_speech_speaker_ids`, then check `speaker_id`.
For `can_match` fixes: re-run `_populate_speech_speaker_ids` only.

Run across all three sets. Print a table:

```
stage        | report_type          | Before | After
-------------|----------------------|--------|------
can_extract  | budget               |  3/5   |  5/5
can_match    | oral-answer          |  3/5   |  5/5
---
Held-out improvement: N speeches flipped
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

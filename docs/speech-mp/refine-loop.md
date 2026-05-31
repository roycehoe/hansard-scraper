# Environment Note

All Python scripts in this project must be run via `poetry run python3` (not bare `python3`), with `PYTHONPATH` set to the project root:

```
PYTHONPATH=/path/to/handsard-scraper poetry run python3 scripts/speech_speaker_match_rate.py
```

The project uses a remote PostgreSQL database; `DATABASE_URL` is loaded from `.env` automatically.

---

# Before Starting — Resume Check

Before beginning Setup or any loop iteration, load existing artifacts:

- `docs/speech-mp/progress.txt` — iteration log; read it to determine which iteration the loop is on.
- `docs/speech-mp/matching-patterns.md` — accumulated knowledge about speaker string formats and failure modes; read before investigating any failures.

**Do not regenerate these files if they already exist.** If artifacts are present, skip Setup and resume from the last incomplete step in `progress.txt`.

---

# Goal

Improve `_populate_speech_mp_ids` in `populate/mp_links.py` so that ≥95% of Speech rows in the matchable target set receive a non-null `mp_id`.

**Target set definition** — exclude from the denominator:
1. **Structural non-MPs**: `Mr Speaker`, `Mr Deputy Speaker`, `The Clerk`, `Hon. Members`, and similar presiding officers or collective references. These are never in the `Mp` table by design.
2. **Section headers misidentified as speakers**: all-caps strings with no name structure (e.g. `LIQUEFIED PETROLEUM GAS (Conditions of a Licence)`, `PART I INTRODUCTION`). These are speech parsing failures — do not fix them here.
3. **Speeches where `speaker` is None**: already excluded.

"Matched" means `Speech.mp_id` is non-null after `_populate_speech_mp_ids` runs. Track the match rate as `matched / (total − excluded)`.

**Secondary metric**: also track total matched / total non-null-speaker speeches (including excluded) to make the exclusion count visible.

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

All matching logic lives in `_populate_speech_mp_ids` in `populate/mp_links.py`. The helper `resolve_canonical_name` (in `services/sitting_attendance.py`) handles the existing cascade and should not be modified here — add pre-processing steps before calling it.

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

## Setup

**Step 1 — Validate the target set.**
Run `scripts/speech_speaker_match_rate.py` against the full corpus (not just the sample) to count:
- Total Speech rows with non-null speaker
- Rows matching the structural-non-MP exclusion pattern
- Rows matching the section-header exclusion pattern
- Denominator (total − excluded)

Record counts in `docs/speech-mp/progress.txt` under `## Setup`.

**Step 2 — Draw a stratified sample.**
Draw from Speech rows with non-null speaker, stratified by report_type. Within each type:
- **Pilot** (K=5 per type): used for diagnosis and inspection
- **Held-out** (K=3 per type): not inspected during diagnosis; used only in validation
- **Regression** (~30 total, from speeches that already match at baseline): checked after every fix

Write all three sets of Speech IDs to `docs/speech-mp/sample.json`. Do not re-sample in later iterations.

## Loop

**Step 1 — Identify the highest-impact unresolved failure pattern.**
From the current failure catalogue, pick the pattern affecting the most sample speeches.

Priority order:
1. Pre-processing failures (constituency suffix, role+name extraction) — fix in `_populate_speech_mp_ids` before calling `resolve_canonical_name`
2. Cascade misses for known MPs — add to `_MANUAL_OVERRIDES` in `services/sitting_attendance.py`
3. Structural exclusions — add to the exclusion list in `_populate_speech_mp_ids`

**Step 2 — Investigate.**
Inspect 2–3 failing Speech rows exhibiting the pattern. Note the exact `speaker` string, the `parliament_number`, and what `Mp.name` should be. Compare against 1–2 passing rows of the same report_type.

**Step 3 — Log findings.**
Append to `docs/speech-mp/progress.txt`:

```
## Iteration N — YYYY-MM-DD

### <pattern> — <short description>

**Affected Speech IDs (pilot sample):**
<list>

**Speaker string (failing):**
<exact string>

**Expected Mp.name:**
<canonical form>

**Root cause:**
<what the current logic does wrong>

**Proposed fix:**
<the code change in populate/mp_links.py or services/sitting_attendance.py>

**Backward-compatibility:**
<why currently-passing speeches are unaffected>

**Outcome:** (filled in after Step 5)
```

If the finding reveals a generalizable pattern, also record it in `docs/speech-mp/matching-patterns.md`.

**Step 4 — Apply one fix.**
Modify `populate/mp_links.py` only (or `services/sitting_attendance.py` for `_MANUAL_OVERRIDES`). One fix per iteration.

**Step 5 — Validate.**
Re-run `scripts/speech_speaker_match_rate.py`. Record before/after for pilot, held-out, and regression sets.

Decision rule:
- **Keep** if: matched count increased AND regression set shows no new failures AND held-out set shows improvement
- **Revert** if: regression failures appear, or neither pilot nor held-out improved

**Step 6 — Check completion.**
Compute `matched / denominator` across the full pilot sample. If ≥95%, stop and report success. If all remaining failures are in the unresolvable categories (role-only, MPs not in the `Mp` table, genuine data gaps), also stop — record the ceiling. Do not iterate against permanently unresolvable cases.

Otherwise continue.

At iteration 10 (or multiples of 10), stop and ask for approval to continue.

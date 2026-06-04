# Progress Report Prompt — All Refine Loops

Paste this prompt into Claude along with the files listed in each section. The output is a cross-loop progress report covering all five refine loops in this project.

---

## Prompt

You are reviewing the refine-loop logs for a Singapore Parliament Hansard scraper. There are five refine loops, each improving a different pipeline stage. Read the files listed below and produce a structured progress report.

### Files to read

**Loop 1 — speech-speaker** (Speech → Speaker ID resolution):
- `docs/speech-speaker/refine-loop.md`
- `docs/speech-speaker/progress.txt`
- `docs/speech-speaker/matching-patterns.md`
- `docs/speech-speaker/learnings.txt`

**Loop 2 — attendance-speaker** (Attendance row → Speaker ID resolution):
- `docs/attendance-speaker/refine-loop.md`
- `docs/attendance-speaker/progress.txt`

**Loop 3 — attendance** (Sitting markdown → Attendance name extraction and matching):
- `docs/attendance/refine-loop.md`
- `docs/attendance/progress.txt`

**Loop 4 — sitting** (Sitting HTML → clean markdown):
- `docs/sitting/refine-loop.md`
- `docs/sitting/progress.txt`

**Loop 5 — report** (Report HTML → speeches parsed and attributed):
- `docs/report/refine-loop.md`
- `docs/report/progress.txt`
- `docs/report/learnings.md`

---

### Report format

Produce exactly these five sections:

---

## 1. Executive Summary

One row per loop. Columns: Loop name | Goal | Metric at baseline | Metric now | Target | Status.

Status values:
- **COMPLETE** — target met, loop closed
- **CEILING** — target not met but no fixable failures remain; blocked on data or source quality
- **ACTIVE** — target not yet met and fixable failures remain

---

## 2. Iteration Log (per loop)

For each loop, produce a table. Columns: Iteration | Date | Stage | Description | Outcome | Before → After | Net gain.

- Stage: `can_extract` (parsing wrong input), `can_match` (resolution failure), `data` (DB population), `artifact` (markdown cleaning), or `N/A` for setup/ceiling entries.
- Outcome: **KEPT**, **REVERTED**, **CEILING**, or **COMPLETE**.
- Before → After: the primary metric for that loop (match rate %, or artifact count, etc.) — whatever the loop tracks. Use the numbers from the progress files exactly.
- Net gain: absolute improvement (e.g. "+26 speeches", "−2,359 failures", "+22/30 pilot").

Flag REVERTED rows so they are easy to scan.

If a loop has multiple criteria phases (e.g. the report loop ran `has_start_line` then `speaker/transcript quality` then `speech quality`), separate them with a sub-heading inside the loop's table.

---

## 3. Remaining Gap Analysis

For each loop that is not COMPLETE, list every unresolved failure category. For each category:

- **Pattern**: what the bad input looks like (exact strings or description)
- **Stage**: `can_extract` | `can_match` | `data gap` | `permanently unresolvable`
- **Estimated count**: from the progress files (corpus-wide if stated, pilot if not)
- **Fix location**: where the fix would go (file + function), or why no fix is possible
- **Evidence**: cite the specific iteration or setup entry in the progress file that identified this category

If a loop has declared a ceiling, state the ceiling metric and the reason it cannot be improved further.

---

## 4. Prioritised Next Actions

Across all loops, list every remaining fixable action ranked by estimated impact (rows/speeches that would newly resolve).

Format each action as:

> **[Loop] [Action type]** — `<what to do>` — estimated +N matches — fix in `<file>:<function>`

Action types: `code fix`, `data load`, `exclusion update`, `architecture change`.

After the fixable actions, list permanently unresolvable gaps separately under a **"Known ceiling — no fix possible"** heading. For each: what it is, how many rows it affects, and why it is unresolvable.

---

## 5. Learnings and Patterns

Synthesise the key non-obvious findings from `docs/speech-speaker/learnings.txt` and `docs/report/learnings.md` into three groups:

**OCR error patterns** — character substitutions and scan artifacts that recur across colonial-era records. List each pattern with the OCR form → canonical form and the fix location.

**Architectural decisions** — choices made during the loops that constrain or guide future work. For example: which dicts are parliament-scoped vs. parliament-agnostic, which scripts are too slow for inline synthesis steps, which exclusions are structural vs. fixable.

**Workflow rules** — lessons about how to run these loops efficiently: agent sizing, DB pre-check order, sample stability, verification approach.

---

### Notes for the report writer

- Treat each `progress.txt` as authoritative. If a metric in the progress file differs from the refine-loop.md baseline, use the progress file value and note the discrepancy.
- When an iteration was REVERTED and immediately re-attempted in the next iteration (e.g. iter 16 first attempt / iter 16 corrected), merge them into one row with outcome "REVERTED then KEPT (corrected)" and the final net gain.
- Do not invent numbers. If a count is not stated in the source files, write "not recorded" rather than estimating.
- The report should be scannable: a reader unfamiliar with the codebase should be able to tell which loops are done, which are active, and what the single highest-impact next action is within 30 seconds of reading the executive summary.

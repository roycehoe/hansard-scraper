# Before Starting — Resume Check

Before beginning Setup or any loop iteration, scan the working directory for existing artifacts and load them:

- `docs/sitting/sample.json` — the fixed strata drawn at Setup Step 1; if present, use it as-is.
- `docs/sitting/progress.txt` — iteration log; if present, read it to determine which iteration the loop is on and what was last attempted.
- `docs/sitting/formatting-patterns.md` — accumulated knowledge about formatting artifacts in sitting HTML; if present, read it before investigating any failures.

**Do not regenerate any of the above files if they already exist.** If all artifacts are present, skip Setup and resume from the last incomplete step recorded in `docs/sitting/progress.txt`.

# Goal

Produce a `get_cleaned_sitting_markdown` function that converts `html_full_content` from `HansardSittingDateResponse` into clean, artifact-free markdown — with no formatting anomalies visible in the output.

Success: ≥95% of documents in the strata sample are fully artifact-free (no formatting anomalies visible in any output field), as tracked in `docs/sitting/progress.txt`. Artifact categories are tracked per-type so you can see whether remaining failures are widespread or isolated — do not grind on categories that affect only 1–2 documents once the per-doc rate is ≥95%.

# Method

Iteratively refine a branched markdown-cleaning function until all identified artifact categories are resolved.

## Setup

**Step 1 — Draw a stratified sample.**
Query the DB for `HansardSittingDateResponse` rows where `html_full_content is not None`. Stratify by `report_type` (or the closest available field), drawing three sets:

- **Pilot** (up to K=5 per group): used for diagnosis and inspection.
- **Held-out** (up to K=3 per group): not inspected during diagnosis; used only in Loop Step 5 to validate that fixes generalise. If a group has fewer than 4 documents total, draw all into the pilot and mark the group as having no held-out set — skip held-out validation for it in Loop Step 5.
- **Regression** (~15–20 documents total, drawn from rows that already produce clean output): checked after every fix to catch breakage in previously-clean documents.

Write all three sets to `docs/sitting/sample.json`:

```json
{
  "pilot": [123, 456, ...],
  "held_out": [789, 101, ...],
  "regression": [202, 303, ...]
}
```

Do not re-sample in later iterations. The sample is fixed for the duration of the loop so before/after comparisons remain valid.

**Step 2 — Run `get_cleaned_hansard_markdown` on the sample.**
For each row in the sample, call `get_cleaned_hansard_markdown(row.html_full_content)` and collect the outputs in memory. Do not write these to the DB at this stage — this is a diagnostic run only.

**Step 3 — Inspect for odd formatting.**
Read through the markdown outputs and catalogue every anomaly you observe. Common things to look for:

- Unreplaced HTML entities or tags leaking through
- Column/page marker patterns not caught by existing regexes
- Broken bold merges (e.g. bold lines that should have merged but didn't, or merged incorrectly)
- Encoding artifacts (mojibake, escaped characters)
- Table structure rendered as garbage
- Unusual whitespace, blank-line runs, or stray punctuation
- Any pattern that looks structurally different from the report `markdown_content` output

Before cataloguing, check whether any observed anomaly might be **correct rendering** for a specific `report_type` — i.e. is "zero anomalies" actually the right output for some document types? If so, exclude those types from the artifact target list and note the exclusion. Iterating to fix output that is correct for its document type is wasted work.

Write each distinct artifact type to `docs/sitting/progress.txt` under `## Setup — Artifact catalogue`. If **no anomalies** are found, stop here and record that `get_cleaned_hansard_markdown` is sufficient as-is; no branch is needed.

**Step 4 — Create the branched function.**
If anomalies were found: in `utils/markdown_parser.py`, rename `get_cleaned_hansard_markdown` to `get_cleaned_report_markdown` and update its one call site in `services/report.py`. Then create `get_cleaned_sitting_markdown` as a copy of the original. Update `services/sitting.py` to call `get_cleaned_sitting_markdown`. All future refinement work touches only `get_cleaned_sitting_markdown`.

**Step 5 — Record the baseline.**
For each artifact category from Step 3, count how many sample documents exhibit it. Write to `docs/sitting/progress.txt` under `## Setup — Baseline`. This is the reference point for the loop.

## Loop

The authoritative iteration count is the number of `## Iteration N` headings in `docs/sitting/progress.txt`. The multiple-of-10 checkpoint in Step 6 counts these headings.

**Step 1 — Identify the highest-frequency unresolved artifact.**
From the current catalogue in `docs/sitting/progress.txt`, pick the artifact type affecting the most sample documents. This is the target for this iteration.

**Step 2 — Investigate.**
Open the raw `html_full_content` for 2–3 documents exhibiting the artifact. Compare the HTML structure against 1–2 documents where it is absent. Determine the root cause: is this an HTML input quirk, a gap in a stripping regex, an html2text rendering issue, or a post-processing step that doesn't apply to sitting documents?

**Step 3 — Log findings.**
Append to `docs/sitting/progress.txt` under a `## Iteration N — YYYY-MM-DD` heading:

```
## Iteration N — YYYY-MM-DD

### Artifact: <short name>

**Affected IDs:**
<list>

**HTML snippet (exhibiting artifact):**
<representative HTML lines>

**Markdown output (before fix):**
<the bad output>

**Root cause:**
<what causes it>

**Proposed fix:**
<the regex or logic change>

**Outcome:** (filled in after Step 5)
<kept / reverted — net change>
```

If the finding reveals a generalizable pattern about sitting HTML structure, also record it in `docs/sitting/formatting-patterns.md`.

**Step 4 — Apply one fix.**
Modify `get_cleaned_sitting_markdown` only. Do not touch `get_cleaned_report_markdown`. Apply one fix per iteration.

Prefer a **condition-gated branch** over modifying shared logic. If a fix only applies to a specific `report_type` or structural pattern, gate it with a condition rather than changing the default path — this limits regression blast radius by leaving the general path untouched. A new private helper (e.g. `_remove_sitting_specific_artifact`) is the usual shape for this. Before applying, state which currently-clean documents could be affected and why they won't be.

**Step 5 — Validate.**
Re-run `get_cleaned_sitting_markdown` across the full sample. For each artifact category, recount occurrences. Print a table:

```
Artifact                    | Before | After
----------------------------|--------|------
unreplaced entity           |   8    |   0
bad bold merge              |   3    |   3  (no change)
stray column marker variant |   5    |   2
---
Clean docs (no artifacts)   | 10/20  | 15/20  (75%)
```

The table must cover all three sets. Decision rule:

- **Keep** if: the target artifact count decreased AND the regression set shows no new artifacts AND (where a held-out set exists) the held-out set shows improvement.
- **Revert** if: new artifacts appeared, the count did not decrease, or the regression set shows any previously-clean document now producing artifacts. Log the reason in `docs/sitting/progress.txt`.

**Step 6 — Widen the sample (every 3 iterations).**
After every third iteration (check the number of `## Iteration N` headings in `docs/sitting/progress.txt`), add more documents to the sample from era groups that are underrepresented or not yet in the pilot. K=5 per group still applies to new groups. Draw a fresh held-out set for new groups only. Expand the regression set proportionally, maintaining the era distribution floor (≥5 colonial, ≥3 mid-era, ≥3 modern).

**Step 7 — Check completion.**
Count the fraction of sample documents that are fully artifact-free. If ≥95% are clean, stop and report success. If all remaining artifact categories affect only 1–2 documents each and the per-doc rate is already ≥95%, also stop — do not grind on rare edge cases. Otherwise, go to Step 1.

If this is iteration 10 (or a multiple of 10), stop regardless and go to Step 8.

**Step 8 — Ask for approval to continue.**
Present:
- Current clean-doc rate vs. 95% target
- Resolved artifact categories (with counts at baseline vs. now)
- Remaining unresolved categories and their current counts, and how many documents each affects
- Any artifacts that appear unfixable without changing html2text configuration

Ask: "Should I continue iterating?"

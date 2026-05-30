# Goal

Target Dataset: All Report rows where `markdown_content` is not None, restricted to report types validated as speech-bearing (determined during setup).

Success: ≥95% of reports in the validated speech-bearing set yield at least one speech.

# Method

Iteratively refine the speech parsing logic until the success threshold is met.

## Setup (discovery phase — output may restructure the goal)

The setup is not bookkeeping. Its outputs determine whether the goal as written is correct before any iteration begins.

**Step 1 — Identify no-speech report types.**
Query the DB for `report_type` values where no document has ever yielded speeches. Exclude these from the sampling pool. Log the excluded types.

**Step 2 — Validate "zero speech" cases empirically.**
Manually inspect 5–10 reports with `markdown_content` that currently yield zero speeches, drawn across different `report_type` values. For each, determine: is this a parsing failure, or is zero speeches the correct result for this document type?

If this inspection reveals that zero speeches is correct behaviour for a significant portion of the dataset, rewrite the goal and success criterion before proceeding to the loop. Do not start iterating against a wrong target.

**Step 3 — Add `report_type` to parsing function signatures.**
`get_start_of_speech_line` currently takes `(markdown_content, title, subtitle, original_title)` — it does not receive `report_type`. Before any condition-gated patch can work, update the signature to include `report_type` and update all call sites in `script.py` (`_get_statistics`, `parse_speeches`). This is a prerequisite for the entire iterative loop.

**Step 4 — Record the baseline.**
Run parsing against the full validated set (excluding no-speech types from step 1) and record the starting success rate. This is the reference point for all future progress and the denominator for the 95% target.

**Step 5 — Draw the pilot sample.**
Sample from failing documents, grouped by `(failure_stage, report_type)`, up to K=3 per group. Exclude `has_markdown=False` rows.

Also draw a **held-out improvement set**: K=3 additional failing documents per group, not shown during diagnosis, used only for post-patch validation.

Also draw a **passing-document regression set**: a sample of ~30 currently-passing documents across report types, used to detect regressions after each patch.

Note: K=3 diagnosis samples is a pilot size. Coverage estimates from this sample are unreliable until the sample is widened in later iterations.

Failure stages, in triage order:
- `has_start_line=False` — blocked from all downstream parsing (highest priority)
- `can_get_speeches=False` — start line found but segmentation broke

## Loop

**Step 1 — Parse the sample**
Run speech parsing on the current sample. For each report, record:
- `report_id`
- `report_type`
- `failure_stage` (`has_start_line` or `can_get_speeches`)

**Step 2 — Investigate and group failures**
Work through failures in triage order (`has_start_line=False` first).

Before investigating individual documents, group the failures by apparent root cause — look across all failing documents of the same `(failure_stage, report_type)` and identify shared structural patterns. A fix written against a pattern covers all instances; a fix written against one document may not.

For each root-cause group:
- Open the raw markdown of representative failing documents.
- Open 1–2 currently-passing documents from the **same `report_type`**. Understanding what the passing case looks like is required for writing a correct conditional branch.
- Determine why parsing fails for this group. Do not assume the current parsing approach is correct — if a fundamentally different strategy would work better, note it.

**Step 3 — Log findings**
Append one entry per root-cause group (not per document) to `progress.txt`. If the investigation reveals a generalizable structural pattern about the markdown format or a `report_type`'s document shape, also record it in `parsing-patterns.md` (reusable knowledge, not iteration-specific). Use this structure:

```
## <failure_stage> — <report_type> — <short description of root cause>

**Affected report IDs:**
<list of IDs sharing this root cause>

**Markdown snippet (failing):**
<representative lines from a failing document>

**Markdown snippet (passing, same report_type):**
<comparable lines from a passing document of the same type>

**Why it fails:**
<what the current logic does wrong for this group>

**Proposed fix / approach:**
<the pattern or logic change that would handle this group>

**Outcome:** (filled in after Step 5–6)
<kept / reverted — net change on held-out set, regression count>
```

**Step 4 — Modify the parsing logic**
Apply one fix per iteration — the single change with the highest coverage across root-cause groups. Do not apply multiple fixes in one iteration even if several are ready; validate one before attempting the next.

When proposing a fix:
- **Prefer adding a condition-gated branch** over modifying the general-case logic. If a fix only applies to a subset of documents (e.g. a specific `report_type`, a title pattern, a structural signal in the markdown), gate it with a condition rather than changing the default path. This limits regression risk almost by construction.
- When branching on `report_type`, compare against the **string value**, not the enum (e.g. `report_type == "oral-answer"`, not `report_type == ReportType.ORAL_ANSWER`), since `report_type` is stored as a plain string in the DB models.
- State your backward-compatibility reasoning: which currently-passing documents could be affected and why they won't be.
- You are not required to preserve any existing function — rewrite freely if a better approach exists.

**Step 5 — Validate the patch**
Run `_get_statistics` on three sets:

1. **Held-out improvement set** — failing documents not shown during diagnosis, from the same `(failure_stage, report_type)` groups. The patch must produce a net improvement here (more documents passing than before) to be accepted. A single document improving is not sufficient.
2. **Full diagnosis sample** — the Step 1 documents, to measure net change on the training set.
3. **Passing-document regression set** — the ~30 passing documents drawn at setup. Any regression here (a previously-passing document now failing) is a signal to investigate before accepting.

**Step 6 — Evaluate the change**
Compare results before and after. Print a progress table:

```
Stage            | report_type        | Before | After
has_start_line   | oral-answer        | 4/7    | 6/7
can_get_speeches | ministerial-stmt   | 2/3    | 2/3  (no change)
---
Passing set regressions: 0/30
```

- If **new passes > new failures** and **no regressions in the passing set**: keep the change. Log the net outcome to `progress.txt`.
- If **new failures ≥ new passes** or **regressions detected**: revert the change. Log why it regressed and what to try instead in `progress.txt`.

**Step 7 — Widen the sample (every 3 iterations)**
Add more documents to the sample from `(failure_stage, report_type)` groups that are underrepresented or not yet in the pilot. K=3 per group still applies to new groups. Draw a fresh held-out set for the new groups. Expand the passing-document regression set proportionally.

**Step 8 — Check completion and iteration budget**
After updating stats, check two conditions:

- If the full validated set is at ≥95% success rate, stop and report success. Do not continue iterating.
- If this is iteration 10 (or a multiple of 10), stop and go to Step 9 regardless of current rate. This is a mandatory review checkpoint to prevent runaway loops with diminishing returns.

Otherwise, go to Step 1.

**Step 9 — Ask for approval to continue**
After completing a full pass (all current failures investigated and either fixed or logged as blocked), or hitting the iteration budget, present:
- Current success rate vs. the 95% target and vs. baseline
- The progress table across all `(failure_stage, report_type)` groups
- Marginal gain this iteration (how many new passes were added)
- Any root-cause groups that seem hard to fix

Ask: "Should I continue iterating?"

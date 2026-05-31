# refine-loop-multi-thread.md

Parallel version of `refine-loop.md`. Instead of one Claude instance driving the loop manually, each iteration fans out two investigation agents — one per failure stage — using Claude Code's Workflow tool. Coordination happens inside the workflow script; the two agents communicate through the orchestrator, not through files or human relay.

## How it works

| Phase | Agents | Parallelism |
|---|---|---|
| Resume | 1 | — |
| Investigate | 2 (A + B) | parallel |
| Synthesize | 1 | — |
| Patch | 1 | — (serialized) |
| Validate | 2 (held-out + regression) | parallel |
| Evaluate | 1 | — |

**Agent A** owns `has_start_line=False` failures.
**Agent B** owns `can_get_speeches=False` failures.

The orchestrator collects both agents' structured findings, picks the single highest-coverage fix, applies it, validates in parallel, then keeps or reverts.

## Prerequisites

Run `refine-loop.md` Setup Steps 1–5 first. The workflow assumes these artifacts exist:

- `sample.json` — pilot, held_out, and regression report ID sets
- `diagnose.py` — runs `_get_statistics` on a list of report IDs
- `inspect_failures.py` — opens raw markdown for a report ID
- `docs/report/progress.txt` — iteration log (may be empty on first run)
- `docs/report/parsing-patterns.md` — accumulated structural knowledge (may be empty on first run)

Do not start the workflow without `sample.json`. Re-sampling mid-run invalidates before/after comparisons.

## Before Invoking

Check these conditions before each invocation. The workflow script does not enforce them.

1. **Sample exists.** `sample.json` must be present. If absent, run `refine-loop.md` Setup Steps 1–5 first.
2. **Sample widening.** Count the `## Iteration N` headings in `docs/report/progress.txt`. If the count is a multiple of 3 (i.e. 3, 6, 9, …), run `refine-loop.md` Loop Step 7 manually to widen the pilot sample before invoking. Update `sample.json` with the new IDs, then invoke.
3. **10-iteration checkpoint.** If the count is 10 (or a multiple of 10), review the current full-corpus success rate against the 95% target before continuing. If the rate is plateaued and marginal gain per iteration is small, consider stopping rather than invoking again.

---

## Invoking the workflow

Save the script below to `.claude/workflows/refine-loop-multi.js`. Then in a Claude Code session:

```
Run the refine-loop-multi workflow.
```

Each invocation runs one iteration. Run it again to continue to the next iteration. The resume check at the start reads `docs/report/progress.txt` to determine where the loop is.

To run multiple iterations back-to-back without manual re-invocation, wrap in a loop in a parent workflow or use `/loop`.

## Completion criterion

Same as `refine-loop.md`: ≥95% of reports in the validated speech-bearing set yield at least one speech. Check the full dataset rate after each iteration with `diagnose.py`. Stop when the threshold is met.

---

## Workflow Script

```javascript
export const meta = {
  name: 'refine-loop-multi',
  description: 'Parallel speech parsing refinement — two investigation agents per iteration',
  phases: [
    { title: 'Resume' },
    { title: 'Investigate' },
    { title: 'Synthesize' },
    { title: 'Patch' },
    { title: 'Validate' },
    { title: 'Evaluate' },
  ],
}

const RESUME_SCHEMA = {
  type: 'object',
  properties: {
    iteration: { type: 'number' },
    pilotIds: { type: 'array', items: { type: 'number' } },
    heldOutIds: { type: 'array', items: { type: 'number' } },
    regressionIds: { type: 'array', items: { type: 'number' } },
    lastPatchSummary: { type: 'string' },
  },
  required: ['iteration', 'pilotIds', 'heldOutIds', 'regressionIds', 'lastPatchSummary'],
}

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    rootCauseGroups: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          failureStage: { type: 'string' },
          reportType: { type: 'string' },
          affectedIds: { type: 'array', items: { type: 'number' } },
          coverage: { type: 'number' },
          whyFails: { type: 'string' },
          proposedFix: { type: 'string' },
          failingSnippet: { type: 'string' },
          passingSnippet: { type: 'string' },
        },
        required: ['failureStage', 'reportType', 'affectedIds', 'coverage', 'whyFails', 'proposedFix'],
      },
    },
  },
  required: ['rootCauseGroups'],
}

const PATCH_SCHEMA = {
  type: 'object',
  properties: {
    patchDescription: { type: 'string' },
    targetGroup: {
      type: 'object',
      properties: {
        failureStage: { type: 'string' },
        reportType: { type: 'string' },
        affectedIds: { type: 'array', items: { type: 'number' } },
      },
      required: ['failureStage', 'reportType', 'affectedIds'],
    },
    backwardCompatReasoning: { type: 'string' },
    estimatedCoverage: { type: 'number' },
  },
  required: ['patchDescription', 'targetGroup', 'backwardCompatReasoning', 'estimatedCoverage'],
}

const VALIDATION_SCHEMA = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          reportId: { type: 'number' },
          passed: { type: 'boolean' },
          failureStage: { type: 'string' },
        },
        required: ['reportId', 'passed'],
      },
    },
    passingCount: { type: 'number' },
    totalCount: { type: 'number' },
  },
  required: ['results', 'passingCount', 'totalCount'],
}

const EVAL_SCHEMA = {
  type: 'object',
  properties: {
    keep: { type: 'boolean' },
    netNewPasses: { type: 'number' },
    regressionCount: { type: 'number' },
    rationale: { type: 'string' },
    progressEntry: { type: 'string' },
  },
  required: ['keep', 'netNewPasses', 'regressionCount', 'rationale', 'progressEntry'],
}

// ── Resume ────────────────────────────────────────────────────────────────────

phase('Resume')
const resume = await agent(`
Read the following files in the working directory and return structured state.

- docs/report/progress.txt: parse to find the current iteration number (count "## Iteration" headings) and
  summarise the last patch outcome in lastPatchSummary. If the file is empty or absent, return
  iteration=0 and lastPatchSummary="none".
- sample.json: parse the JSON and extract the "pilot", "held_out", and "regression" arrays of
  report IDs. If absent, return empty arrays and flag in lastPatchSummary.
- docs/report/parsing-patterns.md: read for context. Do not return its contents — just internalize it so
  you can brief downstream agents accurately if asked.

Return the structured state.
`, { schema: RESUME_SCHEMA, label: 'resume' })

const { iteration, pilotIds, heldOutIds, regressionIds } = resume
const nextIteration = iteration + 1

if (pilotIds.length === 0) {
  log('ERROR: sample.json missing or empty. Run refine-loop.md Setup Step 5 first.')
  return { status: 'setup_required' }
}

log(`Starting iteration ${nextIteration}. Pilot: ${pilotIds.length} IDs, held-out: ${heldOutIds.length}, regression: ${regressionIds.length}.`)

// ── Investigate (parallel) ────────────────────────────────────────────────────

phase('Investigate')
const [startLineFindings, speechFindings] = await parallel([

  () => agent(`
[Agent A — has_start_line=False lane]

You are one of two investigation agents running in parallel. Your lane is reports where the
speech start line cannot be detected (has_start_line=False).

Context files to read before investigating:
- docs/report/parsing-patterns.md — accumulated structural knowledge; read this first
- services/speech.py — the current parsing logic, specifically get_start_of_speech_line

Steps:
1. Run: python diagnose.py --ids ${JSON.stringify(pilotIds)}
   (read diagnose.py first if you are unsure of its CLI interface)
2. Filter results to reports where has_start_line=False.
3. For each failing report, run inspect_failures.py to read its raw markdown.
   (read inspect_failures.py first if you are unsure of its CLI interface)
4. For each failing report_type, also open 1-2 passing documents of the same type for comparison.
5. Group failures by root cause — look across all failing documents for shared structural patterns.
   One root-cause group may cover many report IDs.
6. For each root-cause group, determine why get_start_of_speech_line fails and what fix would
   address the group.

Return one entry per root-cause group. coverage = number of affected report IDs in this group.
Include representative markdown snippets (failing and passing) in each group.
`, { schema: FINDINGS_SCHEMA, label: 'agent-a:has_start_line', phase: 'Investigate' }),

  () => agent(`
[Agent B — can_get_speeches=False lane]

You are one of two investigation agents running in parallel. Your lane is reports where the
start line is found but speech segmentation fails (can_get_speeches=False).

Context files to read before investigating:
- docs/report/parsing-patterns.md — accumulated structural knowledge; read this first
- services/speech.py — the current parsing logic, specifically parse_speeches

Steps:
1. Run: python diagnose.py --ids ${JSON.stringify(pilotIds)}
   (read diagnose.py first if you are unsure of its CLI interface)
2. Filter results to reports where has_start_line=True AND can_get_speeches=False.
3. For each failing report, run inspect_failures.py to read its raw markdown.
   (read inspect_failures.py first if you are unsure of its CLI interface)
4. For each failing report_type, also open 1-2 passing documents of the same type for comparison.
5. Group failures by root cause — look across all failing documents for shared structural patterns.
   One root-cause group may cover many report IDs.
6. For each root-cause group, determine why speech segmentation fails and what fix would
   address the group.

Return one entry per root-cause group. coverage = number of affected report IDs in this group.
Include representative markdown snippets (failing and passing) in each group.
`, { schema: FINDINGS_SCHEMA, label: 'agent-b:can_get_speeches', phase: 'Investigate' }),

])

const allGroups = [
  ...(startLineFindings?.rootCauseGroups || []),
  ...(speechFindings?.rootCauseGroups || []),
].filter(Boolean)

if (allGroups.length === 0) {
  log('No failure groups found in pilot set. Check that diagnose.py is working correctly.')
  return { status: 'no_failures', iteration: nextIteration }
}

log(`Found ${allGroups.length} root-cause group(s) across both lanes.`)

// ── Synthesize ────────────────────────────────────────────────────────────────

phase('Synthesize')
const patchDecision = await agent(`
Two investigation agents have returned findings. Select ONE fix to apply this iteration —
the single change with the highest expected coverage across root-cause groups.

Agent A findings (has_start_line=False lane):
${JSON.stringify(startLineFindings, null, 2)}

Agent B findings (can_get_speeches=False lane):
${JSON.stringify(speechFindings, null, 2)}

Selection rules:
- Pick the fix with the highest coverage (most affected report IDs).
- When coverage is similar, prefer has_start_line fixes over can_get_speeches fixes (higher-priority stage).
- Prefer a condition-gated branch over a change to the general-case logic. If a fix only applies
  to a specific report_type, a title pattern, or a structural signal, gate it with a condition.
  This limits regression risk.
- When branching on report_type, compare against the STRING value (e.g. report_type == "oral-answer"),
  not the enum (e.g. ReportType.ORAL_ANSWER).
- State backward-compatibility reasoning: which currently-passing documents could be affected and why
  they won't be.

Return the selected fix with a complete patch description (enough for another agent to implement it
without reading the investigation findings) and backward-compatibility reasoning.
`, { schema: PATCH_SCHEMA, label: 'synthesize' })

log(`Selected fix: ${patchDecision.targetGroup.failureStage} / ${patchDecision.targetGroup.reportType} — estimated coverage: ${patchDecision.estimatedCoverage}`)

// ── Patch ─────────────────────────────────────────────────────────────────────

phase('Patch')
await agent(`
Apply this fix to services/speech.py. Do not make any other changes.

Fix description:
${patchDecision.patchDescription}

Backward-compatibility reasoning (for your reference):
${patchDecision.backwardCompatReasoning}

Rules:
- Apply exactly this fix. Do not add unrelated cleanup, formatting changes, or additional fixes.
- Match the existing code style.
- Do not add comments that explain what the code does. Only add a comment if the WHY is non-obvious
  (a hidden constraint, a subtle invariant, a specific bug workaround).
- After applying, re-read the modified function to confirm the change is correct.
`, { label: 'patch' })

// ── Validate (parallel) ───────────────────────────────────────────────────────

phase('Validate')
const [heldOutResult, regressionResult] = await parallel([

  () => agent(`
Run diagnose.py on the held-out improvement set — these are failing documents not shown during
investigation, drawn from the same (failure_stage, report_type) groups as the pilot.

Report IDs: ${JSON.stringify(heldOutIds)}

Run: python diagnose.py --ids ${JSON.stringify(heldOutIds)}

Record pass/fail for each report ID. A report passes if it yields at least one speech
(has_start_line=True AND can_get_speeches=True).

Return structured results with passingCount and totalCount.
`, { schema: VALIDATION_SCHEMA, label: 'validate:held-out', phase: 'Validate' }),

  () => agent(`
Run diagnose.py on the regression set — these are documents that were passing before this patch.
Check whether any now fail.

Report IDs: ${JSON.stringify(regressionIds)}

Run: python diagnose.py --ids ${JSON.stringify(regressionIds)}

Record pass/fail for each report ID. Flag any that fail — these are regressions.

Return structured results with passingCount and totalCount.
`, { schema: VALIDATION_SCHEMA, label: 'validate:regression', phase: 'Validate' }),

])

// ── Evaluate ──────────────────────────────────────────────────────────────────

phase('Evaluate')
const evaluation = await agent(`
Evaluate the patch and decide whether to keep or revert it.

Target group: ${patchDecision.targetGroup.failureStage} / ${patchDecision.targetGroup.reportType}
Affected IDs (from investigation): ${JSON.stringify(patchDecision.targetGroup.affectedIds)}

Held-out improvement set results (${heldOutResult?.passingCount} / ${heldOutResult?.totalCount} passing):
${JSON.stringify(heldOutResult?.results, null, 2)}

Regression set results (${regressionResult?.passingCount} / ${regressionResult?.totalCount} passing):
${JSON.stringify(regressionResult?.results, null, 2)}

Decision rules:
- KEEP if: net new passes on held-out set > net new failures AND no regressions on regression set.
  A single document improving is not sufficient — there must be a net improvement on the held-out set.
- REVERT if: net new failures >= net new passes OR any regressions detected.
- If reverting, revert services/speech.py now (use git checkout services/speech.py or undo the change).

After deciding:
1. Append one entry to docs/report/progress.txt using this structure:

   ## Iteration ${nextIteration} — <failure_stage> — <report_type> — <short description>

   **Affected report IDs:** <list>
   **Markdown snippet (failing):** <from investigation>
   **Markdown snippet (passing, same report_type):** <from investigation>
   **Why it fails:** <from investigation>
   **Proposed fix / approach:** <from patchDecision>
   **Outcome:** <kept / reverted — net change on held-out set, regression count>

2. If investigation revealed a new generalizable structural pattern about the markdown format or
   a report_type's document shape, also append it to docs/report/parsing-patterns.md.

Return the evaluation result.
`, { schema: EVAL_SCHEMA, label: 'evaluate' })

log(`Iteration ${nextIteration} complete: ${evaluation.keep ? 'KEPT' : 'REVERTED'} — net new passes: ${evaluation.netNewPasses}, regressions: ${evaluation.regressionCount}`)

return {
  iteration: nextIteration,
  kept: evaluation.keep,
  netNewPasses: evaluation.netNewPasses,
  regressionCount: evaluation.regressionCount,
  rationale: evaluation.rationale,
}
```

---

## Differences from refine-loop.md

| | refine-loop.md | refine-loop-multi-thread.md |
|---|---|---|
| Investigation | Sequential, one instance | Parallel (Agent A + Agent B) |
| Communication | Human reads files between steps | Orchestrator passes structured JSON between agents |
| Synthesis | Human picks the fix | Synthesize agent picks from both lanes' findings |
| Patch application | Human-supervised, one at a time | Same — single patch agent, serialized |
| Validation | Sequential | Parallel (held-out + regression sets) |
| Iteration log | Human writes to progress.txt | Evaluate agent appends to progress.txt |
| Sample widening (every 3 iterations) | Manual (Loop Step 7) | Not yet implemented — add manually when needed |
| 10-iteration checkpoint | Manual (Loop Step 8–9) | Not yet implemented — check iteration count in progress.txt |

The 10-iteration checkpoint and sample widening from `refine-loop.md` Loop Steps 7–9 are not
encoded in the workflow script. After every 3 iterations, manually widen the pilot sample per
`refine-loop.md` Step 7 and update `sample.json`. At iteration 10 (or multiples), review the
current success rate before continuing.

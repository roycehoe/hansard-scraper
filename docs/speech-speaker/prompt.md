# Speech → Speaker Refine Loop — Orchestration Prompt

Spawn three subagents sequentially. Complete each fully — code change, regression,
pilot assessment, progress.txt entry — before spawning the next. Each subagent
operates in a worktree-isolated environment and must merge its changes before the
next subagent starts.

## Project context (read before spawning any subagent)

Working directory: `/Users/meinhardt/ghq/github.com/roycehoe/handsard-scraper`

This is a Singapore Parliament Hansard scraper. The speech → speaker refine loop
improves the rate at which `Speech.speaker` strings resolve to a `Speaker` row.

**Current state:**
- Pilot: 267 speeches, match rate 226/267 = 84.6%
- Regression set: 53 speeches (baseline 40/40 at iteration 6; full set now 53)
- Last documented iteration: 15 (see `docs/speech-mp/progress.txt`)
- Next iterations to run: 16, 17, 18

**Key files:**
- `docs/speech-mp/refine-loop.md` — loop protocol (read before documenting)
- `docs/speech-mp/progress.txt` — iteration log (prepend new entries at top)
- `docs/speech-mp/sample.json` — fixed pilot/held-out/regression Speech IDs
- `docs/speech-mp/matching-patterns.md` — accumulated failure mode knowledge
- `populate/speaker_links.py` — `_populate_speech_speaker_ids` — main resolution logic
- `services/attendance.py` — `resolve_canonical_name`, `strip_title`, `build_speaker_lookups`

**How to run checks:**
```
PYTHONPATH=. poetry run python3 scripts/run_regression_check.py
PYTHONPATH=. poetry run python3 scripts/run_pilot_assessment.py
```

**Decision rule (from refine-loop.md):**
- KEPT if regression set has no new failures AND pilot match count increases
- REVERTED otherwise; log the reason

**progress.txt entry format** (prepend at top, most-recent-first):
```
## Iteration N — YYYY-MM-DD

### can_match — <types> — <short description>

**Affected Speech IDs (pilot):** (count from pilot assessment diff)

**Speaker string (failing):** (examples from pilot assessment unmatched list)

**Speaker string (passing, same report_type):** (a passing contrast example)

**Root cause:** (what the current logic does wrong)

**Proposed fix:** (the code change)

**Files changed:** (list)

**Backward-compatibility:** (reasoning — which passing cases could be affected and why they won't be)

**Outcome:** KEPT / REVERTED
- Regression: N/53 = X%
- Pilot: N/267 = X% (before → after if measurable)
- Top newly-resolved: (examples)
```

---

## Subagent 1 — Iteration 16: wordset initial-stripping

**File:** `services/attendance.py`

**Problem:** `_build_wordset_subset_lookup` keys on `frozenset(all_words)` including
single-character initials. A query for `Aline Wong` produces `{aline, wong}`, which
never matches the Speaker entry `Wong Aline K` whose key is `{aline, k, wong}`.

**Fix — build side** in `_build_wordset_subset_lookup`, filter single-char tokens
before keying and before applying the 3-word minimum:

```python
# current:
words = _period_normalize(strip_title(display)).split()
if len(words) < _MIN_WORDSET_SUBSET_WORDS:
    continue
key = (frozenset(words), parliament)

# replace with:
words = [w for w in _period_normalize(strip_title(display)).split() if len(w) > 1]
if len(words) < _MIN_WORDSET_SUBSET_WORDS:
    continue
key = (frozenset(words), parliament)
```

**Fix — lookup side** in `_try_name_variant`, strip initials from the query too:

```python
# current:
result = lookups.wordset_subset.get((frozenset(_period_normalize(name).split()), parliament))

# replace with:
_wss_words = [w for w in _period_normalize(name).split() if len(w) > 1]
result = lookups.wordset_subset.get((frozenset(_wss_words), parliament))
```

Do not change anything else.

**After the code change:**
1. `PYTHONPATH=. poetry run python3 scripts/run_regression_check.py`
2. `PYTHONPATH=. poetry run python3 scripts/run_pilot_assessment.py`
3. Run `ruff check .` and fix any errors introduced.
4. Prepend `## Iteration 16` to `docs/speech-mp/progress.txt`. Fill in all fields.
   Confirm `Dr Aline Wong` and `Dr Augustine Tan` now appear in the pilot output
   as resolved (they should — check the unmatched list).

---

## Subagent 2 — Iteration 17: presiding officer mapping

**Files:** `populate/speaker_links.py`

**Problem:** `Mr Speaker` (×18,122 corpus-wide) and `Mr Deputy Speaker` (×2,132)
are the largest unresolved category. They are presiding officers whose names do not
appear in the speaker string — only their role title does.

**Step A — generate the dict.** Run:
```
PYTHONPATH=. poetry run python3 scripts/find_presiding_officers.py
```
Capture the printed `_PRESIDING_OFFICERS` dict literal. If the script errors or
produces an empty dict, investigate before proceeding.

**Step B — add the dict** to `populate/speaker_links.py` near the top (after the
`_NON_SPEAKERS` set):
```python
_PRESIDING_OFFICERS: dict[tuple[str, int], str] = {
    <paste output from Step A>
}
```

**Step C — add early handling** in `_populate_speech_speaker_ids`, inside the
per-speech loop, immediately after the `_NON_SPEAKERS` / `startswith("(")` guard:

```python
# Presiding officer strings carry no individual name — resolve by parliament lookup.
_po_role: str | None = None
if raw in ("Mr Speaker", "Mdm Speaker"):
    _po_role = "SPEAKER"
elif raw.startswith("Mr Deputy Speaker") or raw.startswith("The Deputy Speaker"):
    _po_role = "DEPUTY SPEAKER"
if _po_role is not None:
    _po_parl = parliament if parliament != 0 else next(
        (p for p in _COLONIAL_PARLIAMENT_FALLBACKS if (_po_role, p) in _PRESIDING_OFFICERS),
        parliament,
    )
    _po_name = _PRESIDING_OFFICERS.get((_po_role, _po_parl))
    if _po_name:
        _po_canonical, _po_resolved_parl = _resolve_with_parliament_fallback(
            _po_name, _po_parl, lookups, speaker_id_lookup
        )
        if _po_canonical:
            _po_sid = speaker_id_lookup.get((_po_canonical, _po_resolved_parl))
            if _po_sid:
                crud.set_speaker_id(speech_id, _po_sid)
                updated += 1
    continue  # always skip cascade for presiding officers
```

The `continue` fires unconditionally — presiding officer strings are never resolvable
via the name cascade.

Note: `raw` at this point is the result of `speaker.rstrip(":").strip()` but before
the paren-extraction block. Make sure the guard fires before paren extraction, not after.

**After the code change:**
1. Run regression check and pilot assessment.
2. Run `ruff check .` and fix any introduced errors.
3. Prepend `## Iteration 17` to `docs/speech-mp/progress.txt`.

---

## Subagent 3 — Iteration 18: double-parenthetical extraction

**File:** `populate/speaker_links.py`

**Problem:** `The Second Deputy Prime Minister (Foreign Affairs) (Mr. S. Rajaratnam)`
has two parenthetical groups. The current regex `r"\s*\(([^)]+)\)\s*$"` grabs only
the trailing one — `(Foreign Affairs)` — which is not a name. The name-bearing paren
`(Mr. S. Rajaratnam)` is skipped.

**Fix** — replace the current paren-match block in `_populate_speech_speaker_ids`:

```python
# current:
paren_match = re.search(r"\s*\(([^)]+)\)\s*$", raw)
if paren_match:
    inner = paren_match.group(1).strip()
    if strip_title(inner) != inner:
        raw = inner
    else:
        raw = raw[: paren_match.start()]

# replace with:
parens = list(re.finditer(r"\(([^)]+)\)", raw))
if parens:
    title_paren = next(
        (m for m in reversed(parens) if strip_title(m.group(1).strip()) != m.group(1).strip()),
        None,
    )
    if title_paren:
        raw = title_paren.group(1).strip()
    else:
        raw = raw[: parens[0].start()].strip()
```

The logic: scan all parens right-to-left; use the first one whose inner content has a
recognisable title prefix (i.e. `strip_title` changes it). If none has a title prefix,
strip everything from the first paren onward (constituency-strip behaviour, unchanged).

**After the code change:**
1. Run regression check and pilot assessment.
2. Run `ruff check .` and fix any introduced errors.
3. Prepend `## Iteration 18` to `docs/speech-mp/progress.txt`.
4. Confirm `The Second Deputy Prime Minister (Foreign Affairs) (Mr. S. Rajaratnam)`
   is no longer in the pilot unmatched list.

---

## After all three subagents complete

Report:
- Regression result per iteration (N/53)
- Pilot rate per iteration (N/267), before → after
- KEPT or REVERTED for each
- Top newly-resolved speaker strings per iteration
- Any judgment calls or unexpected findings
- Updated overall pilot rate after all three

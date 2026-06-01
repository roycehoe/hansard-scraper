# Speech → Speaker Refine Loop — Orchestration Prompt

Spawn seven subagents. Subagents 1–6 run sequentially — complete each fully before
spawning the next. Subagent 7 (colonial data) is independent and may run concurrently
with Subagents 3–6.

## Project context (read before spawning any subagent)

Working directory: `/Users/meinhardt/ghq/github.com/roycehoe/handsard-scraper`

This is a Singapore Parliament Hansard scraper. The speech → speaker refine loop
improves the rate at which `Speech.speaker` strings resolve to a `Speaker` row.

**Current state:**
- Pilot: 267 speeches, match rate 226/267 = 84.6%
- Regression set: 53 speeches (baseline 40/40 at iteration 6; full set now 53)
- Last documented iteration: 15 (see `docs/speech-speaker/progress.txt`)
- Next iterations to run: 16, 17, 18, 19, 20 (+ colonial data collection)

**Key files:**
- `docs/speech-speaker/refine-loop.md` — loop protocol; Loop Step 4 has the exact `progress.txt` entry template
- `docs/speech-speaker/progress.txt` — iteration log (prepend new entries at top, most-recent-first)
- `docs/speech-speaker/sample.json` — fixed pilot/held-out/regression Speech IDs
- `docs/speech-speaker/matching-patterns.md` — accumulated failure mode knowledge
- `populate/speaker_links.py` — `_populate_speech_speaker_ids` — main resolution logic
- `services/attendance.py` — `resolve_canonical_name`, `strip_title`, `build_speaker_lookups`

**How to run checks:**
```
PYTHONPATH=. poetry run python3 scripts/run_regression_check.py
PYTHONPATH=. poetry run python3 scripts/run_pilot_assessment.py
```

Pilot assessment prints: `Pilot (267 IDs): X/267 = X.X%`, a per-group table, then
`Top unmatched speaker strings (N total):` with lines like `  3x  'Dr Aline Wong'`.
To confirm a specific speaker resolved, check it no longer appears in that unmatched list.

Regression check prints: `Regression set: X/53 passing`. If regressions exist, a table
shows speech ID, parliament, speaker string, and resolved canonical (or `<unresolved>`).

**Decision rule:**
- **KEPT** if regression set has no new failures AND pilot match count increases
- **REVERTED** otherwise; log the reason

**If REVERTED:**
1. `git checkout -- <file(s) you changed>` to restore originals
2. Re-run `PYTHONPATH=. poetry run python3 scripts/run_regression_check.py` to confirm baseline is restored
3. In `progress.txt`, set `**Outcome:** REVERTED — <reason>`
4. Do **not** commit

**If KEPT:** `git add <files changed>` then `git commit -m 'feat: iteration N — <short description>'`

**Return format** — end each code subagent's response with:
```
## Iteration N result
Outcome: KEPT / REVERTED
Regression: X/53 = X%
Pilot: X/267 = X% (before → after)
Newly resolved: 'example 1', 'example 2'
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
2. `PYTHONPATH=. poetry run python3 scripts/run_pilot_assessment.py` — confirm `Dr Aline Wong`
   and `Dr Augustine Tan` no longer appear in the top unmatched list
3. `ruff check .` — if errors, fix them and re-run both checks above
4. Prepend `## Iteration 16` to `docs/speech-speaker/progress.txt`; fill all fields per the
   template in `docs/speech-speaker/refine-loop.md` Loop Step 4
5. If KEPT: commit. If REVERTED: follow the REVERT protocol in the project context above.

Return: see return format above.

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

Do not change anything else.

**After the code change:**
1. `PYTHONPATH=. poetry run python3 scripts/run_regression_check.py`
2. `PYTHONPATH=. poetry run python3 scripts/run_pilot_assessment.py`
3. `ruff check .` — if errors, fix them and re-run both checks above
4. Prepend `## Iteration 17` to `docs/speech-speaker/progress.txt`; fill all fields per the
   template in `docs/speech-speaker/refine-loop.md` Loop Step 4
5. If KEPT: commit. If REVERTED: follow the REVERT protocol in the project context above.

Return: see return format above.

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

Do not change anything else.

**After the code change:**
1. `PYTHONPATH=. poetry run python3 scripts/run_regression_check.py`
2. `PYTHONPATH=. poetry run python3 scripts/run_pilot_assessment.py` — confirm
   `The Second Deputy Prime Minister (Foreign Affairs) (Mr. S. Rajaratnam)` no longer
   appears in the top unmatched list
3. `ruff check .` — if errors, fix them and re-run both checks above
4. Prepend `## Iteration 18` to `docs/speech-speaker/progress.txt`; fill all fields per the
   template in `docs/speech-speaker/refine-loop.md` Loop Step 4
5. If KEPT: commit. If REVERTED: follow the REVERT protocol in the project context above.

Return: see return format above.

---

## Subagent 4 — Iteration 19: loop strip_title until stable

**File:** `services/attendance.py`

**Problem:** `strip_title` removes only the first matching prefix per call and returns.
Stacked titles like `Assoc. Prof. Dr Yaacob Ibrahim` or `RAdm [NS] Lui Tuck Yew` are
only partially stripped — the remainder (`Dr Yaacob Ibrahim` or `[NS] Lui Tuck Yew`)
falls through all resolution strategies.

Top affected speakers corpus-wide (from `docs/improvements.md`):
- `Assoc. Prof. Dr Yaacob Ibrahim` — 2,328 speeches
- `Assoc Prof Dr Yaacob Ibrahim` — 330 speeches
- `RAdm [NS] Lui Tuck Yew` — 384 speeches

Estimated impact: ~2,951 speech rows (+0.6 pp).

**Fix** — replace the current early-return body with a while-loop in `strip_title`:

```python
# current:
def strip_title(text: str) -> str:
    for prefix in _TITLE_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text

# replace with:
def strip_title(text: str) -> str:
    while True:
        for prefix in _TITLE_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        else:
            return text
```

The `else` clause on the `for` loop fires only when no prefix matched — i.e. the string
is stable. This is a pure superset of the current behaviour: a single-prefix name goes
through exactly one iteration and returns the same result.

**Backward-compatibility:** Zero regression risk. Any name that currently resolves does
so because `strip_title` already returns the right suffix on the first pass; the loop
exits after that same pass for those names. The only change is that names requiring two
or more prefix strips now reach the resolution cascade in a fully stripped state.

Do not change anything else.

**After the code change:**
1. `PYTHONPATH=. poetry run python3 scripts/run_regression_check.py`
2. `PYTHONPATH=. poetry run python3 scripts/run_pilot_assessment.py` — confirm
   `Assoc. Prof. Dr Yaacob Ibrahim` no longer appears in the top unmatched list
3. `ruff check .` — if errors, fix them and re-run both checks above
4. Prepend `## Iteration 19` to `docs/speech-speaker/progress.txt`; fill all fields per the
   template in `docs/speech-speaker/refine-loop.md` Loop Step 4
5. If KEPT: commit. If REVERTED: follow the REVERT protocol in the project context above.

Return: see return format above.

---

## Subagent 5 — Iteration 20 research: role-only speaker discovery

**No code changes.** This subagent's sole output is the `_ROLE_ONLY_SPEAKERS` dict literal
for Subagent 6 to implement.

**Step A — discover the full role-only set.** Run:

```python
PYTHONPATH=. poetry run python3 - <<'EOF'
from sqlmodel import Session, select, func
from database.init import engine
from database.speech import Speech
from database.report import Report
import re

role_re = re.compile(r"^The\s+[A-Z][a-zA-Z\s]+$")
with Session(engine) as s:
    rows = s.exec(
        select(Speech.speaker, Report.parliament_number, func.count())
        .join(Report, Speech.report_id == Report.id)
        .where(Speech.speaker_id == None)
        .group_by(Speech.speaker, Report.parliament_number)
        .order_by(func.count().desc())
    ).all()

for speaker, parl, n in rows:
    if speaker and role_re.match(speaker.strip()):
        print(f"  parl={parl}  n={n:>6}  {speaker}")
EOF
```

This prints every distinct role-only string with its parliament number and frequency.

**Step B — build the mapping.** For each (role, parliament) pair with n ≥ 5, identify
the MP who held that role. Use web search against Singapore Infopedia, Wikipedia
("List of Prime Ministers of Singapore", "Chief Ministers of Singapore", etc.) and the
Hansard sitting dates to bound the tenure. Colonial roles are tractable:

| Role | Parliament | MP |
|---|---|---|
| The Chief Minister | 0 (LA, 1955–56) | David Marshall |
| The Chief Minister | 0 (LA, 1956–59) | Lim Yew Hock |
| The Chief Minister | 0 (LA, 1959) | Lee Kuan Yew |
| The Prime Minister | 1 | Lee Kuan Yew |
| The Prime Minister | 2–8 | Lee Kuan Yew (until 1990); Goh Chok Tong thereafter |
| The Financial Secretary | 0 | Research from Step A output |

For parliament=0, the sitting dates in `Sitting.sitting_date` can help disambiguate
tenures that span a parliament boundary.

Do not guess. If a role cannot be confirmed, leave it out — a missed match is better
than a wrong attribution.

**Return:** Respond with the complete `_ROLE_ONLY_SPEAKERS` dict literal as a Python
code block, plus the source (URL or reference) for each entry. Do not write any files.
Subagent 6 will implement it.

---

## Subagent 6 — Iteration 20 code: role-only ministerial mapping

**File:** `populate/speaker_links.py`

**Input:** The `_ROLE_ONLY_SPEAKERS` dict literal produced by Subagent 5.

**Step A — add the dict** to `populate/speaker_links.py` near `_PRESIDING_OFFICERS`:

```python
_ROLE_ONLY_SPEAKERS: dict[tuple[str, int], str] = {
    # (normalised_role_string, parliament_number): canonical_speaker_name
    # Populate from Subagent 5 findings
}
```

**Step B — add early handling** in `_populate_speech_speaker_ids`, immediately after
the `_po_role` presiding-officer block (and before the paren-extraction block):

```python
# Role-only strings — resolve by parliament→person mapping.
_role_key = (raw, parliament) if parliament != 0 else None
if _role_key is None:
    for _fb in _COLONIAL_PARLIAMENT_FALLBACKS:
        if (raw, _fb) in _ROLE_ONLY_SPEAKERS:
            _role_key = (raw, _fb)
            break
if _role_key and _role_key in _ROLE_ONLY_SPEAKERS:
    _role_name = _ROLE_ONLY_SPEAKERS[_role_key]
    _role_canonical, _role_parl = _resolve_with_parliament_fallback(
        _role_name, _role_key[1], lookups, speaker_id_lookup
    )
    if _role_canonical:
        _role_sid = speaker_id_lookup.get((_role_canonical, _role_parl))
        if _role_sid:
            crud.set_speaker_id(speech_id, _role_sid)
            updated += 1
    continue  # role-only strings are never resolvable via the name cascade
```

The `continue` fires unconditionally — if the role isn't in the dict, the speech stays
unmatched rather than falling through to produce a wrong result.

Do not change anything else.

**After the code change:**
1. `PYTHONPATH=. poetry run python3 scripts/run_regression_check.py`
2. `PYTHONPATH=. poetry run python3 scripts/run_pilot_assessment.py`
3. `ruff check .` — if errors, fix them and re-run both checks above
4. Prepend `## Iteration 20` to `docs/speech-speaker/progress.txt`; fill all fields per the
   template in `docs/speech-speaker/refine-loop.md` Loop Step 4. Report the exact
   `_ROLE_ONLY_SPEAKERS` dict built, the source for each entry, and how many pilot speeches
   moved from unmatched to matched.
5. If KEPT: commit. If REVERTED: follow the REVERT protocol in the project context above.

Return: see return format above.

---

## Subagent 7 — Colonial LA members data collection (5-agent parallel)

This is a data task, not a code fix. No code changes. No `progress.txt` entry.
This subagent group is independent of code iterations 16–20 and may run concurrently
with Subagents 3–6.

**Goal:** Expand `data/colonial_la_members.json` with missing colonial Legislative
Assembly members so that speech and attendance rows from parliament=0 (volumes 1–26,
1955–1965 era) can be resolved. Each new entry directly unlocks matches in both
`Speech.speaker_id` and `Attendance.speaker_id` without any pipeline change.

**parliament_number — two contexts, one field name:**

| Context | Value | Meaning |
|---|---|---|
| `Sitting` / `Report` DB rows | `0` | All colonial LA era sittings (1955–1965) |
| `Speaker` table / JSON entries | `1` | LA-era members — use this for almost all candidates |
| `Speaker` table / JSON entries | `0` | Pre-1955 Municipal Commission only (extremely rare) |

When writing JSON entries, use `parliament_number: 1` for virtually every candidate.
The resolution code automatically falls back from parliament=0 → 1, 2, 3 when
looking up Speaker rows. Use `parliament_number: 0` only for figures confirmed in
the pre-1955 Municipal Commission era.

---

### Phase 1 — Scout (run inline before spawning agents)

**Step 1 — baseline candidate count.** Run:

```bash
PYTHONPATH=. poetry run python3 scripts/find_unmatched_attendees.py \
    --json /tmp/la_candidates.json --verbose
```

Record the number of names in the `candidates` bucket from the verbose output.
This is the before count for the verification step later.

**Step 2 — filter the raw candidate list.** Load `/tmp/la_candidates.json` and
remove the following before assigning work to agents:

1. Names already present in `data/colonial_la_members.json` (exact match)
2. Obvious OCR variants of existing entries (e.g. `Gob Chew Chua` → already have
   `Goh Chew Chua`; `Lim Yew Yock` → already have `Lim Yew Hock`)
3. Role / ministry strings — not person names (e.g. `Ministry of Labour and
   Government Whip`, `Minister of Defence`, `Water Resources and Deputy Government Whip`)
4. Malformed / truncated names with unmatched parentheses (e.g. `Yeoh Ghim Seng (Joo Chiat`)

**Step 3 — divide and assign.** From the remaining candidates with frequency ≥ 5,
take the top 50 sorted by descending frequency. Divide into 5 slices of ~10 names
each (slice 1 = highest frequency, slice 5 = lowest) and pass one slice to each
research agent.

---

### Phase 2 — Research (5 parallel agents, model: haiku)

Spawn 5 agents concurrently. Each receives its assigned name slice and a copy of
the current `data/colonial_la_members.json` for dedup context.

Each agent applies this protocol to every name in its slice:

**1. OCR / variant check first.**
Compare the name against `data/colonial_la_members.json`. If it is clearly a
corrupted or decorated form of an existing entry (e.g. `lbrahim Othman` →
`Ibrahim Othman`; `Abdul Hamid Bin Haji Jumat. P.M.N.` → `Abdul Hamid Bin Haji Jumat`):
do **not** add a new entry. Note the variant string in the existing entry's `comments`
field and move on.

**2. Role / noise check.**
If the name is a ministry, role title, or clearly not a person's name, skip it and
list it in the report as `noise`.

**3. Confirm via web search.**
Search `"<name>" Singapore Legislative Assembly` and `"<name>" Singapore Infopedia`.
Confirm the person was an elected or nominated LA member — not a visitor, civil servant,
or clerk.

**4. If confirmed**, produce a JSON entry:
```json
{"name": "Canonical Name", "party": "Party Name",
 "parliament_number": 1, "is_legislative_assembly": true, "comments": null}
```
The `name` field must match how the person appears in Hansard markdown. If unsure,
check attendance records:
```python
PYTHONPATH=. poetry run python3 - <<'EOF'
from sqlmodel import Session, select
from database.init import engine
from database.attendance import Attendance
with Session(engine) as s:
    rows = s.exec(
        select(Attendance.speaker_name)
        .where(Attendance.speaker_name.ilike("%<partial name>%"))
        .limit(20)
    ).all()
print(rows)
EOF
```

**5. If unconfirmable**, list the name as `unconfirmable — <reason>`. Do not guess.
A missed match is better than a wrong attribution.

**Return:** a JSON array of confirmed new entries plus a plain-text report listing:
- OCR variants identified (variant → existing entry it maps to)
- Noise strings skipped
- Unconfirmable names with reason

---

### Phase 3 — Synthesis

After all 5 agents complete:

1. Merge the 5 JSON arrays, deduplicating by `name`.
2. Append confirmed entries to `data/colonial_la_members.json`.
3. Load:
   ```bash
   PYTHONPATH=. poetry run python3 scripts/load_colonial_la_speakers.py
   ```
4. **Verify improvement** — re-run the scout and compare against the Phase 1 baseline:
   ```bash
   PYTHONPATH=. poetry run python3 scripts/find_unmatched_attendees.py --verbose
   ```
   Report how many names moved out of the `candidates` bucket (i.e. are now resolved).

**Report:**
- Names processed per agent (slice assignment)
- New entries added (count + names)
- OCR variants identified (list)
- Noise strings filtered (count)
- Unconfirmable names (list with reason)
- `candidates` bucket size before → after
- Total `Speaker` rows inserted by the loader

---

## After all seven subagents complete

Read `docs/speech-speaker/progress.txt` (top entries for iterations 16–20) and each
code subagent's return block to compile this report:

- Regression result per iteration (N/53) for iterations 16–20
- Pilot rate per iteration (N/267), before → after
- KEPT or REVERTED for each code iteration
- Top newly-resolved speaker strings per iteration
- Any judgment calls or unexpected findings
- Updated overall pilot rate after all iterations
- Estimated DB match rate improvement from the colonial data load (Subagent 7)

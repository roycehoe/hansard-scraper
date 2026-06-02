# Attendance Pipeline Fix Loop — Orchestration Protocol

Reduces the `candidates` bucket in `find_unmatched_attendees.py --verbose` by fixing
OCR corruptions that block name resolution against existing Speaker table entries.
Progress is tracked in `docs/speech-speaker/progress-pipeline.txt`.

---

# Architecture Rule — Read This First

## OCR corrections are parliament-agnostic

An OCR scanner makes the same character substitution error regardless of which
parliament the sitting belongs to. **Never** scope an OCR fix to specific parliament
numbers in `_MANUAL_OVERRIDES`. That encodes the person's parliamentary history rather
than the OCR error, and requires manual enumeration of every parliament they served in.

**Wrong approach (do not repeat):**
```python
# Each parliament needs its own entry — error-prone and maintenance burden
_MANUAL_OVERRIDES = {
    ("jek yuen thong", 1): "Jek Yeun Thong",
    ("jek yuen thong", 3): "Jek Yeun Thong",
    ("jek yuen thong", 4): "Jek Yeun Thong",
    ("jek yuen thong", 6): "Jek Yeun Thong",
}
```

**Correct approach:**
```python
# One entry; the cascade handles parliament-specific lookup
_OCR_CORRECTIONS = {
    "jek yuen thong": "Jek Yeun Thong",  # applies at any parliament
}
```

## What goes where

| Fix type | Location | Why |
|---|---|---|
| Character substitution (b↔h, l↔I, u↔e) | `_OCR_CORRECTIONS` | Parliament-agnostic |
| Post-nominal decorations (J.P., D.U.T.) | `_OCR_CORRECTIONS` | Parliament-agnostic |
| OCR-corrupted prefix (Inche., Haii) | `_OCR_CORRECTIONS` | Parliament-agnostic |
| Surname-only forms (barker, bani) | `_MANUAL_OVERRIDES` | Parliament needed to disambiguate |
| Inverted canonicals (s rajaratnam → Rajaratnam, S) | `_MANUAL_OVERRIDES` | Cascade can't reach inverted form |
| Specific structural one-offs | `_MANUAL_OVERRIDES` | Case-by-case |

## How `_OCR_CORRECTIONS` works

Applied in `resolve_canonical_name` BEFORE the parliament-scoped cascade:

```python
corrected = _OCR_CORRECTIONS.get(_period_normalize(name))
if corrected:
    name = corrected
# existing cascade unchanged — finds corrected name at correct parliament
```

The key is `_period_normalize(ocr_form)`. Verify keys with:
```python
python3 -c "
import re
def pn(s):
    s = re.sub(r'(?<=[A-Z])\.(?=[A-Z])', ' ', s)
    s = re.sub(r'([A-Z])\.', r'\1', s)
    return re.sub(r'\s+', ' ', s).strip().lower()
print(pn('Your. OCR. Form. Here'))
"
```

---

# Environment Note

```bash
PYTHONPATH=. poetry run python3 scripts/find_unmatched_attendees.py --verbose
```

Takes ~6 minutes. Run in background; never block a synthesis step on it.

---

# Before Starting — Resume Check

Load existing artifacts:
- `docs/speech-speaker/progress-pipeline.txt` — iteration log; read to find the last
  incomplete iteration and its before-count.
- `services/attendance.py` — `_OCR_CORRECTIONS` and `_MANUAL_OVERRIDES` — check what
  has already been added before researching new overrides.
- `docs/speech-speaker/progress-research.txt` — pipeline fix candidates table (classified
  OCR forms from the research loop; use as the initial queue).

---

# Method

## Per-iteration steps

**Step 1 — Pick a fix type from the queue.**
Batch by fix type (character substitution, post-nominal, prefix), not by frequency.
Each iteration should be one logical code change. Reference `progress-research.txt`
for the classified candidate list.

**Step 2 — Confirm the canonical and volumes.**
For each OCR form, run two checks inline (not via a sub-agent):

```python
# 1. Confirm canonical exists in Speaker table
PYTHONPATH=. poetry run python3 - <<'EOF'
from sqlmodel import Session, select
from database.init import engine
from database.speaker import Speaker
with Session(engine) as s:
    rows = s.exec(select(Speaker).where(Speaker.name.ilike("%PARTIAL%")).limit(5)).all()
    for r in rows: print(r.parliament_number, r.name)
EOF

# 2. Confirm which volumes the OCR form appears in (to verify correct attribution)
PYTHONPATH=. poetry run python3 - <<'EOF'
from sqlmodel import Session, select, text
from database.init import engine
with Session(engine) as s:
    rows = s.exec(text("""
        SELECT volume_no, COUNT(*) FROM sitting
        WHERE markdown_content ILIKE '%OCR FORM%'
        GROUP BY volume_no ORDER BY volume_no
    """)).all()
    print([(r[0], r[1]) for r in rows])
EOF
```

Cross-reference volumes against `VOLUME_TO_PARLIAMENT` in `services/attendance.py` to
verify the OCR form appears only during the canonical person's active parliamentary term.
**A missed match is better than a wrong attribution.**

**Step 3 — Compute the `_period_normalize` key.**
Use the verification snippet above. Common traps:
- Trailing period after a lowercase letter survives: `"Wee Toon. Boon"` → `"wee toon. boon"`
- Periods between uppercase letters are expanded: `"D.U.T."` → `"d u t"`
- `"Mr,"` (comma) is NOT stripped — period-only stripping applies

**Step 4 — Add to `_OCR_CORRECTIONS`.**
One entry per OCR form. Add a comment with the specific character error. Do not add
parliament entries in `_MANUAL_OVERRIDES` for the same name.

**Step 5 — Verify.**
Run `find_unmatched_attendees.py` in the background:
```bash
PYTHONPATH=. poetry run python3 scripts/find_unmatched_attendees.py --verbose 2>&1 \
  | grep -E "Unmatched|Candidates|distinct" | head -5
```

Record before → after counts in `progress-pipeline.txt`.

**Step 6 — Commit.**
One commit per fix type:
```
fix: OCR <description> (<N> rows resolved)
```

**Step 7 — Check completion.**
Stop when all remaining candidates with frequency ≥ 5 are confirmed unresolvable
(noise, post-LA MPs outside fallback range, genuinely unknown people).

---

# Baseline and Progress

See `docs/speech-speaker/progress-pipeline.txt` for the full iteration log with
before/after counts per iteration.

Pre-pipeline-fix baseline (after research loop session 1):
- Distinct candidates: 221
- Candidate rows: ~2,439

After research loop + pipeline fix iterations 1–6 (as of 2026-06-02):
- Distinct candidates: 194
- Candidate rows: 1,095

# Colonial LA Members Research Loop — Orchestration Protocol

Expands `data/colonial_la_members.json` to improve Speaker resolution for colonial-era
records (parliament=0 sittings, volumes 1–26, 1955–1965). Each confirmed entry directly
unlocks matches in both `Speech.speaker_id` and `Attendance.speaker_id` without any
pipeline change.

---

# Environment Note

All Python scripts must be run with PYTHONPATH set:

```bash
PYTHONPATH=. poetry run python3 scripts/find_unmatched_attendees.py
```

The project uses a remote PostgreSQL database; `DATABASE_URL` is loaded from `.env`.
`find_unmatched_attendees.py --verbose` scans all sittings and takes ~6 minutes.
Run it in the background; do not block a synthesis agent on it.

When fanning out research to sub-agents, use **3 agents** (Haiku model). Run the DB
pre-check inline before spawning — it eliminates most candidates cheaply and avoids
burning agent overhead on names that already resolve. Use Sonnet only for the synthesis
step (combining results, writing files, running the loader).

---

# Before Starting — Resume Check

Before beginning Setup or any loop iteration, load existing artifacts:

- `data/colonial_la_members.json` — current confirmed members; never re-research names already here.
- `docs/speech-speaker/progress-research.txt` — iteration log; read to determine which iteration the loop is on and what was last attempted.
- `docs/speech-speaker/learnings.txt` — session notes capturing non-obvious findings and workflow lessons; read before investigating any failures.

Handle partial artifact states as follows:
- All three present (`progress-research.txt`, `colonial_la_members.json`, and the candidate JSON from `--json`) → skip Setup entirely; resume from the last incomplete step in `progress-research.txt`.
- `progress-research.txt` absent → treat as iteration 0; run Setup from Step 1.
- `progress-research.txt` present but `colonial_la_members.json` missing → flag as an integrity issue before proceeding. A missing JSON means all prior Speaker inserts may be absent from the DB. Check the Speaker table directly before re-running the loader.
- `progress-research.txt` present but the candidate JSON stale or missing → re-run `find_unmatched_attendees.py` to regenerate it; do not re-run full Setup.

---

# parliament_number — Two Contexts, One Field Name

This is the single most common source of wrong entries. Always refer to this table:

| Context | Value | Meaning |
|---|---|---|
| `Sitting` / `Report` / `Speech` DB rows | `0` | All colonial LA era sittings (1955–1965) |
| `Speaker` table / `colonial_la_members.json` | `1` | LA-era elected/nominated members (use for almost all candidates) |
| `Speaker` table / `colonial_la_members.json` | `0` | Pre-1955 Municipal Commission only (extremely rare) |

The resolution code (`_COLONIAL_PARLIAMENT_FALLBACKS = [1, 2, 3]`) automatically falls
back from `parliament=0` → `1, 2, 3` when looking up Speaker rows. A Speaker row at
`parliament_number=1` is therefore reachable from any colonial-era sitting.

---

# Goal

Reduce the `candidates` bucket in `find_unmatched_attendees.py --verbose` by confirming
and adding genuinely missing LA members to `data/colonial_la_members.json`.

**Target set definition** — a name belongs in the candidates bucket if:
1. It appears in Attendance records from parliament=0 sittings.
2. It passes all noise filters (not presiding, not allcaps header, not document noise).
3. It has no matching Speaker row.

A name is **resolvable via this loop** only if the person is a confirmed LA member not
yet in the Speaker table. Names that are OCR corruptions of existing Speaker rows,
role/ministry strings, or post-LA era MPs are **not resolvable here** — they require
pipeline fixes or are noise.

**Ceiling awareness:** Most of the candidates bucket is OCR noise, not missing people.
The realistic ceiling for this loop is far below the raw candidate count. Stop iterating
when all remaining high-frequency candidates are confirmed noise or unresolvable.

---

# Baseline

Established 2026-06-02 (before session 1 additions):

- Unmatched attendance rows: **3,030**
- Candidates bucket (likely real people, no Speaker entry): **2,663**
- Distinct candidate names: **223**
- Presiding: 79 | Allcaps header: 19 | Document noise: 269

After session 1 (Lim Huan Boon + Tan Siak Kew added): verification scan pending.

**Top candidates by frequency at baseline (freq ≥ 5):**

| Count | Name | Status after session 1 |
|---|---|---|
| 1024 | Lai Tha Chai | OCR of Lai Tai Chai (parl=3+); needs follow-up — see learnings.txt |
| 136 | Lim Huan Boon | ✅ Added (session 1) |
| 113 | Chin Ham Tong | OCR of Chin Harn Tong (parl=3, post-LA) |
| 88 | Tan Siak Kew | ✅ Added (session 1) |
| 51 | lbrahim Othman | OCR of Ibrahim Othman (parl=6+, post-colonial) |
| 50 | P. Govindasamy | Unconfirmable (session 1) |
| 45 | Tan Soo Khoon (Brickworks GRC | Malformed/truncated — noise |
| 42 | E.W. Barker) (Tanglin | Malformed/truncated — noise |
| 31 | Wong Kwei Cheong, P.B.m. | Wong Kwei Cheong in Speaker at parl=5 only, not LA era |
| 25 | Mohd Ali Bin Aiwi | OCR of Mohd Ali Bin Alwi (already in JSON) |
| 24 | Rahmat Bin Kenap A1-Haj | Already in Speaker table at parl=1 |
| 24 | Tay Eng Soon, P.B.m. | Tay Eng Soon in Speaker at parl=5+, not LA era |

**Known noise categories (filter before researching):**
- Decorated variants with post-nominals: `Thio Chan Bee. J.P.`, `Lim Yew Hock. S.M.N.`
- Malformed truncated names with unmatched parens: `Yeoh Ghim Seng (Joo Chiat`
- Role/ministry strings: `Ministry of Labour and Government Whip`, `Minister of Defence`
- OCR of names already in JSON: `Gob Chew Chua` → `Goh Chew Chua`, `Leong Keng Sung` → `Leong Keng Seng`
- Post-LA era MPs whose Hansard OCR corrupts their name: often appear in colonial volumes during visits

---

# Method

## Setup (run once if `progress-research.txt` is absent)

**Step 1 — Generate the current candidate list.**

```bash
PYTHONPATH=. poetry run python3 scripts/find_unmatched_attendees.py \
    --json /tmp/la_candidates.json --verbose
```

Record the `candidates` bucket count and distinct name count in
`docs/speech-speaker/progress-research.txt` under `## Setup — Baseline`.

**Step 2 — Validate the noise filters.**

Before classifying candidates, verify that `find_unmatched_attendees.py`'s built-in noise filters are correctly scoped for this corpus. For each category, inspect 3–5 candidates that were *excluded* and confirm they are genuinely noise:

- **Presiding officer filter**: check that no genuine LA members are dropped because their name begins with a presiding-officer prefix.
- **Allcaps header filter**: colonial-era OCR frequently renders names in allcaps — confirm that 3–5 allcaps-excluded strings are headers, not member names.
- **Document noise filter**: confirm that 3–5 excluded strings are not role or ministry strings that double as legitimate attendance entries.

If any filter is too broad or too narrow, adjust it in `find_unmatched_attendees.py`, regenerate the candidate list, and record findings in `progress-research.txt` under `## Setup — Filter validation` before proceeding.

**Step 3 — Filter and classify.**

Load `/tmp/la_candidates.json`. Remove:
1. Names already in `data/colonial_la_members.json` (exact match)
2. OCR variants of existing JSON entries: if the first whitespace-delimited token of the candidate name matches the first token of any existing JSON entry (case-insensitive), flag as a likely OCR variant and confirm manually before researching further
3. Role/ministry strings (contain no plausible person name tokens)
4. Malformed truncated names (unmatched parentheses)
5. Decorated variants of existing JSON entries (post-nominals: `.J.P.`, `.B.B.M.`, `.S.M.N.`)

**Step 4 — DB pre-check.**

For each remaining candidate, run a targeted Speaker table lookup:

```python
PYTHONPATH=. poetry run python3 - <<'EOF'
from sqlmodel import Session, select
from database.init import engine
from database.speaker import Speaker
with Session(engine) as s:
    rows = s.exec(select(Speaker).where(Speaker.name.ilike("%PARTIAL%")).limit(10)).all()
for r in rows: print(r.id, r.name, r.party, r.parliament_number)
EOF
```

A match at `parliament_number` 1, 2, or 3 means the fallback will find this person.
Mark as `already_resolved` — no JSON entry needed. Record in `progress-research.txt`.

**Step 5 — Rank the research queue.**
Sort remaining candidates by frequency (descending). These are the only names worth
researching. Write the ranked list to `progress-research.txt` under `## Setup — Research queue`.

---

## Loop

The authoritative iteration count is the number of `## Iteration N` headings in
`docs/speech-speaker/progress-research.txt`.

**Step 1 — Pick the top unresearched candidates.**
Take the top 5–10 by frequency from the research queue that have not been attempted
in a prior iteration.

**Step 2 — Research each candidate.**

For each name:

1. **Web-search:** `"<name>" Singapore Legislative Assembly` and `"<name>" Singapore Infopedia`
2. **Confirm:** was this person an elected or nominated LA member (not a visitor, clerk,
   or official without a seat)? Minimum evidence: explicit identification as an LA member
   in at least one of — Singapore Infopedia, parliament.gov.sg, or a published academic
   or government source on the LA. Appearing in a news article, being mentioned in a
   Hansard debate, or being associated with a government ministry is not sufficient. If
   the only source is ambiguous ("attended a session", "associated with the Assembly"),
   log as unconfirmable.
3. **If confirmed:** produce a JSON entry. Use the name form that matches how the person
   appears in Hansard (check Attendance table if unsure):
   ```python
   PYTHONPATH=. poetry run python3 - <<'EOF'
   from sqlmodel import Session, select
   from database.init import engine
   from database.attendance import Attendance
   with Session(engine) as s:
       rows = s.exec(
           select(Attendance.speaker_name)
           .where(Attendance.speaker_name.ilike("%PARTIAL%"))
           .limit(20)
       ).all()
   print(rows)
   EOF
   ```
4. **If unconfirmable:** record as `unconfirmable — <reason>`. Do not guess.
   A missed match is better than a wrong attribution.
5. **If OCR artifact of a Speaker-table entry:** note the variant and the canonical name.
   Do not add to JSON. The fix belongs in the name-resolution pipeline, not here.

**Step 3 — Update `data/colonial_la_members.json`.**
Append confirmed entries. Format:

```json
{"name": "Canonical Name", "party": "Party Name",
 "parliament_number": 1, "is_legislative_assembly": true, "comments": null}
```

**Step 4 — Load and log findings.**
Run the loader:

```bash
PYTHONPATH=. poetry run python3 scripts/load_colonial_la_speakers.py
```

Prepend a new entry to `docs/speech-speaker/progress-research.txt` using this template:

```
## Iteration N — YYYY-MM-DD

**Candidates researched:** <list of names attempted>

**Confirmed and added:**
- <name> | <party> | source: <URL or reference>
- ...

**Unconfirmable:**
- <name> — <reason>

**OCR artifacts / already resolved:**
- <candidate form> → <canonical> (already in Speaker table at parl=X)

**Outcome:** ADDED / SKIPPED
- Entries added: N
- Speaker rows inserted: N
- Candidates bucket: before → after (run verify step below)
```

**Step 5 — Verify improvement.**
Run the scout in the background and wait for the notification:

```bash
PYTHONPATH=. poetry run python3 scripts/find_unmatched_attendees.py --verbose
```

Record the new `candidates` bucket count in the iteration log.

If the count did not decrease after adding confirmed entries (not merely unconfirmable ones), do not log as complete and move on — investigate first:
1. Query the `Attendance` table for the candidate name to confirm the exact `speaker_name` form used in the DB.
2. Compare it against the `name` field in `colonial_la_members.json` (case, spelling, ordering).
3. Correct the JSON entry if the form doesn't match, re-run the loader, and re-check the bucket before closing the iteration.

If the count did not decrease because all candidates this iteration were unconfirmable, that is expected — log it as `SKIPPED` and continue.

**Step 6 — Check completion.**
Stop and report when any of the following is true:

1. All remaining candidates with frequency ≥ 5 have been researched.
2. All remaining high-frequency candidates are confirmed OCR artifacts or post-LA MPs
   (i.e. the ceiling has been reached for this approach).
3. The `candidates` bucket has stopped decreasing for 2 consecutive iterations despite
   genuine research attempts.

At that point, compile a ceiling report: how many candidates remain, why they cannot
be resolved via JSON additions, and what pipeline fix (if any) would address them.

---

# Ceiling and Pipeline Fix Candidates

Names that are OCR corruptions of Speaker-table entries cannot be fixed by adding JSON
entries — the corrupted form will still fail name matching. These require a different
fix. Track them here for the pipeline fix loop.

**Known pipeline fix candidates (from session 1):**

| OCR form | Canonical | Freq | Speaker table status |
|---|---|---|---|
| `Lai Tha Chai` | `Lai Tai Chai` | 1024 | parl=3,4,5,6 — NOT parl=1 or 2; may also need parl=1 JSON entry |
| `lbrahim Othman` | `Ibrahim Othman` | 51 | parl=6+ — not colonial |
| `Gob Keng Swee` | `Goh Keng Swee` | 9 | parl=1 ✓ — name mismatch only |
| `Gob Chew Chua` | `Goh Chew Chua` | 9 | in JSON ✓ — name mismatch only |
| `Leong Keng Sung` | `Leong Keng Seng` | 7 | in JSON ✓ |
| `Yong Nyuk Lm` | `Yong Nyuk Lin` | 10 | parl=1 ✓ |
| `Chin Ham Tong` | `Chin Harn Tong` | 113 | parl=3 only — not colonial |

The `Lai Tha Chai` case is ambiguous: if Lai Tai Chai served in the LA era (1955–1963)
before appearing in parliament.gov.sg records, a `parliament_number=1` JSON entry for
`Lai Tai Chai` would resolve all 1,024 occurrences. Investigate this first — it is the
highest-impact single action remaining.

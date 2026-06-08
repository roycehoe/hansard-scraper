# Speaker Attribution Improvements

Fixable gaps in `speaker_id` resolution for `Speech` and `Attendance` rows, ordered by effort.

Current state (post `populate_speaker_links` run):

| Table | Unmatched | Total | Match rate |
|---|---|---|---|
| `speech` | 98,534 | 484,156 | 79.6% |
| `attendance` | 30,632 | 96,327 | 68.2% |

---

## Fix 1 — Loop `strip_title` until stable

**File:** `services/attendance.py`
**Estimated impact:** ~2,951 speech rows

`strip_title` removes the first matching prefix and returns. Stacked titles like
`Assoc. Prof. Dr Yaacob Ibrahim` or `RAdm [NS] Lui Tuck Yew` only get one prefix
stripped; the remainder fails all resolution strategies.

```python
def strip_title(text: str) -> str:
    while True:
        for prefix in _TITLE_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        else:
            return text
```

`[NS]` is in `_TITLE_PREFIXES` but only matches at the start of a string. After
`RAdm ` is stripped, `[NS]` is at the start and a second pass catches it. For
`Assoc. Prof. Dr`, the second pass removes `Dr `. Zero regression risk — strictly
a superset of current behaviour.

Top affected speakers: `Assoc. Prof. Dr Yaacob Ibrahim` (2,328), `Assoc Prof Dr
Yaacob Ibrahim` (330), `RAdm [NS] Lui Tuck Yew` (384).

---

## Fix 2 — Use `strip_title` to detect parenthetical titles in speech resolution

**File:** `populate/speaker_links.py`
**Estimated impact:** ~3,000–4,000 speech rows

`_INNER_TITLE` is a hardcoded regex of honorific prefixes that excludes `BG`,
`RAdm`, `MG`, `Assoc. Prof.`, and others. When the speaker string is a role with
a parenthetical name — `The Minister for Education (RAdm Teo Chee Hean)` — the
inner text doesn't match `_INNER_TITLE`, so `raw` is trimmed to `The Minister for
Education` instead of `RAdm Teo Chee Hean`, and resolution fails.

Replace `_INNER_TITLE` with a call to the already-existing `strip_title`:

```python
# Current (speaker_links.py ~line 121):
if _INNER_TITLE.match(inner):
    raw = inner
else:
    raw = raw[: m.start()]

# Proposed:
if strip_title(inner) != inner:   # inner starts with a recognised title prefix
    raw = inner
else:
    raw = raw[: m.start()]
```

`_TITLE_PREFIXES` covers `BG `, `RAdm `, `MG `, `Assoc. Prof. `, and 30 others,
so this stays in sync automatically. The `_INNER_TITLE` regex can then be removed.

Top affected speakers:
- `The Senior Minister of State for Law (Assoc. Prof. Ho Peng Kee)` — 938 rows
- `The Senior Minister of State for Home Affairs (Assoc. Prof. Ho Peng Kee)` — 889 rows
- `The Deputy Prime Minister (BG Lee Hsien Loong)` — 993 rows
- `The Minister for Education (RAdm Teo Chee Hean)` — 788 rows
- `The Minister for Trade and Industry (BG George Yong-Boon Yeo)` — 482 rows
- `The Minister for Information and the Arts (BG George Yong-Boon Yeo)` — 397 rows
- `The Minister for the Environment and Water Resources (Assoc. Prof. Dr Yaacob Ibrahim)` — 709 rows

Note: Fix 1 (looping `strip_title`) should be applied first so that compound
prefixes like `Assoc. Prof. Dr` are fully stripped from the extracted inner name.

---

## Fix 3 — Wordset subset matching for names with middle initials

**File:** `services/attendance.py` (`resolve_canonical_name`)
**Estimated impact:** ~1,000–2,000 speech rows

The wordset lookup requires an exact word count match. Speaker names that omit a
middle initial fail to match the canonical `speaker.name` which includes one:

- `Dr Aline Wong` → after title strip → `Aline Wong` (2 words); `mp.name = Wong Aline K` → natural form `Aline K Wong` (3 words) → `frozenset({aline, wong}, 2)` ≠ `frozenset({aline, wong, k}, 3)`
- `Dr Augustine Tan` → `Augustine Tan` (2 words); `mp.name = Tan H.H. Augustine` → natural form `Augustine H.H. Tan` → non-initial words `{augustine, tan}` (2 words)

Add an initial-stripped fallback after the existing wordset lookup in
`resolve_canonical_name`:

```python
# After the existing wordset lookup fails:
words = _period_normalize(name).split()
non_initial = [w for w in words if len(w) > 1]
if len(non_initial) < len(words):   # initials were present
    ws = frozenset(non_initial)
    canonical = wordset.get((ws, len(non_initial), parliament))
if canonical:
    return canonical
```

The `_get_wordset_lookup` builder also needs a parallel set of entries keyed on
non-initial words so the lookup table contains entries to match against:

```python
# In _get_wordset_lookup, alongside the existing entry:
non_initial_words = [w for w in words if len(w) > 1]
if len(non_initial_words) < len(words):
    ni_key = (frozenset(non_initial_words), len(non_initial_words), parl)
    counts_ni[ni_key] = counts_ni.get(ni_key, 0) + 1
    entries_ni.append((ni_key, canonical_speaker_name))
# Add only unambiguous ni_key entries to _WORDSET_LOOKUP
```

Top affected: `Dr Aline Wong` (676 speeches), `Dr Augustine Tan` (1,482 speeches).

---

## Fix 4 — Parliament→Speaker role mapping

**File:** `populate/speaker_links.py` (`_populate_speech_speaker_ids`)
**Estimated impact:** ~17,000–18,000 speech rows

`Mr Speaker` (14,801 speeches) and `Mr Deputy Speaker` (2,590 speeches) are
presiding officers who are MPs, but the speaker string carries no individual name
so the resolution cascade finds nothing.

The `attendance` table already records the Speaker per sitting (parsed via
`_parse_speaker_line` as the `SPEAKER` role). A parliament→Speaker lookup can be
derived directly from this data:

```sql
SELECT sa.speaker_name, s.parlement_no, count(*) AS n
FROM attendance sa
JOIN sitting s ON sa.sitting_id = s.id
WHERE sa.speaker_name NOT IN ('SPEAKER', '')
  AND (s.markdown_content LIKE '%SPEAKER%')
GROUP BY sa.speaker_name, s.parlement_no
ORDER BY s.parlement_no, n DESC;
```

From the results, build a hardcoded `{parliament: speaker_name}` dict (and a
parallel one for Deputy Speaker). In `_populate_speech_speaker_ids`, before the
existing resolution cascade, add:

```python
_SPEAKER_BY_PARLIAMENT: dict[int, str] = {
    # to be filled from query above
    8: "Tan Soo Khoon",
    9: "Abdullah Tarmugi",
    ...
}

if raw in ("Mr Speaker", "Mdm Speaker"):
    resolved_name = _SPEAKER_BY_PARLIAMENT.get(parliament)
    if resolved_name:
        canonical = resolve_canonical_name(resolved_name, parliament)
```

The Deputy Speaker role is harder because it changed multiple times within a
parliament; a finer-grained date→person lookup would be needed there. The Speaker
(lower turnover) is tractable with a per-parliament dict.

---

## Structural limits

These categories cannot be resolved by pipeline changes alone.

| Category | Rows | Reason |
|---|---|---|
| `The Prime Minister`, `The Minister for X` (no parenthetical) | ~3,128 | No name in the string; requires a date-range→person timeline table built from external sources |
| Colonial-era names (parliaments 0–3, pre-1965) | ~8,000 speech, ~3,945 attendance | Not in the `speaker` table; `scrape_speakers_by_parliament.py` only covers post-independence records |
| `The President` | small | Constitutionally not a speaker; `speaker_id` will always be null |
| `An hon. Member`, `Hon. Members` | ~1,109 | Anonymised by design in the Hansard source |

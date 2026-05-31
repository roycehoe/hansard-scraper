# No-Speech Doc Attribution

## Background

The speech parsing pipeline (`services/speech.py::get_speeches`) identifies 1,449 docs as
"no-speech" — docs where a start line was found but `get_speeches` returns an empty list.
These were excluded from the speaker/transcript quality target (see `docs/progress.txt` Iteration 6).

The refine-loop exclusion rationale was: "zero speeches is correct for these — they have no
speaker markup." This is technically true but misses the point: **every entry in the Hansard
was authored by a parliamentary member**, and the Hansard records who that member is.

The goal of the pipeline is to map every word recorded in the Hansard back to the member who
spoke or wrote it. That goal is not met for these 1,449 docs.

---

## Where the Attribution Lives

Every `HandsardWebsiteResponse.content` HTML document contains an `MPs Speaking` / `MP_Speak`
field — either as an HTML `<meta>` tag (old format) or as a table row (new format). This field
is already carried through to the markdown header by `get_cleaned_handsard_markdown` as:

```
MPs Speaking:| Name1; Name2; ...
```

This is the Hansard's own attribution for the record. It names the member(s) who moved,
presented, or authored the item.

---

## Population Breakdown

Total no-speech docs: **1,449**

| `MPs Speaking` count | Total | Notes |
|----------------------|-------|-------|
| 0 (empty) | 3 | Nothing to attribute |
| 1 (single) | 1,193 | Attributable — see below |
| 2+ (multi) | 253 | Not attributable — see below |

### By `report_type`

| type | zero | single | multi |
|------|------|--------|-------|
| `motion` | 0 | 334 | 15 |
| `bill` | 1 | 335 | 9 |
| `budget` | 0 | 218 | 69 |
| `atbp` | 2 | 143 | 0 |
| `oral-answer` | 0 | 8 | 76 |
| `speaker` | 0 | 63 | 1 |
| `president-address` | 0 | 44 | 4 |
| `written-answer` | 0 | 2 | 46 |
| `ministerial-statement` | 0 | 13 | 30 |
| `bill-intro` | 0 | 26 | 0 |
| `misc` | 0 | 7 | 0 |
| `written-answer-na` | 0 | 0 | 2 |
| `yang-di-message` | 0 | 0 | 1 |

---

## Single-Speaker Docs (1,193) — Attributable

Body text is short procedural content authored by the single named member:

- **Adjournment motions** — `"That Parliament do now adjourn." − [Mr Gan Kim Yong]`
- **Bill First Readings** — `"presented by the Minister for Home Affairs (Mr Wong Kan Seng); read the First time…"`
- **Procedural resolutions** — President's concurrences, oaths, etc.

The `MPs Speaking` name IS the author. The body text IS their contribution.

**Example** (`motion`, parl 12, `id=20452`):
```
MPs Speaking:| Mr Gan Kim Yong
...
# Adjournment
Resolved, "That Parliament do now adjourn." − [Mr Gan Kim Yong].
_Adjourned accordingly at 6.59 pm._
```

---

## Multi-Speaker Docs (253) — Not Attributable

Body text is a PDF annex/table link index with no prose. The multiple names in `MPs Speaking`
are session participants, not authors of the annex document itself.

**Example** (`oral-answer`, parl 10, `id=25173`):
```
MPs Speaking:| Mr Lee Hsien Loong; Dr Amy Khor; Dr Lily Neo; Mr Gan Kim Yong; ...
Title: ANNEX - ECONOMIC RESTRUCTURING SHARES
---
[Annex - Singaporeans who did not qualify for ERS (Cols. 2273-2274)](url)
```

**Example** (`budget`, parl 10, `id=25152`):
```
MPs Speaking:| Mr Lee Hsien Loong; Mr Abdullah Tarmugi (Mr Speaker);
Title: APPENDIXES - ANNUAL BUDGET STATEMENT
---
[ANNEX A - CHANGES TO EXCISE DUTIES FOR PETROL (Cols. 117-118)](url)
[ANNEX B - UTILITIES SAVE REBATES (Cols. 117-118)](url)
...
```

All four multi-speaker types (`oral-answer`, `budget`, `written-answer`,
`ministerial-statement`) follow this pattern: the body is an index of PDF links, not speech.
Attributing these to any individual would be fabrication.

---

## Recommendation

Add a fallback path to `get_speeches` in `services/speech.py`:

> When `get_speeches` would return `[]`, check the markdown header for a single name in
> `MPs Speaking:`. If exactly one name is present, return
> `[Speech(speaker=that_name, transcript=<body lines joined>)]`.

This covers the 1,193 single-speaker docs cleanly. The 253 multi-speaker docs and 3
zero-speaker docs are left as-is (no speeches) — their body content is not attributable
prose.

### Expected outcome

- No-speech docs drop from 1,449 to ~256 (253 multi + 3 zero).
- 1,193 previously-unattributed records gain a correct speaker attribution.
- No fabricated attributions.

### Implementation sketch

In `services/speech.py`, extract the helper:

```python
_MP_SPEAK_RE = re.compile(r"MPs? Speaking:\|\s*([^\n|]+)", re.IGNORECASE)

def _extract_single_speaker(markdown: str) -> Optional[str]:
    """Return the single MP name from the MPs Speaking header, or None."""
    m = _MP_SPEAK_RE.search(markdown)
    if not m:
        return None
    names = [n.strip() for n in m.group(1).split(";") if n.strip()]
    return names[0] if len(names) == 1 else None
```

Then in `get_speeches`, after the main loop produces an empty list:

```python
if not speeches:
    speaker = _extract_single_speaker(markdown)
    if speaker:
        body = " ".join(
            line.strip()
            for line in markdown.splitlines()[start_of_speech_line + 1:]
            if line.strip() and line.strip().strip("* ")
        )
        if body:
            return [Speech(speaker=speaker, transcript=body)]
```

### What to verify after implementing

- Regression set (30 docs, all currently passing) still passes.
- A sample of the 1,193 newly-attributed docs shows correct speaker names and
  non-empty, plausible transcripts.
- Multi-speaker docs still return `[]` (fallback does not fire for them).
- Zero-speaker docs still return `[]`.

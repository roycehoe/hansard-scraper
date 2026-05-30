# Parsing Refinement Learnings

## Setup

- **Baseline:** 15272/21826 (70.0%) pass rate across all report types with markdown, excluding `bill-intro`
- **No-speech types excluded:** `bill-intro` (28 docs with markdown, 0 speeches — these are formal bill-reading notices, not speech transcripts)
- **Only failure stage:** `has_start_line` (6554 failures). `can_get_speeches` failures = 0.
- **Failure breakdown by type:**
  - `budget`: 2186 failing / 2370 with markdown (92.2% fail rate)
  - `president-address`: 424 / 438 (96.8%)
  - `atbp`: 338 / 403 (83.9%)
  - `speaker`: 243 / 335 (72.5%)
  - `motion`: 680 / 2077 (32.7%)
  - `written-answer`: 578 / 2059 (28.1%)
  - `oral-answer`: 382 / 7572 (5.0%)
  - others: small counts

---

## Iteration 1

### has_start_line — oral-answer, written-answer, motion, budget, president-address — title appears as markdown `# heading` in Parliament 12+ (2012+) documents

**Affected report IDs (sample):** 19984, 20002, 20027 (oral-answer); 19975, 19985, 19986 (written-answer); 20475, 20067 (motion); 20362, 20363, 20366 (budget); 20826, 20847, 20851 (president-address)

**Markdown snippet (failing — oral-answer, 2012):**
```
| Parliament No:| 12  
...
# Update on National Research Foundation's Work
1 **Dr Lim Wee Kiak** asked the Prime Minister ...
**The Deputy Prime Minister ... (Mr Teo Chee Hean) (for the Prime Minister)** : ...
```

**Markdown snippet (failing — oral-answer with italic in heading, 2012):**
```
# Impact of Livestock Export Rule Changes on the Annual Observance of _Korban_ in Singapore
6 **Assoc Prof Fatimah Lateef** asked the Minister ...
```

**Markdown snippet (passing — oral-answer, 2009):**
```
****
**ILLEGAL MONEYLENDERS AND RUNNERS**

12\. **Mdm Cynthia Phua** asked the Deputy Prime Minister ...
```

**Why it fails:**
`get_start_of_speech_line` checks for `{title}**` (bold marker at end) in each line. New-format documents (Parliament 12+, 2012 onwards) have the title as a markdown h1 heading (`# Title`), which contains no `**` markers. The function scans the entire document and finds nothing.

**Proposed fix:**
After the existing bold-title checks, add a check: if the line starts with `#`, strip the `#` prefix and markdown emphasis markers (`_`, `*`), then compare case-insensitively against `title`, `f"{title} {subtitle}"`, and `original_title` (with newlines replaced by spaces). Return that line index if matched.

This is purely additive — old-format documents never have a bare `# Title` line that matches the document title (their title is in bold), so no regressions are expected.

**Net outcome:** Applied in iteration 1. See post-patch statistics below.

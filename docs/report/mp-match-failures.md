# MP Match Failure Analysis

After `populate_mp_links` ran, the following records still have `mp_id IS NULL`:

| Table | Unmatched | Total | Match rate |
|---|---|---|---|
| `sittingattendance` | 30,632 | 96,327 | 68.2% |
| `speech` | 98,534 | 484,156 | 79.6% |

---

## SittingAttendance Failures

### Root Cause Breakdown

| Root cause | Rows | Notes |
|---|---|---|
| Parliament 0 — no MPs in db (volumes 12–23) | 7,751 | `VOLUME_TO_PARLIAMENT` maps volumes 12–23 to parliament 0, which has no rows in the `mp` table |
| Case mismatch (`bin` vs `Bin`) | 1,457 | Sitting attendance records store `bin` lowercase; `mp.name` uses title-cased `Bin` |
| Name absent from `mp` table | 21,424 | Person exists in history but `mp.name` is a different format, or is genuinely not scraped |

**Total: 30,632**

### Root Cause 1 — Parliament 0 (7,751 rows)

`infer_parliament` looks up `sitting.volume_no` in `VOLUME_TO_PARLIAMENT`. Volumes 12–23 are mapped to parliament 0, but no `Mp` rows exist for `parliament_number = 0`. Every attendance row tied to those volumes therefore fails the `mp_id_lookup.get((mp_name, 0))` call unconditionally.

These volumes correspond to a transitional era (post-Legislative Assembly, pre-Parliament renumbering). The root fix is either to create `Mp` rows for parliament 0 or to adjust the volume→parliament mapping.

### Root Cause 2 — Case mismatch (1,457 rows)

The attendance lookup is a raw dict key comparison: `mp_id_lookup.get((record.mp_name, parliament))`. No case normalisation is applied to `record.mp_name` before the lookup. MPs of Malay heritage are frequently stored in `sittingattendance` with lowercase `bin`/`binte` while `mp.name` uses uppercase `Bin`/`Binte`.

Top offenders:

| `mp_name` in sittingattendance | `mp.name` | Rows |
|---|---|---|
| `Sidek bin Saniff` | `Sidek Bin Saniff` | 552 |
| `Othman bin Haron Eusofe` | `Othman Bin Haron Eusofe` | 480 |
| `Rohan bin Kamis` | `Rohan Bin Kamis` | 97 |
| `Othman bin Wok` | `Othman Bin Wok` | 94 |
| `Rahmat bin Kenap` | `Rahmat Bin Kenap` | 92 |
| `Sha'ari bin Tadin` | `Sha'ari Bin Tadin` | 91 |

Fix: apply `LOWER()` on both sides of the attendance lookup, or normalise `mp.name` and `record.mp_name` to a common case before matching.

### Root Cause 3 — Name format mismatch or truly absent (21,424 rows)

This bucket breaks into three sub-types:

**3a — Format differs, person IS in `mp` table (~12,089 rows)**

The attendance name matches a real MP but uses a different surface form than `mp.name`. The attendance matching code performs no name normalisation at all (unlike the speech code), so these all fail. Common patterns:

- Period vs no-period initials: `S. Jayakumar` → `S Jayakumar`; `K. Shanmugam` → `K Shanmugam`; `J.B. Jeyaretnam` → `J B Jeyaretnam`
- Inverted format: `E.W. Barker` → `Barker, E.W.`; `Augustine H.H. Tan` → `Tan H.H. Augustine`; `Aline K. Wong` → `Wong Aline K`; `George Yong-Boon Yeo` → `Yeo Yong-Boon, George`
- Missing `Bin`: `Abdullah Tarmugi` → `Abdullah Bin Tarmugi`; `Othman Haron Eusofe` → `Othman Bin Haron Eusofe`
- Missing title suffix: `Ong Chit Chung` → `Ong Chit Chung, Dr`; `Mohd Ariff Bin Suradi` → `Mohd Ariff Bin Suradi, Haji`

Fix: apply the same normalisation pipeline used for speech (strip_title → normalize_name → resolve_canonical_name) to attendance `mp_name` before lookup.

**3b — Colonial-era MPs not scraped (~3,945 rows in volumes 1–11)**

Parliament 1 volumes 1–11 contain pre-1965 Legislative Assembly sitting records. The names that appear (e.g. `Lim Ching Siong`, `D.S. Marshall`, `G.A.P. Sutherland`, `R. Jumabhoy`, `A.R. Lazarous`) are not in the `mp` table because `scrape_mps_by_parliament.py` only covers the post-independence parliament.gov.sg listings. These are structurally missing data.

**3c — Other absent names (~5,390 rows)**

Names spread across all parliaments that cannot be resolved even with format normalisation. Includes officials who attended sittings in non-MP roles (ministers, civil servants, foreign dignitaries), attendees recorded under nicknames or abbreviations, and genuine scraping gaps.

### Top 30 Unmatched `mp_name` Values

| Count | mp_name |
|---|---|
| 679 | Abdullah Tarmugi |
| 648 | Tony Tan Keng Yam |
| 581 | George Yong-Boon Yeo |
| 552 | Sidek bin Saniff |
| 539 | S. Jayakumar |
| 538 | Bernard Chen |
| 509 | Eugene Yap Giau Cheng |
| 504 | Ong Chit Chung |
| 480 | Othman bin Haron Eusofe |
| 454 | Low Seow Chay |
| 454 | John Chen Seow Phun |
| 442 | E.W. Barker |
| 427 | Augustine H.H. Tan |
| 417 | S. Vasoo |
| 416 | Aline K. Wong |
| 373 | K. Shanmugam |
| 370 | Mohamad Maidin B P M |
| 364 | S. Chandra Das |
| 309 | P. Selvadurai |
| 308 | Lai Tha Chai |
| 296 | Zulkifli bin Mohammed |
| 288 | J.F. Conceicao |
| 256 | Tan Boon Wan |
| 253 | Michael Lim Chun Leng |
| 253 | S. Ramaswamy |
| 245 | Goh Chew Chua |
| 245 | P. Govindaswamy |
| 237 | Ibrahim bin Othman |
| 237 | Kenneth Chen Koon Lap |
| 237 | R. Sinnakaruppan |

---

## Speech Failures

### Root Cause Breakdown

| Category | Rows | Description |
|---|---|---|
| Role-based "The X" speakers | 33,073 | `The Minister for…`, `The Prime Minister`, `The Chairman`, etc — not real names |
| All-caps section headers | 18,974 | `ADJOURNMENT`, `MINISTRY OF EDUCATION`, `ASSENTS TO BILLS PASSED`, etc — document structure leaked into speaker field |
| Presiding officers | 18,332 | `Mr Speaker`, `Mr Deputy Speaker`, `Mdm Deputy Speaker` — roles, not resolvable to individual MPs |
| Unresolved real names | 13,537 | Genuine speaker names that the resolution pipeline failed to match |
| Title + surname only | 4,970 | `Mr Shanmugam`, `Dr Vasoo`, `Mr Iswaran` — surname alone is unresolvable when multiple MPs share it |
| Bracket artifacts | 3,345 | `[Mr Deputy Speaker (Mr Matthias Yao Chih) in the Chair]` — presiding-officer change notices |
| Compound title not fully stripped | 2,951 | `Assoc. Prof. Dr Yaacob Ibrahim`, `RAdm [NS] Lui Tuck Yew` — `strip_title` removes only one prefix per call |
| Non-speaker placeholders | 1,109 | `An hon. Member`, `Hon. Members`, etc — already in the `_NON_SPEAKERS` exclusion set but still unmatched |
| Underscore artifacts | 2,243 | `_something` — parse artefacts |

**Total: 98,534**

### Distribution by Parliament

| Parliament | Unmatched speeches |
|---|---|
| 0 (pre-parliament) | 8,282 |
| 1 | 701 |
| 2 | 833 |
| 3 | 3,867 |
| 4 | 5,488 |
| 5 | 5,876 |
| 6 | 11,508 |
| 7 | 6,213 |
| 8 | 10,552 |
| 9 | 12,468 |
| 10 | 15,741 |
| 11 | 14,523 |
| 12 | 2,482 |

Failures are concentrated in parliaments 9–11 (volumes 67–87), which are the highest-volume periods. The absolute unmatched count is high there even though the per-parliament match rate is reasonable.

### Category Details

**Category: Role-based "The X" speakers (33,073)**

Speakers like `The Prime Minister (BG Lee Hsien Loong)` and `The Senior Minister of State for Law (Assoc. Prof. Ho Peng Kee)` carry role text before the parenthetical name. The current `_INNER_TITLE` regex in `mp_links.py` extracts the name from the parenthetical only when it starts with a known title prefix (`Mr`, `Mrs`, `Dr`, etc.). This works for `The Deputy Prime Minister (BG Lee Hsien Loong)` but leaves cases where the role prefix (`The Minister for…`) is itself the entire speaker string without a parenthetical.

Top examples:
- 14,801 × `Mr Speaker`
- 10,578 × `The Chairman`
- 3,128 × `The Prime Minister`
- 2,590 × `Mr Deputy Speaker`
- 993 × `The Deputy Prime Minister (BG Lee Hsien Loong)` — parenthetical extraction should work but `BG` title resolves to `Lee Hsien Loong` who is in the mp table; the failure here suggests `BG` prefix is stripped but the resulting name `Lee Hsien Loong` doesn't match any `mp.name` exactly (stored as `Lee Hsien Loong` in the mp table — this is a parliament-range issue)

**Category: Compound title not fully stripped (2,951)**

`strip_title` iterates `_TITLE_PREFIXES` and returns after removing the **first** matching prefix. For stacked compound titles, the second title is left in place:

- `Assoc. Prof. Dr Yaacob Ibrahim` → after `strip_title` removes `Assoc. Prof. ` → `Dr Yaacob Ibrahim` → `strip_title` is not called again → `resolve_canonical_name('Dr Yaacob Ibrahim', parliament)` fails because `dr yaacob ibrahim` (3 words) does not match the 2-word wordset key for `Yaacob Ibrahim`
- `RAdm [NS] Lui Tuck Yew` → `strip_title` removes `RAdm ` → `[NS] Lui Tuck Yew` → `[NS]` is listed as a prefix but only matches at the start of a string; it is now mid-string and is not stripped

Top instances: `Assoc. Prof. Dr Yaacob Ibrahim` (2,328), `Assoc Prof Dr Yaacob Ibrahim` (330), `RAdm [NS] Lui Tuck Yew` (384).

Fix: call `strip_title` in a loop until no prefix is consumed, or add compound multi-prefix patterns like `Assoc. Prof. Dr ` directly to `_TITLE_PREFIXES`.

**Category: Title + surname only (4,970)**

Single-token surnames after title stripping: `Mr Shanmugam` → `Shanmugam`, `Dr Vasoo` → `Vasoo`. The resolution pipeline has no path for surname-only resolution unless a manual override exists (a few are in `_MANUAL_OVERRIDES`). Most are ambiguous across parliaments (multiple MPs with the same surname).

Top: `Mr Shanmugam` (696), `Mr Conceicao` (509), `Mr Iswaran` (518), `Mr Rajaratnam` (561).

**Category: Unresolved real names (13,537)**

Names that look like genuine speakers but failed all resolution strategies. Sub-types:

- **Name not in `mp` table at all** (colonial-era or missing from scrape): `Mr David Marshall`, `Mr Lim Cher Kheng`, `Mr Chew Swee Kee`, `Mr Francis Thomas`, `Tun Lim Yew Hock` — pre-independence figures
- **Inverted-name rearrangement failure**: `Dr Augustine Tan` → `Augustine Tan` → inverted lookup key is `augustine h h tan` (from `Tan H.H. Augustine`) but the candidate key is `augustine tan` — word sets differ because the middle initial `H.H.` is absent in the speech form
- **Word-count mismatch in wordset lookup**: `Dr Aline Wong` → `Aline Wong` (2 words) vs `mp.name = Wong Aline K` (3 words including middle initial) — wordset lookup requires exact word-count match
- **Name with constituency appended**: `Mr Lai Tha Chai (Henderson)` — parenthetical extraction in `mp_links.py` uses `_INNER_TITLE` regex and only extracts the inner content if it starts with a title prefix; `Henderson` does not, so `raw` is trimmed to `Mr Lai Tha Chai` and then resolved — but `Lai Tha Chai` is not in the `mp` table
- **All-caps noise that looks like names**: `EXEMPTED BUSINESS (Motion)` (330), `Total` (113), `Year` (106), `Country` (34) — document table content misdetected as speakers

### Top 30 Unmatched Speaker Values

| Count | speaker |
|---|---|
| 14,801 | `Mr Speaker` |
| 10,578 | `The Chairman` |
| 3,218 | `ADJOURNMENT` |
| 3,128 | `The Prime Minister` |
| 2,590 | `Mr Deputy Speaker` |
| 2,328 | `Assoc. Prof. Dr Yaacob Ibrahim` |
| 1,482 | `Dr Augustine Tan` |
| 993 | `The Deputy Prime Minister (BG Lee Hsien Loong)` |
| 938 | `The Senior Minister of State for Law (Assoc. Prof. Ho Peng Kee)` |
| 889 | `The Senior Minister of State for Home Affairs (Assoc. Prof. Ho Peng Kee)` |
| 862 | `[Mr Deputy Speaker (Mr Matthias Yao Chih) in the Chair]` |
| 848 | `ASSENTS TO BILLS PASSED` |
| 838 | `An hon. Member` |
| 788 | `The Minister for Education (RAdm Teo Chee Hean)` |
| 772 | `Hon. Members` |
| 709 | `The Minister for the Environment and Water Resources (Assoc. Prof. Dr Yaacob Ibrahim)` |
| 696 | `Mr Shanmugam` |
| 676 | `Dr Aline Wong` |
| 661 | `ASSENT TO BILLS PASSED` |
| 660 | `Dr Vasoo` |
| 606 | `The Minister for Trade and Industry (BG Lee Hsien Loong)` |
| 561 | `Mr Rajaratnam` |
| 546 | `[Mdm Deputy Speaker (Ms Indranee Rajah) in the Chair]` |
| 522 | `The Minister of State for Law (Assoc. Prof. Ho Peng Kee)` |
| 518 | `Mr Iswaran` |
| 509 | `Mr Conceicao` |
| 482 | `The Minister for Trade and Industry (BG George Yong-Boon Yeo)` |
| 443 | `MAIN AND DEVELOPMENT ESTIMATES OF SINGAPORE FOR THE` |
| 397 | `The Minister for Information and the Arts (BG George Yong-Boon Yeo)` |
| 384 | `RAdm [NS] Lui Tuck Yew` |

---

## Summary of Actionable Root Causes

### Not bugs — expected non-resolution

These account for roughly **72,500 speech rows** (73% of unmatched speeches) and are inherent to the data:

- Presiding-officer roles (`Mr Speaker`, `The Chairman`) — not individual MPs
- Role-only speaker strings (`The Prime Minister`, `The Minister for...`) without a name component
- All-caps document structure headers leaked as speakers
- Bracket/underscore parse artefacts
- `An hon. Member` placeholders
- Colonial-era names with no `Mp` row

### Fixable bugs or gaps

| Issue | Estimated affected rows | Fix |
|---|---|---|
| Attendance: no name normalisation applied | ~12,089 attendance | Apply `strip_title` + `resolve_canonical_name` to `mp_name` before attendance lookup |
| Attendance: case sensitivity (`bin` vs `Bin`) | 1,457 attendance | Normalise case before dict lookup |
| Attendance: parliament 0 has no `Mp` rows | 7,751 attendance | Populate `Mp` rows for parliament 0, or remap affected volumes |
| Speech: `strip_title` called once — compound prefixes (`Assoc. Prof. Dr`) not fully stripped | ~2,951 speech | Loop `strip_title` until stable, or add compound entries to `_TITLE_PREFIXES` |
| Speech: word-count mismatch in wordset lookup for names with/without middle initial | ~1,000+ speech | Extend wordset lookup to allow subset matching for names with middle initials |
| Speech: inverted rearrangement misses middle-initial forms (`Dr Augustine Tan` vs `Tan H.H. Augustine`) | ~1,482 speech | Add to `_MANUAL_OVERRIDES`, or add bin-free + initial-stripped fallback |

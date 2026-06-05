# Attendance → Speaker ID Gap: 202 Unresolved Rows

## Context

The attendance pipeline (`populate_attendances` → `populate_speaker_links`) achieves 99.8%
speaker_id resolution on the production database (96,298 / 96,500 rows). The remaining
202 unmatched rows all fall into the colonial bucket — sittings where
`COALESCE(sitting.parlement_no, 0) = 0`.

This document details what those 202 rows actually are, why they remain unmatched, and
what paths exist to resolve them.

---

## Environment

```bash
# All Python commands must use:
DATABASE_URL="..." PYTHONPATH=. poetry run python3 ...

# DATABASE_URL is in .env at project root (DigitalOcean managed Postgres)
# Use poetry run — bare python lacks the virtualenv
```

---

## Parliament number convention — critical

Two different `parliament_number` contexts exist in this codebase:

| Context | Value | Meaning |
|---|---|---|
| `Sitting.parlement_no` / `VOLUME_TO_PARLIAMENT` result | `0` | Colonial LA era (1955–1965) |
| `Speaker.parliament_number` / `colonial_la_members.json` | `1` | LA-era elected/nominated members |
| `Speaker.parliament_number` | `0` | Pre-1955 Municipal Commission only (extremely rare) |

The resolution cascade in `populate/speaker_links.py` handles parl=0 sittings by falling
back through `_COLONIAL_PARLIAMENT_FALLBACKS = [1, 2, 3]` when looking up Speaker rows.

---

## What the 202 rows actually are

**Important:** The query `COALESCE(sitting.parlement_no, 0) = 0` captures two distinct
populations:
1. Genuinely colonial-era sittings (volumes 12–26, `VOLUME_TO_PARLIAMENT` → 0 or 1–2)
2. Modern sittings where `parlement_no IS NULL` and `volume_no` maps to a modern parliament

Some of the 202 rows are from population 2 — modern-era role strings / document noise
appearing in sittings with a NULL `parlement_no`. Verify volume_no when investigating.

### Full list of unmatched `speaker_name` values (with frequency)

| Freq | speaker_name | Likely category |
|---|---|---|
| 9 | `Speaker` | Role string / presiding officer not resolved |
| 7 | `Minister for the Environment and Water Resources and Deputy Government Whip` | Modern-era role string — parsing failure |
| 6 | `\| _Parliament of Singapore_` | Document noise — parsing failure |
| 6 | `for Community Development, Youth and Sports and Minister for Transport` | Truncated role — parsing failure |
| 6 | `\| _Speaker,_` | Document noise — parsing failure |
| 5 | `\| \|` | Document noise |
| 3 | `Speaker, preceded by the Serjeant at Arms` | Procedural text — parsing failure |
| 3 | `Minister for Security and Defence, Prime Minister's Office` | Role string |
| 3 | `for Defence and Deputy Leader of the House` | Truncated role |
| 3 | `Resources and Deputy Government Whip` | Truncated role |
| 3 | `Ministry of Labour and Government Whip` | Role string |
| 3 | `Second Minister for Information, Communications and the Arts` | Role string |
| 3 | `2.30 p.m` | Document noise |
| 3 | `I have been informed by the President that…` | Procedural text |
| 3 | `Minister for Education and Minister for Home Affairs` | Role string |
| 3 | `Water Resources and Minister-in-charge of Muslim Affairs` | Role string |
| 3 | `SPEAKER` | Role string — case variant of presiding officer |
| 2 | `to the Minister for Home Affairs and Minister for the Environment` | Truncated role |
| 2 | `Parliamentary Secretary to the Minister for Culture` | Role string |
| 2 | `The following Bills were assented to by the President…` | Procedural text |
| 2 | `16th March, 1967` | Date — document noise |
| 2 | `Education and Ministry of Information, Communications and the Arts` | Truncated role |
| 2 | `Punch Coomaraswamy, Deputy Speaker` | OCR variant — Speaker table has `Coomaraswamy, P.` |
| 2 | `\|  _Parliament of Singapore_` | Document noise |
| 2 | `A.V. Winslow` | Possible colonial member — unconfirmable (see research history) |
| 2 | `C.V. Devan Nair` | Likely in Speaker table under different form — check |
| 1 | `Community Development, Youth and Sports` | Truncated role |
| 1 | `Culture` | Truncated role |
| 1 | `Development and Deputy Government Whip` | Truncated role |
| 1 | `Development and Sports and Minister-in-charge of Muslim Affairs` | Truncated role |
| 1 | `Development Loan Bill` | Bill title — parsing failure |
| 1 | `Development, Youth and Sports and Second Minister…` | Truncated role |
| 1 | `DL Chiang Hai Ding` | OCR: `DL` prefix → should be `Dr`/`Mr` — `Chiang Hai Ding` in Speaker table |
| 1 | `DR Yeoh Ghim Seng` | OCR: `DR` all-caps prefix — `Yeoh Ghim Seng` in Speaker table |
| 1 | `E.P. Shanks, Q.C. Attorney-General` | Colonial official — manual override `("shanks", 1)` exists but parl may not resolve |
| 1 | `er for Community Development, Youth and Sports` | Truncated role — parsing failure |
| 1 | `for Information, Communications and the Arts` | Truncated role |
| 1 | `for Trade and Industry and Acting Minister…` | Truncated role |
| 1 | `Goh Keng Swee Kreta Ayer) Minister for Finance` | OCR: role+constituency appended — `Goh Keng Swee` in Speaker table |
| 1 | `Hwang Soo un` | OCR: `un` → `Jin` — `Hwang Soo Jin` in Speaker table |
| 1 | `I have been informed by the President: that…` | Procedural text |
| 1 | `Inche. Buang Bin Omar Junid` | Already in `_OCR_CORRECTIONS` → should resolve — investigate |
| 1 | `J,F. Conceicao` | Already in `_MANUAL_OVERRIDES` → should resolve — investigate |
| 1 | `Judges' Remuneration` | Bill title — parsing failure |
| 1 | `Lau Teik Sobn` | OCR: `Sobn` → `Soon` — `Lau Teik Soon` in Speaker table |
| 1 | `Lee Tee long` | OCR: `long` → `Leng`? — check Speaker table |
| 1 | `Lee Yock Suen` | Possible colonial member — check Speaker table |
| 1 | `Lim Kim San Cairnhill), Minister for National Development` | OCR: constituency+role appended — `Lim Kim San` in Speaker table (also in `_OCR_CORRECTIONS`) |
| 1 | `Lim You Eng` | Possible colonial member — check Speaker table |
| 1 | `Lirn Choon Mong` | OCR: `Lirn` → `Lim` — check `Lim Choon Mong` in Speaker table |
| 1 | `Minister for Manpower and Minister for Health` | Role string |
| 1 | `Minister of Defence` | Role string |
| 1 | `Minister, Prime Minister's Office` | Role string |
| 1 | `Mohd Mi Bin Alwi` | OCR: `Mi` → `Ali` — `Mohd Ali Bin Alwi` in Speaker table |
| 1 | `**Mr Ng Kah Ting` | Markdown bold prefix not stripped — `Ng Kah Ting` in Speaker table |
| 1 | `**Mr Speaker:` (various forms) | Procedural text — parsing failure |
| 1 | `[Mr Speaker in the Chair]` | Procedural text |
| 1 | `MR Tan Soo Khoon` | All-caps `MR` not in `_TITLE_PREFIXES` — `Tan Soo Khoon` in Speaker table |
| 1 | `Mt. Lin You Eng` | OCR: `Mt.` → `Mr.` — same person as `Lim You Eng`? |
| 1 | `National Service` | Document fragment |
| 1 | `Ngeow Pack Hua ABoon Lay)` | OCR: constituency appended — check `Ngeow Pack Hua` in Speaker table |
| 1 | `### OFFICIAL REPORT` | Markdown heading — parsing failure |
| 1 | `of Supply [3rd Allotted Day]:` | Procedural text |
| 1 | `Ong Piah Teng, O.B.E.` | Already in `_OCR_CORRECTIONS` → should resolve — investigate |
| 1 | `Ong Tang Cheong` | OCR variant of `Ong Tong Cheong`? — check Speaker table |
| 1 | `Ong Tong Cheong` | Check Speaker table |
| 1 | `Order read for resumed consideration in Committee` | Procedural text |
| 1 | `Othman bin Haron ELisofe` | OCR: `ELisofe` → `Eusofe` + lowercase `bin` — `Othman Bin Haron Eusofe` in Speaker table |
| 1 | `## PARLIAMENTARY DEBATES` | Markdown heading — parsing failure |
| 1 | `Parliamentary Secretary to the Deputy Prime Minister` | Role string |
| 1 | `Parliamentary Secretary to the Minister for Education` | Role string |
| 1 | `P. Coomaraswamy, Deputy Speaker` | OCR variant — same as `Punch Coomaraswamy` |
| 1 | `Phek Hoong` | Possible colonial member — check Speaker table |
| 1 | `Phua Bali Lee` | OCR variant of `Phue Bah Lee`? — check Speaker table |
| 1 | `Phue Bah Lee` | Possible colonial member — check Speaker table |
| 1 | `P. Selvadural` | OCR: `ural` → `urai` — already in `_OCR_CORRECTIONS` as `p seivadurai` variant — investigate |
| 1 | `Resumption of debate on Question` | Procedural text |
| 1 | `Seah Mui Kok, B.a.m.` | Already in `_OCR_CORRECTIONS` (other B.B.m. forms) — investigate |
| 1 | `Seah Mui Kok, B.B.m.` | Already in `_OCR_CORRECTIONS` — investigate |
| 1 | `Seah Mui Kok, e.B.m.` | OCR variant — add to `_OCR_CORRECTIONS` |
| 1 | `Secretary to the Minister for National Development` | Role string |
| 1 | `Senior Minister of State, Prime Minister's Office` | Role string |
| 1 | `Sia Khoon Soong` | Possible colonial member — check Speaker table |
| 1 | `## SINGAPORE` | Markdown heading — parsing failure |
| 1 | `S.V. Lingam.` | Possible colonial member — check Speaker table |
| 1 | `Tan Cheng Sen` | Likely noise — no Speaker table match, low frequency |
| 1 | `Tay Bon Too` | Likely noise — no Speaker table match, low frequency |
| 1 | `Technology` | Document fragment |
| 1 | `That Mr Punchardsheram Coomaraswamy do take the Chair…` | Procedural text |
| 1 | `"That the sum to be allotted for Head 25 be reduced` | Procedural text |
| 1 | `the Bill` | Document fragment |
| 1 | `The first message dated the 11th December, 1958…` | Procedural text |
| 1 | `The following Bill was assented to…` | Procedural text |
| 1 | `The Hon. Mr Chew Swee Kee` | `The Hon. Mr` not in `_TITLE_PREFIXES` — `Chew Swee Kee` likely in Speaker table |
| 1 | `The Hounourable Mr A.J. Braga` | `Hounourable` typo not in `_TITLE_PREFIXES` — colonial official, not in Speaker table |
| 1 | `**The Minister for Law and National Development` | Role string with markdown bold prefix |
| 1 | `There being only one proposal, the Clerk then declared…` | Procedural text |
| 1 | `The second message also dated the 11th December, 1958…` | Procedural text |
| 1 | `Thio Chan Bee, J.P.Tanglin)` | OCR: post-nominal+constituency merged — `Thio Chan Bee` in Speaker table |
| 1 | `Too Chong Tee` | Possible colonial member — check Speaker table |
| 1 | `Tunah), Parliamentary Secretary to the Prime Minister` | Truncated — person's surname is `Tunah`? |
| 1 | `Urn Kim San` | OCR: `Urn` → `Lim` — already in `_OCR_CORRECTIONS` as `urn cheng lock` variant; `Lim Kim San` in Speaker table |
| 1 | `Wong Foo Nam.` | Possible colonial member — check Speaker table |
| 1 | `Wong Lm Ken` | OCR: `Lm` → `Lim` — check `Wong Lim Ken` in Speaker table |
| 1 | `Yaacob Bin Mohamed AI-Haj` | OCR: `AI-Haj` → `Al-Haj` — Islamic suffix stripping should handle this |
| 1 | `Ya'acob Bin Mohamed Kampong Ubi), Minister of State…` | Apostrophe variant + constituency+role — should resolve after stripping |
| 1 | `_________________________` | Document noise |
| 1 | `Yeoh Ghim Seng)` | Trailing paren — already in `_OCR_CORRECTIONS` → investigate |
| 1 | Dates (`12th March 1996`, `21st March, 1981`, etc.) | Document noise — parsing failures |
| 1 | `Absent: Mr Ahmad Mohd Magad` | "Absent:" prefix not stripped — `Ahmad Mohd Magad` likely in Speaker table |
| 1 | `Adbul Hamid Bin Haji Jumat` | OCR: `Adbul` → `Abdul` — `Abdul Hamid Bin Haji Jumat` in Speaker table |
| 1 | `Affairs)` | Document fragment |
| 1 | `Andrew Fong` | Unconfirmable — no Speaker table match, no LA membership evidence |
| 1 | `Ang Kok Peng, B.B.m.` | OCR variant — add to `_OCR_CORRECTIONS` |
| 1 | `Ang Kok Peng. B.B.M.` | OCR variant — add to `_OCR_CORRECTIONS` |
| 1 | `Ang Nam Piau.` | Trailing period — already in `_OCR_CORRECTIONS` as `mg nam piau` → `Ang Nam Piau`; investigate |
| 1 | `*Appendix, cols. 895-900` | Document noise |
| 1 | `[APPENDIX-MAIN ESTIMATES…` | Document noise |
| 1 | `**ASSENT TO BILL PASSED**` / `**ASSENT TO BILLS PASSED**` | Markdown heading — parsing failure |
| 1 | `Bedok GRC` | Constituency name — parsing failure (modern era, NULL parlement_no) |
| 1 | `by $120,000 in respect of subhead 33 therein."-` | Procedural text |
| 1 | `Cha,u Sik Ting` | OCR: comma inside name — `Chau Sik Ting` in Speaker table |
| 1 | `C.H. Butterfield. Q.C.` | Colonial official — `_MANUAL_OVERRIDES` has `("butterfield", 1)` but form may not resolve |
| 1 | `C.H. Koh.` | Unknown — check Speaker table |
| 1 | `Ch'ng lit Koon` | OCR: `lit` → `Jit`? — `Ch'ng Jit Koon`/`Chng Jit Koon` may be in Speaker table |
| 1 | `Chor Yeok Eng Bukit Timah), Parliamentary Secretary…` | OCR: constituency+role — `Chor Yeok Eng` in Speaker table |

---

## Root cause categories

### Category 1 — Parsing failures (~80–90 rows)

The attendance parser (`services/attendance.py::_extract_section_lines` +
`_parse_entry_line`) is leaking non-name content into attendance rows. These include:

- Procedural text blocks (bill assents, Speaker election motions)
- Markdown headings (`### OFFICIAL REPORT`, `## PARLIAMENTARY DEBATES`)
- Role-only strings (`Ministry of Labour and Government Whip`)
- Truncated role strings (wrap-around from previous line: `for Defence and Deputy Leader`)
- Document noise (`| |`, dates, bill titles)
- The `**` markdown bold prefix appearing on some lines

These should never become `Attendance` rows. The fix is in `_extract_section_lines` /
`_parse_entry_line` in `services/attendance.py` — tighten the section boundary detection
or add filters for lines that are clearly not person names.

### Category 2 — OCR variants not in `_OCR_CORRECTIONS` (~40–50 rows)

Names that belong to real speakers already in the Speaker table, but whose OCR form is
not handled by the existing resolution cascade. Requires new entries in `_OCR_CORRECTIONS`
(parliament-agnostic) or `_MANUAL_OVERRIDES` (parliament-scoped) in `services/attendance.py`.

High-confidence targets (canonical is clear, Speaker row exists):
- `Hwang Soo un` → `Hwang Soo Jin`
- `Lau Teik Sobn` → `Lau Teik Soon`
- `Mohd Mi Bin Alwi` → `Mohd Ali Bin Alwi`
- `Othman bin Haron ELisofe` → `Othman Bin Haron Eusofe`
- `Adbul Hamid Bin Haji Jumat` → `Abdul Hamid Bin Haji Jumat`
- `DL Chiang Hai Ding` → `Chiang Hai Ding` (DL = OCR of Dr/Mr)
- `DR Yeoh Ghim Seng` → `Yeoh Ghim Seng` (all-caps title prefix)
- `MR Tan Soo Khoon` → `Tan Soo Khoon` (all-caps `MR` not in `_TITLE_PREFIXES`)
- `Cha,u Sik Ting` → `Chau Sik Ting` (comma inside name)
- `Ang Kok Peng, B.B.m.` / `Ang Kok Peng. B.B.M.` → `Ang Kok Peng`
- `Seah Mui Kok, e.B.m.` → `Seah Mui Kok`
- `Goh Keng Swee Kreta Ayer) Minister for Finance` → `Goh Keng Swee`
- `Thio Chan Bee, J.P.Tanglin)` → `Thio Chan Bee`
- `Lirn Choon Mong` → `Lim Choon Mong` (if in Speaker table)
- `Absent: Mr Ahmad Mohd Magad` → `Ahmad Mohd Magad` (`Absent:` prefix not stripped)
- `**Mr Ng Kah Ting` → `Ng Kah Ting` (markdown `**` prefix not stripped)
- `The Hon. Mr Chew Swee Kee` → `Chew Swee Kee` (`The Hon. Mr` not in `_TITLE_PREFIXES`)
- `Punch Coomaraswamy, Deputy Speaker` / `P. Coomaraswamy, Deputy Speaker` → `Coomaraswamy, P.`
- `Urn Kim San` → `Lim Kim San` (if not already caught by `urn cheng lock` logic)

Also investigate these — they should already resolve via existing entries but don't:
- `Inche. Buang Bin Omar Junid` (in `_OCR_CORRECTIONS`)
- `J,F. Conceicao` (in `_MANUAL_OVERRIDES`)
- `Ong Piah Teng, O.B.E.` (in `_OCR_CORRECTIONS`)
- `Ang Nam Piau.` (in `_OCR_CORRECTIONS` via `mg nam piau`)
- `Yeoh Ghim Seng)` (in `_OCR_CORRECTIONS`)
- `P. Selvadural` (related entry exists)
- `Yaacob Bin Mohamed AI-Haj` / `Ya'acob Bin Mohamed Kampong Ubi)…`

### Category 3 — Possible genuine colonial gaps (~10–15 rows)

Names that may represent real people not currently in the Speaker table. Requires
research before any action.

| Name | Notes |
|---|---|
| `C.V. Devan Nair` | C.V. Devan Nair was a prominent PAP founding member / trade unionist / later President. Very likely in Speaker table under an inverted or different form — check before assuming absent. |
| `Lim You Eng` / `Mt. Lin You Eng` | `Mt.` = OCR of `Mr.` — same person. Check Speaker table for `Lim You Eng`. |
| `Lee Yock Suen` | Check Speaker table. |
| `Ong Tang Cheong` / `Ong Tong Cheong` | Two OCR forms of same person? Check Speaker table. |
| `Phek Hoong` | Unknown. Check Speaker table. |
| `Phua Bali Lee` / `Phue Bah Lee` | Two OCR forms? Check Speaker table. |
| `Sia Khoon Soong` | Unknown. Check Speaker table. |
| `S.V. Lingam.` | Unknown. Check Speaker table. |
| `Ch'ng lit Koon` | OCR: `lit` → `Jit` — `Chng Jit Koon` was a PAP MP. Check Speaker table. |
| `Wong Foo Nam.` | Unknown. Check Speaker table. |
| `Too Chong Tee` | Unknown. Check Speaker table. |
| `C.H. Koh.` | Unknown. Check Speaker table. |
| `A.V. Winslow` | Previously researched — no biographical records found. Likely noise. |
| `Andrew Fong` | Previously researched — no LA membership evidence found. Likely noise. |
| `Tan Cheng Sen` | Previously researched — likely noise. |
| `Tay Bon Too` | Previously researched — likely noise. |

---

## What has already been done

- **Research loop** (`docs/speech-speaker/research-loop.md`): Ran 14+ iterations checking
  attendance candidates against biographical sources. Ceiling declared 2026-06-02. Added
  `Lim Huan Boon` and `Tan Siak Kew` to `data/colonial_la_members.json`. All remaining
  high-frequency candidates confirmed as OCR artifacts, noise, or post-LA era MPs.

- **Pipeline fix loop** (`docs/speech-speaker/pipeline-fix-loop.md`): 14 iterations of
  OCR corrections added to `_OCR_CORRECTIONS` in `services/attendance.py`. Applied to
  attendance ingestion; already resolved the bulk of OCR variants.

- **Attendance-speaker refine loop** (`docs/attendance-speaker/refine-loop.md`): Applied
  `resolve_canonical_name` + parliament-0 fallback to `_populate_attendance_speaker_ids`.
  Ceiling: 99.8% (202 unmatched), declared 2026-06-05.

---

## Recommended approach for the next Claude instance

**Start here — query the actual unmatched rows with parliament context:**

```python
DATABASE_URL="..." PYTHONPATH=. poetry run python3 - <<'EOF'
from sqlmodel import Session, text
from database.init import engine

with Session(engine) as s:
    rows = s.exec(text("""
        SELECT a.speaker_name, COUNT(*) AS freq,
               s.parlement_no, s.volume_no
        FROM attendance a
        JOIN sitting s ON a.sitting_id = s.id
        WHERE a.speaker_id IS NULL
        GROUP BY a.speaker_name, s.parlement_no, s.volume_no
        ORDER BY freq DESC
    """)).all()
    for name, freq, pno, vno in rows:
        print(f"{freq:3d}  parl={pno}  vol={vno}  {name!r}")
EOF
```

**Prioritised fix order:**

1. **Category 2 (OCR variants)**: Add entries to `_OCR_CORRECTIONS` or `_MANUAL_OVERRIDES`
   in `services/attendance.py`. After editing, re-run `populate_attendances` for affected
   sittings and then `populate_speaker_links`. Each fix here removes real rows.

2. **Category 3 (possible genuine gaps)**: For each candidate, check the Speaker table
   first (`SELECT * FROM speaker WHERE name ILIKE '%partial%'`). If found under a
   different form, it's a Category 2 fix. If genuinely absent and confirmed as an LA
   member, add to `data/colonial_la_members.json` and run
   `scripts/load_colonial_la_speakers.py`.

3. **Category 1 (parsing failures)**: These should not exist as Attendance rows at all.
   Fixing `_extract_section_lines` / `_parse_entry_line` in `services/attendance.py` to
   reject non-name content would prevent them on future ingestion but will not remove
   existing rows from the DB (they'd need a targeted DELETE).

**Key files:**
- `services/attendance.py` — `_OCR_CORRECTIONS`, `_MANUAL_OVERRIDES`, `_TITLE_PREFIXES`,
  `_extract_section_lines`, `_parse_entry_line`
- `populate/speaker_links.py` — `_populate_attendance_speaker_ids`,
  `_COLONIAL_PARLIAMENT_FALLBACKS`
- `data/colonial_la_members.json` — 71 confirmed LA members
- `scripts/load_colonial_la_speakers.py` — idempotent loader for the JSON
- `docs/speech-speaker/research-loop.md` — research loop methodology
- `docs/attendance-speaker/progress.txt` — iteration history and ceiling declaration

**After any fix:** re-run `populate_speaker_links` and re-check the unmatched count.
The target is 0 genuine person-name rows unmatched; noise/parsing-artifact rows may
remain until the parser is tightened.

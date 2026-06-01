# Attendance Speaker Matching Patterns

Accumulated knowledge about `Attendance.speaker_name` string formats and how to handle them.

## How attendance names originate

`Attendance.speaker_name` is parsed from the PRESENT/ABSENT sections of `Sitting.markdown_content` by `services/attendance.py::_parse_entry_line`. The raw name is extracted from the attendance list with minimal normalisation — titles are NOT stripped at parse time.

## Name formats

### Standard title + name
`Dr Toh Chin Chye`, `Mr Lee Kuan Yew`, `Dr Goh Keng Swee`
The most common format. No normalisation applied before lookup — must strip title via `strip_title` then resolve via `resolve_canonical_name`.

### Initials with periods
`S. Jayakumar`, `K. Shanmugam`, `J.B. Jeyaretnam`, `E.W. Barker`, `J.F. Conceicao`
Stored in attendance with period after initial (`S.`). `Speaker.name` stores them without the period (`S Jayakumar`). Period-stripping is required before lookup.

### Inverted format
`Augustine H.H. Tan` → `Speaker.name = Tan H.H. Augustine`
`George Yong-Boon Yeo` → `Speaker.name = Yeo Yong-Boon, George`
`Aline K. Wong` → `Speaker.name = Wong Aline K`
`Tony Tan Keng Yam` → `Speaker.name = Tan Keng Yam, Tony`
`E.W. Barker` → `Speaker.name = Barker, E.W.`
Inverted-name lookup already exists in `resolve_canonical_name` — but attendance currently bypasses that function entirely.

### Missing `Bin`/`Binte`
`Abdullah Tarmugi` → `Speaker.name = Abdullah Bin Tarmugi`
`Othman Haron Eusofe` → `Speaker.name = Othman Bin Haron Eusofe`
Some attendance records omit the `Bin`/`Binte` patronymic connector. The canonical form in `Speaker` includes it.

### Case mismatch on `bin`/`binte`
`Sidek bin Saniff` → `Speaker.name = Sidek Bin Saniff`
`Othman bin Haron Eusofe` → `Speaker.name = Othman Bin Haron Eusofe`
The attendance record stores `bin` lowercase; `Speaker.name` uses title-cased `Bin`. Raw dict lookup is case-sensitive and misses all of these.

### Missing title suffix
`Ong Chit Chung` → `Speaker.name = Ong Chit Chung, Dr`
`Mohd Ariff Bin Suradi` → `Speaker.name = Mohd Ariff Bin Suradi, Haji`
Some speakers have a title appended to their canonical name (post-nominal form). The attendance record omits it.

### Mohamad Maidin B P M
Abbreviation form: `Mohamad Maidin B P M` = `Mohamad Maidin Bin Packer Mohamed`. Not resolvable via standard normalisation — requires a manual override.

## Parliament derivation

`infer_parliament(sitting)` reads `sitting.volume_no` and `sitting.parlement_no` via `VOLUME_TO_PARLIAMENT`. Volumes 12–23 map to parliament 0 — these volumes correspond to a transitional era (post-Legislative Assembly, pre-Parliament renumbering). No `Speaker` rows exist for `parliament_number = 0`, so every attendance row from those volumes fails unconditionally. The speech pipeline handles this by falling back to parliaments 1, 2, 3 in order — the same approach applies here.

## Known non-resolvable cases

- **Colonial-era speakers not scraped** (~3,945 rows): Pre-1965 Legislative Assembly members (e.g. `D.S. Marshall`, `Lim Ching Siong`, `G.A.P. Sutherland`) are not in `parliament.gov.sg` listings and therefore not in the `Speaker` table. Structurally absent.
- **Non-speaker attendees** (~5,390 rows): Ministers, civil servants, or foreign dignitaries who attended sittings but were never elected. Genuinely absent from `Speaker` table.

## Known top failures (from full-corpus analysis, 2026-06-01)

| speaker_name | Count | Root cause |
|---|---|---|
| Abdullah Tarmugi | 679 | Missing Bin |
| Tony Tan Keng Yam | 648 | Inverted format |
| George Yong-Boon Yeo | 581 | Inverted format |
| Sidek bin Saniff | 552 | bin vs Bin case |
| S. Jayakumar | 539 | Period initial + no normalisation |
| Bernard Chen | 538 | Unknown / absent |
| Eugene Yap Giau Cheng | 509 | Unknown / absent |
| Ong Chit Chung | 504 | Missing title suffix |
| Othman bin Haron Eusofe | 480 | bin vs Bin case |
| E.W. Barker | 442 | Inverted format + period initials |
| Augustine H.H. Tan | 427 | Inverted format |
| S. Vasoo | 417 | Period initial + no normalisation |
| Aline K. Wong | 416 | Inverted format |
| K. Shanmugam | 373 | Period initial + no normalisation |
| Mohamad Maidin B P M | 370 | Abbreviation — manual override needed |

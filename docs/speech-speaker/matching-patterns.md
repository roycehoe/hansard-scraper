# Speech Speaker Matching Patterns

Accumulated knowledge about `Speech.speaker` string formats and how to handle them.

## Speaker string formats

### Title + name (standard)
`Mr Lee Kuan Yew`, `Dr Goh Keng Swee`
Strip title prefix via `strip_title`, then run `resolve_canonical_name`. Works for most modern speeches.

### Title + name + constituency
`Dr Tan Cheng Bock (Ayer Rajah)`, `Mr Hawazi Daipi (Sembawang)`, `Dr Jennifer Lee (Nominated Member)`
The constituency parenthetical is carried through from the bold markup. Must strip the first parenthetical before matching — same logic as `_parse_name_and_location` in `attendance.py`.

### Role + (name)
`The Prime Minister (Mr Lee Kuan Yew)`, `The Financial Secretary (Mr T. M. Hart)`, `The Minister for Health (Dr Toh Chin Chye)`
The actual MP name is inside the outermost parentheses. Extract the inner content, strip title prefix, then match. This pattern is common in older parliamentary records where ministers are introduced by role.

### Role only (unresolvable)
`The Prime Minister`, `The Minister for Social Affairs`
No name present. Cannot match without a role→MP→date mapping. Treat as unresolvable; exclude from denominator only if the role is non-specific (i.e., multiple MPs held this role across parliaments).

### Presiding officers (structural exclusions)
`Mr Speaker`, `Mr Deputy Speaker`, `The Clerk`
Not in the `Speaker` table. Exclude from the match-rate denominator.

### Collective references (structural exclusions)
`Hon. Members`, `Several Members`, `Members`
Not individual MPs. Exclude from denominator.

### Section headers (`can_extract` failures)
All-caps strings with no name structure: `PART I INTRODUCTION`, `CONCLUSION`, `ADJOURNMENT`, `COMMITTEE OF SELECTION`
These are speech parsing failures — `_parse_speeches` misidentified a bold section header line as a speaker. These are now `can_extract` failures: they stay in the denominator until fixed in `services/speech.py`. Do not attempt to match them in `speaker_links.py`.

## Known Correct Exclusions

(Add entries here as they are confirmed during loop iterations.)

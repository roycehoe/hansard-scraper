Goal: Improve Speech.speaker_id match rate by fixing both extraction errors and resolution failures

Problem: Some Speech.speaker values are wrong because services/speech.py extracted the wrong text from the markdown
Problem: Some Speech.speaker values are correct names but populate/speaker_links.py fails to resolve them to a Speaker row

Solution: Extend the existing refine-loop in docs/speech-speaker/refine-loop.md with a new upstream failure category

Method: In refine-loop Setup Step 5 (failure catalogue), add a third category: extraction failures
  - Extraction failure: Speech.speaker is non-null but does not look like a name (all-caps section header, procedural text, empty string, etc.)
  - Fix location: services/speech.py, not populate/speaker_links.py
  - Distinguish from resolution failure: the name was correctly extracted but the cascade did not find a Speaker match

Method: In refine-loop Loop Step 2 (pick highest-impact failure), extend the priority order:
  0. Extraction failures (speech.py) — fix first; resolution logic cannot compensate for a wrong input
  1. Pre-processing failures (constituency suffix, role+name extraction) — fix in speaker_links.py
  2. Cascade misses for known MPs — add to _MANUAL_OVERRIDES
  3. Structural exclusions — add to exclusion list

Method: Diagnostic heuristic for extraction failures
  - Looks like a real name: mixed case, 1–4 words, no colons or brackets beyond a constituency parenthetical
  - Does NOT look like a name: all-caps with no lowercase, sentence-length text, starts with a number
  - For borderline strings, open the Speech.transcript to see what text follows; a section header will have a paragraph body, not a spoken utterance

Method: Test and measure the same way as the existing loop (pilot/held-out/regression sets)
Method: Commit one fix per iteration as the existing loop requires

Note: Do not create a new loop file. Add extraction failures as a first-class failure category
  inside the existing docs/speech-speaker/refine-loop.md

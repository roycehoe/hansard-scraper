# Peer projects

What other parliamentary-record projects do differently from this one, and which of those differences fit the goal in [vision.md](vision.md). Surveyed 14 October 2026 in two rounds of web research: one on which parliaments let a user search by member, one reading the code and papers of the projects that link speeches to members. Claims marked [unverified] rest on a search snippet or a third-party source, because many official sites refused automated fetches.

## Where Singapore sits

| Group | Examples | What the record carries |
|---|---|---|
| Member ID on every speech | Sweden (`intressent_id`), Australia (`name.id` in the Hansard XML), Germany (Bundestag XML, recent periods), Hong Kong LegCo (a speakers list with IDs, 2012 on; per-speech ID unverified) | Linking is a join |
| Search by name, no ID | Japan (Diet Library API `speaker=`, partial text match), US GovInfo (`member:mcconnell`), Scotland and Wales (member dropdown) | A name filter that misses variants |
| Neither | Singapore, Malaysia, the Philippines | Names as free text |

Singapore is in the third group. Even the structured attendance list from `getHansardReport/` gives a free-text name with no ID: `{"mpName": "Mr K Shanmugam (Nee Soon), Minister for Home Affairs and Minister for Law.", "attendance": false, "locationName": null}`.

The projects that face the same problem and solved it by matching names themselves:

| Project | Source | How read |
|---|---|---|
| ParlParse and TheyWorkForYou (mySociety) | UK Commons, Lords, devolved bodies | `pyscraper/resolvemembernames.py`, `base_resolver.py`, `new_hansard.py`, `gidmatching.py`, `patchtool.py` |
| openparliament.ca | Canadian Commons | `parliament/hansards/models.py`, `parliament/imports/alpheus.py`, `imports/hans_old/old.py` |
| LiPaD and PoliticalMashup | Canadian Commons from 1901; Dutch proceedings 1814 to 2012 | Beelen et al. 2017, Canadian Journal of Political Science 50(3) |
| Open Discourse | Bundestag from 1949 | `python/src/od_lib/helper_functions/match_names.py`, `extract_contributions.py` |
| ParlaMint (CLARIN) | 29 European parliaments | Encoding guidelines, `Scripts/validate-parlamint*.xsl` |
| unitedstates/congressional-record | US Congressional Record | `congressionalrecord/govinfo/cr_parser.py`, `subclasses.py` |
| Stanford Congressional Record corpus | US, 1873 to 2017 | `codebook_v4.pdf` |
| Katz and Alexander | Australian House, 1998 to 2022 | Scientific Data 2023; `hansard-proj` scripts `08-data_validation.R`, `09-fix_interjections.R` |
| Knesset corpus | Israel | arXiv 2405.18115 |
| legco-hansard-parser | Hong Kong LegCo | `lib/legco/hansard/filters/event_filter.rb` |
| Par-leh-mate | Singapore | `transform/speeches.py` |
| SGParliament (sgparliament.com) | Singapore, 1955 on | Site pages, Substack posts and debate JSON; compared turn by turn in [report/sgparliament-comparison-2026-10-18.md](report/sgparliament-comparison-2026-10-18.md) |

None of the corpora that pool many parliaments (ParlSpeech V2, ParlaMint, ParlEE, the Comparative Legislators Database) covers Singapore or another Asian Commonwealth parliament. Par-leh-mate, the one earlier Singapore project, reads `<strong>` as the speaker, strips titles with one regex and matches names exactly against a member list, with no fuzzy step. This project's resolver goes further than any peer on Malay, Chinese and Indian name forms; no peer read handles Haji, bin, inverted names or OCR'd names beyond edit distance.

## What we already do the same way

- **Procedural lines get no speaker.** congressional-record's recorder phrases, ParlParse's `nospeaker` paragraphs and openparliament's `procedural` flag do what `_PROCEDURAL_LINE_ANCHORS` in `services/speech.py` does: "Question put, and agreed to", "Bill read a Second time", "The House divided" and similar lines get a NULL speaker. `_LIST_OPENER_RE` also resets the current speaker after "Resolved," and division openers.
- **Unbolded role labels.** openparliament and Open Discourse detect speakers by pattern, not formatting. `_PLAIN_ROLE_LABEL_RE` catches "The Minister for X (Mr Y):" without bold.
- **Bare roles from the same sitting.** ParlParse's `debateofficehistory` resolves "Madam Deputy Speaker" to whoever held the chair earlier that day, and `get_chairman` reads the chair from the header. `_populate_deputy_speaker_links` in `populate/speaker_links.py` resolves a bare "Mr Deputy Speaker" from the deputies named in that sitting's reports, and `services/speaker_link.py` takes the Chairman from "in the Chair" annotations.
- **Unique or nothing.** Stanford keeps a speaker match only when a subset of {chamber, gender, first, last, state} is unique in the session; Open Discourse narrows the pool step by step and accepts only a unique candidate; ParlParse raises on ambiguity. Our surname fallback keeps only surnames unique in a parliament.
- **Term-bounded matching.** Open Discourse filters by electoral term and the Knesset by date in office; we resolve within a parliament number.
- **Published rates and a hand audit.** Stanford publishes match rates and an audit; we publish three rates and a hand-checked precision.

## What they do differently

### A. Every non-speech line ends the current turn (gap 1)

The strongest finding, and five projects agree on it.

- congressional-record classifies every line (speech, recorder, clerk, rollcall, title, excerpt) and sets `break_flow: True` on every non-speech kind, so nothing after it inherits the previous speaker.
- Stanford's codebook (§2.2) ends a speech at the next speaker, the end of a section, "the reading of a bill or other document, or a vote".
- LegCo's parser runs a state machine: a line that is only a parenthetical moves it to an `acting` state and is emitted as an action; a line opening a tabled document or annex moves it to `supplementing`.
- PoliticalMashup and LiPaD store "stage direction" (procedural text and votes) as its own element; Open Discourse cuts interjections and stage directions into a separate table.
- openparliament flags a paragraph as procedural when it opens with "moved", "(" or "[".

Our parser does half of this. A procedural line gets a NULL speaker, but the current speaker carries on to the next unlabelled line unless the procedural line was a list opener. Measured with an instrumented copy of the parser over all reports, 14 October 2026:

| Line kind | Rows |
|---|---|
| Unlabelled lines after a procedural line that is not a list opener, keeping the previous speaker | 11,117 in 4,140 reports; 30 of 30 sampled were non-speech |
| Whole-line editorial notes: "[For vernacular speech, please refer to Appendix A]", "[Pursuant to Standing Order No 22(3), ...]", "[Mr Speaker in the Chair]" | 464 linked |
| "**Mr X** rose -" with a bold label, linked to X but holding no speech | 1,001 linked |
| "Mr X rose -" without bold, credited to the previous speaker | 34 |

Another 2,770 linked rows open with a vernacular note and then carry the member's own translated speech; they are speech. The 1,202 rows after an annex heading are ministers' own tables in written answers, not text credited to the chair. All five errors in the last hand audit were the non-speech class.

### B. Automated checks that a link is plausible (gap 4)

- Katz's `08-data_validation.R` runs seven row-level tests and hand-checks each failure: no two adjacent identical bodies; "(Time expired)" only at the end of a body, which catches a missed speaker split; one party and seat per person per day; the ID exists; the speaker was alive and held a seat that day; the file date equals the header date.
- ParlaMint's validators reject an utterance with no speaker, text outside a segment, and speeches inside a comment section; `validate-parlamint-particDesc.xsl` flags overlapping affiliations for the same role.
- ParlParse's `base_resolver.py` raises on overlapping seats; `regnospeakers` is an allowlist of roles that may stay unmatched, so any other unmatched label is an error, not a quiet NULL.
- ParlParse's `gidmatching.py` aligns old and new parses with `difflib` and records which speeches moved after a parser change.

We have per-sitting attendance, which none of them has. Joining linked rows to that day's attendance:

| Linked speaker that day | Speech rows | Speaker-report pairs |
|---|---|---|
| Present | 986,217 | 117,573 |
| Absent | 6,686 | 2,351 |
| Not in the attendance list | 4,365 | 378 |

6,155 of the absent rows are written answers, which print whether or not the minister attended. Most oral-answer cases are question lines printed for an absent asker ("asked the Minister", "To ask"); Par-leh-mate guards the same opener. The rest include real errors: "The Chairman" on 7 March 2005 linked to S Iswaran, who was absent, and an answer on 16 October 2003 credited to an absent George Yeo.

`scripts/trace_speaker_links.py` (stored links equal what the resolver returns today) and the re-parse guard of 13 October are our nearest equivalents, and neither tests whether a link is right.

### C. Audits that score more than linked rows

- The Knesset paper reports false positives (18,192 of 323,373 matched) and false negatives (19,686 of 362,854 unmatched) separately, keeps a development set apart from a 20-document test set, and counts non-speech text mistaken for a speaker. Its 94.5% is a match rate; the speaker-name correctness on the test set is 98.3%.
- Stanford's parsing audit annotated 1,000 contiguous lines by hand and scored speech start, speech length and name agreement separately (start 94% to 99.7%, exact length 77% to 88%).
- The Hansard-corpus linking paper (Khursheed et al. 2026, arXiv 2608.30485, the source of the 89.3% Commons figure) used two annotators and reported kappa, though for stance, not matching.

Our audits score whether a linked row's text belongs to its speaker. None scores where a speech starts and ends, and each had one reader.

### D. A row type or link confidence stored on the row

LiPaD stores `speaker-link-confidence` per speech from a strict-to-loose cascade; ParlaMint tags each utterance `#chair`, `#regular`, `#guest` or `#interrupting`; Stanford flags a speech procedural when 30% of its bigrams appear in a procedure manual. We store the speaker string and `speaker_id`; which cascade step matched, and whether a NULL row is procedural or unattributable, is not recorded. A stored step would let a hand audit sample by step instead of at random.

### E. Smaller techniques

- **Name history within a debate.** ParlParse's `disambiguate_from_history` resolves an ambiguous surname to the most recent matching speaker in the debate, skipping the one just before. We use the same idea for deputy speakers only. Unlinked speaker strings hold 0.76% of body text, and [vision.md](vision.md) rules resolver tuning past the point of value.
- **Roster-gated bare-name labels.** congressional-record compiles that day's member list into the turn regex; a Malaysian parser scans for every known name. We refuse unbolded "Mr Tan:" because it is often a quoted line; gating it on the report's "MPs Speaking" header would accept it. Only 116 such lines in 81 reports exist, so the payoff is small.
- **Title-gated surname fallback.** ParlParse tries a surname-only match only when a title was stripped.
- **Source patches.** ParlParse keeps hand fixes as diffs applied to the cached source, which is never edited.
- **Stable IDs across re-parses.** ParlParse and openparliament keep old speech IDs mapped to new ones. Our speech IDs change on every re-parse.

### F. Publishing and identity

- **Public person ID tied to Wikidata.** TheyWorkForYou maps its person ID to other systems; the Comparative Legislators Database joins on Wikidata IDs. Our 573 `Person` rows carry no external ID.
- **Dated memberships.** TheyWorkForYou, ParlaMint and the Comparative Legislators Database store each membership and role with `from` and `to` dates; our `Speaker` row is per parliament with no dates.
- **A versioned bulk release.** Katz and Alexander publish CSV and parquet on Zenodo with a DOI and version history; Stanford, Open Discourse and ParlSpeech publish dumps. We have a Postgres database and no export. The parliament.gov.sg terms of use require written permission to republish its content, so this needs permission before it needs code.

## Sources

- ParlParse: https://github.com/mysociety/parlparse
- openparliament.ca: https://github.com/michaelmulley/openparliament
- Beelen et al. 2017 (LiPaD): https://pure.uva.nl/ws/files/19452206/Digitization_of_the_Canadian_Parliamentary_debates.pdf
- Open Discourse: https://github.com/open-discourse/open-discourse
- ParlaMint guidelines and scripts: https://clarin-eric.github.io/ParlaMint/ and https://github.com/clarin-eric/ParlaMint
- congressional-record: https://github.com/unitedstates/congressional-record
- Stanford codebook: https://stacks.stanford.edu/file/druid:md374tz9962/codebook_v4.pdf
- Katz and Alexander: https://pmc.ncbi.nlm.nih.gov/articles/PMC10460412 and https://github.com/lindsaykatz/hansard-proj
- Knesset corpus: https://arxiv.org/abs/2405.18115
- Khursheed et al. 2026: https://arxiv.org/abs/2608.30485
- legco-hansard-parser: https://github.com/siuying/legco-hansard-parser
- Par-leh-mate: https://github.com/parleh-mate/singapore-parliament-speeches
- Parliament of Singapore terms of use: https://www.parliament.gov.sg/terms-of-use

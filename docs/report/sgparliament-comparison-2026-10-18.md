# Comparison with sgparliament.com, 18 October 2026

sgparliament.com is a public reader over the same SPRS record, from the first Legislative Assembly sitting on 22 April 1955 to the present. It splits each debate into speaker turns, links turns to member pages, shows party history within a membership, and adds LLM summaries, topic groups, a PQ explorer and statistics. It offers no API, no download and no source code, and it publishes no accuracy figures. Its disclaimer says the LLM content may contain "hallucinations". The domain was registered in May 2023. Its newsletter, sgparliament.substack.com, signs posts "SGParliament team", but the Substack archive API gives every post with a byline the author Kenneth Tiong (handle `kennethtiong`). That Substack account also runs kennethtiong.com, which publishes the speeches and Parliamentary Questions of Kenneth Tiong, Workers' Party MP for Aljunied GRC. Neither site says in prose that the two share an author.

This report compares its speaker attribution with our speech rows. Our figures come from the local database on 18 October 2026, after the coverage refill. Scripts and raw output are in the session scratchpad and are not kept.

## Verdict

On 27 debates its attribution is not better than ours. Where both sides credit a word to a member, they name the same member for all but 13 of 148,347 words. We credit 4,249 words it leaves with no member, almost all of them the President and the presiding officers. It credits 1,049 words we leave with no member, most of them procedural lines and chamber events that its parser folds into the turn of the member who spoke last. Its text matches ours: 99.06% of its 6-word sequences appear in our speech rows for the same sitting day.

## Method

1. Two sitting dates per Parliament, 0 to 14, drawn at random from our reports with markdown (seed 20261018).
2. For each date, its sitting page (`/sitting/YYYY-MM-DD`) lists the debates. Up to six were tried in random order, and the first with at least three speaker turns was kept. Three dates had none in the six tried: 28 February 1992, 10 September 2012 and 21 February 2021. That leaves 27 debates.
3. Each debate page carries its turns in the `__NEXT_DATA__` JSON block as `debate.events`, each with the printed label (`speaker`) and the linked member (`mpName`, null when unlinked).
4. Each debate was matched to our report on the same date by title, and by position where several reports share a title.
5. Both texts were cut into lower-case words, with bold labels and links removed, and aligned with `difflib.SequenceMatcher` (`autojunk=False`). Each aligned word was compared on the member each side credits: `mpName` there, the `Speaker` row behind `speech.speaker_id` here.
6. Name formats differ ("Noris Ong Chin Guan" and "Ong Chin Guan, Noris"), so every distinct pair of names was read by hand.

## Results

| Aligned words, 155,068 | Words | What they are |
|---|---|---|
| Both credit the same member | 148,334 | |
| Both credit a member, not the same one | 13 | Words at the edge of a turn (Lim Kim San, Low Yong Nguan, Yeoh Ghim Seng). Not read |
| Only we credit a member | 4,249 | 2,736 the 2009 President's Address, 1,448 presiding officers, 56 table cells, 9 other |
| Only it credits a member | 1,049 | Procedural lines, chamber events, committee clause text, order-paper amendments |
| Neither credits a member | 1,423 | |

Words that did not align (52,761 on its side, 24,553 on ours) are almost all in debates the two sites split differently. Its "Development Estimates for 1968" is one debate of 31,709 words, and we hold it as several Budget reports by division. The day-level check above shows the text is present on our side.

### Words only we credit

- **The President.** The 2009 President's Address (our report 21011) has no linked member on its side. We credit it to S R Nathan through the President's Address fallback in `services/speech.py`.
- **Presiding officers.** It never links "Mr Speaker", "Mr Deputy Speaker" or "The Chairman". We link them to the holder of the day (ADR 0002): George Oehlers in 1959 and 1961, A.P. Rajah in 1965, Yeoh Ghim Seng in 1973 to 1985, Tan Soo Khoon in 1991 and 2001, Tan Chuan-Jin in 2020, and the chairs of committees. The 160 words credited to Hwang Soo Jin in the 1978 Committee of Supply follow the source note "[Mr Hwang Soo Jin in the Chair]".
- **Table cells.** In the 2007 written answer "Resident Singles" its parser turns table cells into turns labelled "Year" and "2005" with no member. We keep the table in Vivian Balakrishnan's answer.

### Words only it credits

- **Procedural lines.** In the 2018 Public Sector (Governance) Bill it credits 505 words to Ong Ye Kung: "Question put, and agreed to", "Bill considered in Committee", "Clauses 6 to 14 inclusive ordered to stand part of the Bill" and the text of each amendment. We store these rows as PROCEDURAL or HEADING with no speaker (ADR 0007).
- **Chamber events.** In 1959 it credits "(Laughter)" and "(Interruption)" to Lee Kuan Yew, "Mr Lee Kuan Yew rose" to William Tan, and "Thereupon Mr Thomas left the Chamber" to Francis Thomas. We store them as CHAMBER_EVENT rows with no speaker.
- **Order-paper amendments.** In the 1973 Committee of Supply it credits 97 words of amendments on the order paper to their movers (Mohd. Ariff Bin Suradi, Ng Kah Ting, Ch'ng Jit Koon). We hold them in an unlinked "The Chairman" row. Neither is right: the text is an order-paper document. Crediting the mover is the better of the two.
- About 400 words, most of them in the 1967 Development Estimates, were not read.

## Limits

- 27 debates is a small sample. Long debates hold most of the words: five debates over 20,000 words each make up most of the aligned text.
- The check of text runs one way. It shows its text is in our rows, not that our text is in its debates.
- Agreement is not correctness. Both sides could credit the same wrong member. The stratified sample in the next section asks that question.

## What it says about its method

A Sonnet reader went through all 10 posts on sgparliament.substack.com, all 23 posts on kennethtiong.com, and the site's About, Disclaimer, Issue Provenance, Debate Topics, PQ Explorer, Stats, Maiden Speeches, Adjournment Motions and Budget pages, with the page JavaScript where the text was thin. Its quotes were checked against the downloaded pages. The posts announce features and say little about method.

| Question | What it says |
|---|---|
| Source | "every sitting that Parliament's own site (sprs.parl.gov.sg) publishes, from the first sitting of the Legislative Assembly on 22 April 1955" ([About](https://www.sgparliament.com/aboutus)) |
| How it fetches, and how often | Not stated. The 6 and 7 November 2023 sittings were announced 10 days later ([post](https://sgparliament.substack.com/p/the-6th-and-7th-november-2023-parliamentary)) |
| Coverage history | Built backwards in 2023: "We've now parsed the 11th Parliament (save the first three sittings)" ([post](https://sgparliament.substack.com/p/explore-the-11th-parliament-2006)). The About page now claims 1955 on |
| Speaker turns and member links | Not stated. The page code keeps the printed label beside the resolved member (`mp_name` or else `raw_speaker`), as our `speech.speaker` and `speaker_id` do |
| Presiding officers, procedural lines | Not stated. The comparison above shows presiding officers unlinked and procedural lines folded into the last turn |
| Party history | "A member's party is shown as it was at the time of each sitting" ([About](https://www.sgparliament.com/aboutus)). Source not stated |
| Government and opposition | "since 5 June 1959, every party but the PAP; from 1955 to 1959, every party but the Labour Front, the Alliance and the Singapore People's Alliance". Nominated and ex officio members and the Speaker are on neither side ([About](https://www.sgparliament.com/aboutus)) |
| Oral and written PQs | Split by the "Oral Answer" and "Written Answer" section headers. It has no split for "all of the 11th Parliament and roughly a fifth of the 12th", which lack them (PQ Explorer page code) |
| LLM use | Timelines are LLM output, built from sections of "typically >=1000 characters for each topic" chosen "based on their vector similarity to the topic", and "may contain hallucinations" ([Disclaimer](https://www.sgparliament.com/disclaimer)). Debate Topics' semantic groups are "LLM-detected topic clusters". Issue Provenance has a match threshold that defaults to 0.57. Models are not stated |
| Maiden speeches | "The first substantive speech (≥4,000 chars, non-PQ) by each member" (Maiden Speeches page code) |
| Accuracy | None reported: no audit, no error rate, no known-error list |
| Stack | Next.js static export with JSON endpoints under `/api/parliament/`. Database and hosting not stated |

### Worth taking

1. **Government side per sitting.** Its dated rule for who was in government, including the 1955 to 1959 coalition, fits beside `PartyAffiliation`, which already holds dated party history. Small to medium.
2. **Stated heuristics for derived tables.** The maiden speech rule is one line that a reader can check. Any derived view we publish should state its rule the same way. Small.
3. **Oral and written PQ split.** We already have it where it does not. SPRS gives every record a report type, and our `report_type` holds 800 `oral-answer` and 844 `written-answer` or `written-answer-na` reports in the 11th Parliament, and 918 and 2,213 in the 12th. A PQ view over it is small.
4. **Analyses over existing tables.** Speech concentration (Gini of speeches per member), vocabulary drift, co-absence pairs from leave of absence, and adjournment motions with mover and responding minister. Each is a query over `speech`, `attendance` and `speaker`. Co-absence inherits the attendance limit in the data loss register, where a line naming two members keeps only the first.
5. **A public limits page.** Its Disclaimer names the failure and the mitigation in two sentences. Our limits live in `docs/vision.md`, which a website reader will not open.

Semantic search over embeddings is the largest item and the least proven. It reports no evaluation of its similarity search or its topic clusters.

### Where we are ahead

- **Stated accuracy.** It publishes none. We publish three attribution figures after every write, and hand audits: the 17 October audit read 406 linked rows and found 404 right (99.5%, Wilson 98.2% to 99.9%).
- **Presiding officers and the President**, linked to the holder of the day (ADR 0002). It leaves them unlinked.
- **Non-speech lines** kept apart with a `kind` (ADR 0007, ADR 0009). It folds them into the last speaker's turn, so its per-member word counts, Gini and vocabulary drift include text the member did not say.
- **The raw record**, stored as received, and a register of everything cleaned (`docs/data-loss-register.md`). It states neither.
- **Reproducibility.** Golden fixtures for each parser fix, rehearsed writes and a stopping rule. Its method is unpublished, so its results cannot be replayed.
- **Open access.** It has no API or download.

### What its writing does not answer

How it fetches and splits turns, how a turn is linked to a member, where member and party data come from, which models and embeddings it uses, how attendance is parsed, what its adjournment "respondent seniority score" and "sharpeRatio" mean, and its current update cadence.

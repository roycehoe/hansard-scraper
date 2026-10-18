# Comparison with sgparliament.com, 18 October 2026

sgparliament.com is a public reader over the same SPRS record, from the first Legislative Assembly sitting on 22 April 1955 to the present. It splits each debate into speaker turns, links turns to member pages, shows party history within a membership, and adds LLM summaries, topic groups, a PQ explorer and statistics. It offers no API, no download and no source code, and it publishes no accuracy figures. Its disclaimer says the LLM content may contain "hallucinations". The domain was registered in May 2023. Its newsletter, sgparliament.substack.com, signs posts "SGParliament team", but the Substack archive API gives every post with a byline the author Kenneth Tiong (handle `kennethtiong`). That Substack account also runs kennethtiong.com, which publishes the speeches and Parliamentary Questions of Kenneth Tiong, Workers' Party MP for Aljunied GRC. Neither site says in prose that the two share an author.

This report compares its speaker attribution with our speech rows. Our figures come from the local database on 18 October 2026, after the coverage refill. Scripts and raw output are in the session scratchpad and are not kept.

## Verdict

On a stratified sample of 191 reports across Parliaments 0 to 14, with blind judges reading each disputed passage against the source, it credits 95.5% of words to the right person and we credit 99.4%. With Addenda to the President's Address read as nobody's words the figures are 96.8% and 98.5%. Its errors are presiding officers and heads of state left unlinked, and procedural lines and chamber events given to the last speaker. Most of ours are subheadings we give no speaker on purpose. The first pass below, on 27 debates, found the same pattern.

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
- Agreement is not correctness. Both sides could credit the same wrong member. The stratified sample below asks that question.

## Stratified sample: who credits the right person

Weighted by each stratum's share of the corpus text, with Addenda to the President's Address credited to the minister who signs them:

| | sgparliament.com | This project |
|---|---|---|
| Words credited correctly, Parliaments 0 to 14 | 95.5% | 99.4% |
| With Addenda read as nobody's words | 96.8% | 98.5% |
| Gap, 95% bootstrap | | 3.6 to 3.9 points ahead (1.4 to 1.7 with the second reading) |

The two sites share their errors on agreed words: 2 of 449 judged draws were wrong on both (0.45%, Wilson 0.12% to 1.61%). That bound applies to both columns equally, so the levels above are less certain than the gap.

### Method

1. **Strata.** Seven Parliament groups (0, 1 to 3, 4 to 6, 7 to 9, 10 and 11, 12, 13 and 14) by seven report-type groups (oral answers, written answers, bills, Budget, motions, addresses, other), 49 in all. Up to four reports per stratum were drawn from our reports with markdown (seed 20261019), 196 in all. Our rows were read from the local database at about 12:10 on 18 October.
2. **Matching.** Each report was matched to a debate on its site for the same date, by title and then by shared 6-word sequences. A report that matched by neither was tried against every debate of that day. 191 matched. The 5 that did not are one-line reports (four adjournments and a "New Member Sworn") with nothing matching on its site.
3. **Units.** Words were aligned as in the first comparison. A unit is the run of aligned words that sits in one of its turns and one of our rows: 10,744 units over 694,362 words. 8,995 units (650,909 words) credit the same member on both sides, 773 (13,651 words) credit no one on either, and 976 (29,802 words) disagree: 696 credited only by us, 277 only by it, 3 by both to different members.
4. **Judging.** Sonnet judges read each sampled unit against the source text around it and said who the words belong to and whether each site's credit was right. The sites were shown as "Site A" and "Site B" in random order, so a judge could not tell which was ours. The rules: the member speaking, the asker of a question, the minister answering (tables included), the presiding officer in the chair, the head of state for an address, the member for a subheading inside the member's own speech and for a motion read after "I beg to move"; no one for procedural lines, chamber events, headings, editorial notes, division lists, printed order-paper text and "An hon. Member".
5. **Sample.** Up to 10 units per stratum in each direction of disagreement, at random. Units both sites agree on were drawn in proportion to their words, 10 per stratum, and units neither credits 4 per stratum, so that each draw stands for the same number of words. 1,174 judgements in all.
6. **Checks.** The first excerpt builder found the first copy of a repeated sentence rather than the unit's own, which matters for amendment formulas that every mover repeats. It was rebuilt to walk our rows through the source in order, and the 58 units whose excerpt moved were judged again. Every verdict was checked against what the site credits: 7 that scored the printed label rather than the person credited were set by the rule. One verdict was overturned by hand: unit 100118 (Budget, Telecommunications, 1971), where the judge took Ng Kah Ting for the Member for Delta; the label before the passage is his, and Delta is Yeo Choo Kok.
7. **Estimate.** For a disagreement cell, the share of judged words that are right; for a cell drawn by words, the share of draws that are right. Each stratum's cells are summed by their words, and strata are weighted by their share of our speech text. The gap's interval comes from 1,000 bootstrap draws within cells.

### By Parliament group

Addenda credited to the signing minister.

| Parliaments | sgparliament.com | This project |
|---|---|---|
| 0 (1955 to 1965) | 93.6% | 99.8% |
| 1 to 3 (1965 to 1976) | 96.7% | 99.6% |
| 4 to 6 (1977 to 1991) | 96.8% | 96.0% |
| 7 to 9 (1991 to 2001) | 88.9% | 99.9% |
| 10 and 11 (2002 to 2011) | 93.6% | 99.5% |
| 12 (2011 to 2015) | 98.9% | 99.8% |
| 13 and 14 (2016 to 2025) | 98.9% | 99.7% |

Its one lead, Parliaments 4 to 6, comes from one unit of ours and the Addenda reading. In the 1985 Supply Bills we credit the printed "Resolved, That ..." line to Tony Tan, whose name it carries in brackets as mover, and only two units were sampled in that cell.

### Where each side is wrong

Of the 368 judged disagreements, one side alone is wrong in 366.

- **It alone is wrong in 335**: presiding officers left unlinked (161), procedural lines (67) and chamber events (35) given to the last speaker, the Governor, Yang di-Pertuan Negara and President left unlinked (19), member speech (12), printed documents, tables, headings and editorial notes (39), and others.
- **We alone are wrong in 31**: subheadings inside a member's own speech, which we give no speaker on purpose (24), and 7 procedural lines, headings, editorial notes and printed text credited to a member.

Under the rule the judges used, the subheadings count against us. Read as headings with no speaker, they move our figure by less than 0.1 points, because they are short.

### Gaps this found in our parser

Both sites miss these, so they are worth fixing:

- A question printed under "The following question stood in the name of Ms Foo Mee Har" is credited to no one. It belongs to the member named.
- A "The Chairman" ruling headed "Announcement by Mr Speaker" in the Committee of Supply of the 1980s is credited to no one. It belongs to the Speaker of the day.
- A bare "The Chairman" in a Committee of Supply with no chair note in reach stays unlinked (2006, 2014, 2018).
- Addenda to the President's Address are credited to the minister in some years (1971 and 1990 to 1994 in the sample) and to no one in others (1968, 1981 and 2006).
- A printed "Resolved, That ... [Dr Tony Tan]" line is credited to the mover (1985). Under ADR 0007 a procedural line has no speaker.

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
3. **Oral and written PQ split.** We already have it where it does not. SPRS gives every record a report type, and `written-answer-na` holds oral questions that Question Time did not reach, not written ones. In the 11th Parliament our `report_type` holds 800 reports answered orally (`oral-answer`), 517 oral questions not reached (`written-answer-na`) and 327 filed for written answer (`written-answer`). In the 12th the three are 918, 1,144 and 1,069. A PQ view over it is small.
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

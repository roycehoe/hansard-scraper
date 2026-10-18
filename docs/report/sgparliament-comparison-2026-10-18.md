# Comparison with sgparliament.com, 18 October 2026

sgparliament.com is a public reader over the same SPRS record, from the first Legislative Assembly sitting on 22 April 1955 to the present. It splits each debate into speaker turns, links turns to member pages, shows party history within a membership, and adds LLM summaries, topic groups, a PQ explorer and statistics. It offers no API, no download and no source code, and it publishes no accuracy figures. Its disclaimer says the LLM content may contain "hallucinations". Its newsletter, sgparliament.substack.com, is bylined Kenneth Tiong, and the domain was registered in May 2023.

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

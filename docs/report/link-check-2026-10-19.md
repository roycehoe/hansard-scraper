# Link check with Parliament 15, 19 October 2026

This check tests whether a linked speech is credited to the right person, across the whole corpus including Parliament 15, which the 19 October backfill added. It repeats the hand check of the 17 October audit ([north-star-audit-2026-10-17.md](north-star-audit-2026-10-17.md), O4) with a new seed and an eighth stratum.

It checks links only. It does not test how a report's text is split into speeches, so the speech fidelity loop's figures ([speech-fidelity-loop.md](speech-fidelity-loop.md)) still cover Parliaments 0 to 14 only.

## Verdict

463 of 464 linked rows are credited to the right person: 99.78%, Wilson 98.8% to 100.0%. Weighted by each stratum's linked rows it is 99.82%. No row is linked to the wrong member. Parliament 15 has 58 of 58 right, Wilson 93.8% to 100.0%. The whole check clears the 95% lower bound that done test 4 in `docs/vision.md` sets. One stratum alone cannot: with 58 rows and no error, the lower bound is 93.8%, and it takes 73 rows with no error to reach 95%.

| Stratum | Right | Wilson 95% | Linked rows in stratum |
|---|---|---|---|
| Parliament 0 | 57 / 58 | 90.9% to 99.7% | 104,193 |
| Parliaments 1 to 3 | 58 / 58 | 93.8% to 100.0% | 55,485 |
| Parliaments 4 to 8 | 58 / 58 | 93.8% to 100.0% | 154,676 |
| Parliaments 9 to 11 | 58 / 58 | 93.8% to 100.0% | 199,224 |
| Parliament 12 | 58 / 58 | 93.8% to 100.0% | 82,994 |
| Parliament 13 | 58 / 58 | 93.8% to 100.0% | 133,042 |
| Parliament 14 | 58 / 58 | 93.8% to 100.0% | 207,422 |
| Parliament 15 | 58 / 58 | 93.8% to 100.0% | 62,050 |
| All | 463 / 464 | 98.8% to 100.0% | 999,086 |

## Method

58 linked rows were drawn at random from each stratum, seed 20261019, with read-only queries on the remote database. `hansard_replica` holds no Parliament 15 rows, so it could not be used. Each row came with its report's stored source HTML and derived markdown, so the check sent no request to SPRS. The strata are the 17 October audit's seven plus Parliament 15. Unlike that audit, there is no date cutoff.

Eight Claude Sonnet readers, one per stratum, judged each row against the source HTML: right, wrong or unsure. The orchestrating session, Claude Opus, then checked their work:

- It re-read every row marked wrong or unsure.
- It settled the 10 chair rows marked unsure. In the newer system the source prints a note such as "[Deputy Speaker (Mr Seah Kian Peng) in the Chair]". In the older system the HTML's `MP_Speak` metadata names the Speaker, as for A. P. Rajah in 1965 and 1966. Report 34249 of 21 March 1978 has the line "Thereupon Mr Speaker left the Chair of the Committee", which puts Yeoh Ghim Seng in the chair. The rest follow from "Mr" or "Mdm" and the dates of office, as in the 17 October audit. All 10 are right.
- It read 5 of each reader's right calls against the source, 40 in all, and agreed with all 40.

Most readers found each row's text in the HTML with a script that took the nearest speaker label before it, and read the odd rows by hand. The orchestrator's spot check is what backs the right calls that no reader read by eye.

## The wrong row

- 702616 (Lee Kuan Yew, report 39193, 16 November 1961): "Appendix C(Cols 0093-0102)", a caption in the index of a tabled list of appointments that follows his written answer. No member spoke it. It is the same class as row 922416 in the 17 October audit, a line of a printed schedule.

## Overturned

- 227432 (Chua Sian Chin, report 36740, 20 December 1968): the reader marked it wrong. The words "(i) rape under section 375 of" appear twice in the source, first in Mr J. F. Conceicao's question and then as the first line of Chua Sian Chin's answer table. The reader matched the first one. The row's neighbours are the answer's lines, so it is right.

## Notes that do not count against a link

- Table lines inside a minister's written answer or a Budget statement were counted as that member's words, under the rule that a written answer is the minister's: 970674, 836374, 990520, 187372, 437666, 459035 and 702647.
- 669502 and 784359 credit E. W. Barker in the chair in 1963 under a People's Action Party label. That is a party label on the Speaker row, not a wrong link.
- 620410 carries a one-line footnote about Mr Thio Chan Bee inside the member's own row.

The packets, the readers' verdicts and the draw script are in the session scratchpad and are not kept.

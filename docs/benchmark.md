# Benchmark

How this project compares with the Singapore Hansard tools a researcher can use today. The README and the website quote this table, so every claim there must trace to a cell here, and every cell here to a source or a measured figure. Surveyed on 18 October 2026. Rerun the measured figures before quoting them after a write that moves them.

## The table

| | This project | SPRS | Pair Search | sgparliament.com | Par-leh-mate |
|---|---|---|---|---|---|
| Who runs it | Royce Hoe, independent | Parliament of Singapore | Open Government Products, with Parliament | Kenneth Tiong, by the Substack byline | parleh-mate, independent |
| Coverage | 22 Apr 1955 to 8 Apr 2025, 41,838 reports. Parliament 15 is not loaded | Live to 7 Oct 2026. 1955 start not probed | 1955 to January 2024 at its 2024 build. Current end not stated | 22 Apr 1955 to 7 Oct 2026, 1,758 sitting days | 10 Sep 2012 to 7 Mar 2024 in its public repo |
| Unit of text | One row per utterance, with a `kind` for non-speech lines | One HTML page per report | One report | One turn per printed speaker | One paragraph |
| Speech linked to a member | 937,091 of 1,051,868 rows linked to a `Speaker` row | No. A bold printed name only; member fields null in the hits read | Not stated | Yes, to a member page | By cleaned name match |
| Presiding officers and the President | Linked to the holder of the day (ADR 0002) | No | Not stated | No, measured | Not stated |
| Procedural lines and chamber events | Rows of their own with no speaker (ADR 0007, ADR 0009) | Printed in the text | Not stated | Folded into the last speaker's turn, measured | Not stated |
| Published accuracy | Three attribution figures after every write; hand audit of 17 Oct 2026: 404 of 406 linked rows right (99.5%) | None | Click rank only: average 3.2 against 23 for other official search | None | None; a disclaimer of "inevitable parsing errors" |
| Raw source kept | Every API response stored as received, with a register of what is cleaned | It is the source | Not stated | Not stated | Raw JSON kept in its repo |
| API or download | Not yet public | Undocumented JSON endpoints; no bulk download | None public | None | Code CC0-1.0; data in BigQuery, access required |
| Search | Full-text over speech rows; by member through `speaker_id` | Keyword; an `mpName` filter on printed names | Keyword and semantic (e5 embeddings, ColBERTv2 rerank) | Keyword, filters, LLM topic groups, similarity search | Dashboard; liveness unconfirmed |
| Update lag | Not live | Within 11 days of a sitting at least; not stated | Not stated | About 10 days in 2023; not stated now | Not stated; main repo last pushed 13 Mar 2025 |

The SMU portal for the 12th Parliament (2016) is still online at s3-ap-southeast-1.amazonaws.com/hansardbrowser and is a frozen visual browser of one Parliament, so it is left out of the table.

## Attribution measured against sgparliament.com

`report/sgparliament-comparison-2026-10-18.md` compares the two record by record. On 27 debates the two credit the same member for 148,334 of 148,347 words both credit. The stratified sample with judged correctness is in the same report.

## Sources

- SPRS: JSON endpoints called on 18 Oct 2026 (`searchResult`, `getHansardTopic`, `getHansardReport`), the calls in `gateway/`. The terms of use at https://www.parliament.gov.sg/terms-of-use say "the Contents of this Site shall not be reproduced, republished, uploaded, posted, transmitted or otherwise distributed" without the prior written permission of Parliament. They do not say whether they cover sprs.parl.gov.sg, and no Hansard reuse licence was found.
- Pair Search: https://www.parliament.gov.sg/newsroom/events/details/ai-powered-search-engine-for-singapore's-hansard-reports ("allows anyone to access, search, and analyse public government records"), https://reports.open.gov.sg/pairsearch ("Built for public officers, citizens", a pilot, the click figures), https://hack.gov.sg/hack-for-public-good-2024/2024-projects/pairsearch/ (coverage, Vespa, e5, ColBERTv2). Its landing page answered curl with HTTP 403, so access today was not checked.
- sgparliament.com: `report/sgparliament-comparison-2026-10-18.md`.
- Par-leh-mate: https://github.com/parleh-mate/singapore-parliament-speeches (README, `resource-json/` listing, licence via the GitHub API). https://parlehmate.onrender.com/ gave no answer to curl and HTTP 503 to a fetch on 18 Oct 2026. Its name matching is described in `peer-projects.md`.
- This project: `docs/vision.md` "Measuring progress", `docs/report/north-star-audit-2026-10-17.md`, and the local database on 18 Oct 2026.

## Open questions

- Whether Parliament's terms of use cover redistributing Hansard text, and whether written permission is needed before the API or a download goes public.
- SPRS: first sitting served, update lag, and whether `mpName` matches anything beyond printed text.
- Pair Search: access today, current end date, member attribution, API terms.
- Par-leh-mate: data after March 2024, download without BigQuery access, a member ID column, whether its site is up.

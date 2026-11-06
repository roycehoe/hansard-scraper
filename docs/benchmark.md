# Benchmark

How this project compares with the Singapore Hansard tools a researcher can use today. The README and the website quote this table, so every claim there must trace to a cell here, and every cell here to a source or a measured figure. Surveyed on 18 October 2026; Telescope added on 4 November 2026. Rerun the measured figures before quoting them after a write that moves them.

## The table

| | This project | SPRS | Pair Search | Telescope | sgparliament.com | Par-leh-mate |
|---|---|---|---|---|---|---|
| Who runs it | Royce Hoe, independent | Parliament of Singapore | Open Government Products, with Parliament | Open Government Products, from Hack for Public Good 2025; a "Limited Release" since 10 Feb 2025, which OGP defines as "not officially resourced" | An individual author | parleh-mate, independent |
| Coverage | 22 Apr 1955 to Oct 2026. 41,838 reports to 8 Apr 2025, and Parliament 15 added on 19 Oct 2026, for 1,758 sittings | Live to 7 Oct 2026. 1955 start not probed | 1955 to January 2024 at its 2024 build. Current end not stated | Parliamentary questions only. Latest sitting 7 Oct 2026; oldest seen 7 Sep 1967; highest record id seen 30,795, against this project's 31,969 question reports. Total not stated | 22 Apr 1955 to 7 Oct 2026, 1,758 sitting days | 10 Sep 2012 to 7 Mar 2024 in its public repo |
| Unit of text | One row per utterance, with a `kind` for non-speech lines | One HTML page per report | One report | One question report, shown as the SPRS HTML with its page markers left in the text | One turn per printed speaker | One paragraph |
| Speech linked to a member | 999,086 of 1,115,831 rows linked to a `Speaker` row | No. A bold printed name only; member fields null in the hits read | Not stated | Per report only, from the SPRS "MPs Speaking" field. No asker or answerer: a member is "involved in" a question | Yes, to a member page | By cleaned name match |
| Presiding officers and the President | Linked to the holder of the day (ADR 0002) | No | Not stated | Not stated | No, measured | Not stated |
| Procedural lines and chamber events | Rows of their own with no speaker (ADR 0007, ADR 0009) | Printed in the text | Not stated | Not stated | Folded into the last speaker's turn, measured | Not stated |
| Published accuracy | Three attribution figures after every write; hand audit of 17 Oct 2026: 404 of 406 linked rows right (99.5%) | None | Click rank only: average 3.2 against 23 for other official search | None | None | None; a disclaimer of "inevitable parsing errors" |
| Words credited to the right person, measured 18 Oct 2026 | 99.4% (98.5% with Addenda read as nobody's) | Not applicable: no member links | Not measured | Not measured | 95.5% (96.8%) | Not measured |
| Raw source kept | Every API response stored as received, with a register of what is cleaned | It is the source | Not stated | Not stated | Not stated | Raw JSON kept in its repo |
| API or download | Not yet public | Undocumented JSON endpoints; no bulk download | None public | Undocumented tRPC JSON endpoints behind the site; no download | None | Code CC0-1.0; data in BigQuery, access required |
| Search | Full-text over speech rows; by member through `speaker_id` | Keyword; an `mpName` filter on printed names | Keyword and semantic (e5 embeddings, ColBERTv2 rerank) | Semantic (vector embeddings), listing the members in the results; an LLM summary of each question; LLM "areas of interest" from a member's last 20 questions; related questions | Keyword, filters, LLM topic groups, similarity search | Dashboard; liveness unconfirmed |
| Update lag | Not live | Within 11 days of a sitting at least; not stated | Not stated | Same last sitting as SPRS (7 Oct 2026) on 4 Nov 2026 | About 10 days in 2023; not stated now | Not stated; main repo last pushed 13 Mar 2025 |

The SMU portal for the 12th Parliament (2016) is still online at s3-ap-southeast-1.amazonaws.com/hansardbrowser and is a frozen visual browser of one Parliament, so it is left out of the table.

## Attribution measured against sgparliament.com

`report/sgparliament-comparison-2026-10-18.md` compares the two record by record. On a stratified sample of 191 reports over Parliaments 0 to 14, judged blind against the source, sgparliament.com credits 95.5% of words to the right person and this project 99.4%, a gap of 3.6 to 3.9 points. With Addenda to the President's Address read as nobody's words the figures are 96.8% and 98.5%. Quote both readings, or the first with the reading named.

## Sources

- SPRS: JSON endpoints called on 18 Oct 2026 (`searchResult`, `getHansardTopic`, `getHansardReport`), the calls in `gateway/`. The terms of use at https://www.parliament.gov.sg/terms-of-use say "the Contents of this Site shall not be reproduced, republished, uploaded, posted, transmitted or otherwise distributed" without the prior written permission of Parliament. They do not say whether they cover sprs.parl.gov.sg, and no Hansard reuse licence was found.
- Pair Search: https://www.parliament.gov.sg/newsroom/events/details/ai-powered-search-engine-for-singapore's-hansard-reports ("allows anyone to access, search, and analyse public government records"), https://reports.open.gov.sg/pairsearch ("Built for public officers, citizens", a pilot, the click figures), https://hack.gov.sg/hack-for-public-good-2024/2024-projects/pairsearch/ (coverage, Vespa, e5, ColBERTv2). Its landing page answered curl with HTTP 403, so access today was not checked.
- Telescope: https://www.hack.gov.sg/2025/telescope/ (PQs only, "Limited Release" of 10 Feb 2025, and "we decided not to" split asker from answerer because older transcripts are inconsistently formatted). The live site at https://telescope.gov.sg is a client-rendered Next.js app; its FAQ text and its tRPC calls were read from the page bundles on 4 Nov 2026 with curl. The FAQ says an MP's topics come from "a large language model" summarising "the last 20 questions / answers of each MP", and the PQ count is every PQ "the MP has participated in (whether asking or answering)" from "MPs Speaking". `transcript.getLatestSittingDate` returned 7 Oct 2026; `mp.getAll` returned 498 members (391 ex-MPs) with 70,206 member-PQ pairs; `transcript.get` on id 12708 returned the SPRS HTML with "Page: 70" inside a sentence, an LLM summary and the two members; searches for "Barisan Sosialis" returned questions from 7 Sep 1967. OGP's https://www.hack.gov.sg/about-hfpg/ defines a Limited Release: "it's not officially resourced, so don't expect regular updates and we may shut it down eventually." The site's JavaScript was last modified on 28 Oct 2026, and its member list holds Parliament 15 members with their current offices. A LinkedIn post found by search, which could not be fetched, names Latasha Lenus of OGP and Jing Yi Lai as its builders. Its FAQ says it "reproduces parts of the Hansard. The copyright to the Hansard is owned by the Singapore Government".
- sgparliament.com: `report/sgparliament-comparison-2026-10-18.md`.
- Par-leh-mate: https://github.com/parleh-mate/singapore-parliament-speeches (README, `resource-json/` listing, licence via the GitHub API). https://parlehmate.onrender.com/ gave no answer to curl and HTTP 503 to a fetch on 18 Oct 2026. Its name matching is described in `peer-projects.md`.
- This project: `docs/vision.md` "Measuring progress", `docs/report/north-star-audit-2026-10-17.md`, and the local database on 18 Oct 2026.

## Open questions

- Whether Parliament's terms of use cover redistributing Hansard text, and whether written permission is needed before the API or a download goes public.
- SPRS: first sitting served, update lag, and whether `mpName` matches anything beyond printed text.
- Pair Search: access today, current end date, member attribution, API terms.
- Telescope: how many question reports it holds, and whether its oldest is the 1955 one.
- Par-leh-mate: data after March 2024, download without BigQuery access, a member ID column, whether its site is up.

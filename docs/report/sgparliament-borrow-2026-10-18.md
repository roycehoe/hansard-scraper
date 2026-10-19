# What to borrow from sgparliament.com, 18 October 2026

The question was what sgparliament.com does that this project should take, judged against [vision.md](../vision.md): a complete, queryable record for researchers studying political history at scale. The earlier [comparison](sgparliament-comparison-2026-10-18.md) measured its attribution and listed five things worth taking. This report checks those five, reads the parts of the site that pass did not, and ranks the candidates.

## Verdict

Take their revision check. Each debate page compares "our first copy of this section against the text Parliament publishes now" and shows the words Parliament changed. Of 84 debates sampled, 18 of the 47 from the newer system carry changes, and none of the 37 from the older system. SPRS edits its record after publication, and this project would not notice. Raw rows carry no fetch date, every stage skips what it already stores, and when one report id is stored twice the first copy becomes the `Report`. The check serves objective 1, which promises the raw response "exactly as received", and the raw-first strategy. It is also the only candidate where waiting loses data. SPRS keeps no history, so a version nobody fetched is gone. Every other candidate below rests on text we already hold and can be built in any month. The runner-up is a dated record of offices held. Their career pages compute one for Parliaments 12 to 15, and the attendance lists we store print it for every sitting since 1955.

## Ranked candidates

| Rank | Candidate | Objective | We have it? | Cost | Lands in | Their rule sourced? |
|---|---|---|---|---|---|---|
| 1 | Capture Parliament's revisions to the record | 1, raw first | No | Small to start, medium in full | Migration, `scripts/`, ADR, loss register | Yes: both sides of each diff are SPRS text |
| 2 | Offices held, by sitting | 3, 4 | Text stored, no field | Medium | Stage 7, `attendance` or a new table, loss register | Yes: printed in the attendance list |
| 3 | Government or opposition on each date | 4 | Party by date yes, governing parties no | Small | `data/` file, table | Stated, not cited |
| 4 | Spoken or written, by report type | 2 | `report_type` yes, no mapping | Small | `docs/data-dictionary.md`, a view | Stated |
| 5 | The question lifecycle, and three wrong definitions in our dictionary | 2, 6 | Mostly | Small | `docs/data-dictionary.md`, parser later | SPRS's own section names |
| 6 | Debates followed across sittings | 2 | No | Medium | New link table, script | Title rule stated, rest LLM |
| 7 | Motion outcomes | 2 | Procedural rows only | Medium, after 6 | Derived table | Unknown |
| 8 | Their party histories as leads | 4 | Yes, sourced | Small | `data/party_affiliations.json` | Not sourced |

## Method

- Their pages are a Next.js static export (build `8Zil_7vxb7lmo2zPRFyyg`). I read the `__NEXT_DATA__` block of the home page, the member, sitting and motion lists, 8 member pages, 1 sitting page and 84 debate pages, and the page code of all 32 page bundles.
- Debate sample: 48 pages, 6 per decade of the debate sitemaps (seed 20261018), then 36 more from 10 September 2012 to 15 April 2025 (seed 20261019).
- 163 requests to sgparliament.com over 15 minutes, all with curl and no browser. Two to the Substack, which has published nothing since 2 November 2024, so its 10 posts were not reread.
- Their `robots.txt` reads `Disallow: /api/`, because "crawlers with unique query strings bypass the edge cache and bill an invocation each". I called no `/api/` endpoint. What their rules derive server-side is therefore unknown, and the page code is the evidence.
- Five calls to SPRS: one search for 18 February 2019, one `getHansardTopic`, the search page, its script bundle and `/search/fetchData`.
- I did not touch the database. Scratch files are in the session scratchpad and are not kept.

## 1. Capture Parliament's revisions to the record

**Evidence.** Each debate page carries `debate.revisions` with `comparedOn`, a list of `changes` and a `more` count. Each change has a `kind` (`section_title`, `event_text`, `event_added` or `event_removed`), a `pct` and `segs`, a list of kept (`=`), removed (`-`) and added (`+`) runs. The page labels it "Revised by Parliament after first publication" and says "The transcript on this page is Parliament's current text" (page code of `/debate/[id]`).

[Debate 9496](https://www.sgparliament.com/debate/9496) is an oral answer of 18 February 2019 on screening work permit applicants, compared on 16 October 2026. Lee Bee Wah's "concern on their maids" became "concern about", "MOM's" became "the Ministry of Manpower's (MOM)", and Zaqy Mohamad's "So, when I talked about adverse conduct" became "When I talk about adverse conduct". I fetched the same item from SPRS (`getHansardTopic`, id `oral-answer-1923`). It now holds every later wording and none of the earlier ones.

In the sample:

| Debates | With changes |
|---|---|
| Newer system, 2013 to 2025 | 18 of 47, 38% (Wilson 26% to 53%) |
| of which 2015 to 2019 | 14 of 19 |
| of which 2020 to 2025 | 4 of 25 |
| Older system, 1955 to 2010 | 0 of 37 (upper bound 9.4%) |

The 18 debates hold 40 changes. 31 change an utterance's text, by a median of 2.4% of it and at most 37.5%. Most are copy-editing: acronyms spelt out, punctuation, "benefitted" to "benefited". Some change a member's words. Walter Theseira's "eligible families who are not coming forward" became "families which are not coming forward" (debate 8415, 5 November 2019). 7 add an utterance, all of them chair calls with a time, such as "Mdm Speaker: Ms Sylvia Lim. 4.44 pm", five of them in the Registration of Criminals (Amendment) Bill of 29 February 2016 (debate 13701). 2 change a title: "Seller" became "Seller's" (debate 9972), and debate 200 gained the word "Trafficking".

Their site went up in 2023. The first newsletter post is dated 15 July 2023. So Parliament made the changes to the 2015 to 2019 records after that, and the changes to records of 2023 and 2024 show that the edits continue.

**Why a researcher wants it.** A historian who quotes the Hansard needs to know the quoted text can change after the citation. Work on wording, such as vocabulary drift or the formality score on their `/language` page, partly measures the editor. Added chair calls change turn counts. What Parliament changed in its own record, and when, is itself a finding. Objective 1 promises the raw response "preserved exactly as received". That promise needs the date it was received.

**What we hold.** Nothing. `hansardwebsiteresponse` has no fetch date (`database/hansard_website_response.py`). The docs give the load dates, for example the 14 October 2026 load of text from 10 September 2012 on (vision.md). Each stage skips rows it already stores ("Staged, incremental population" in vision.md). When raw rows share a `report_id`, only the first becomes a `Report` (`populate/reports.py`, data-loss-register.md). So a refetch would either not happen or land as a second raw row that nothing reads. Our newer-system copy is probably the revised text: SPRS served the revised wording for the one item checked, and our load ran two days before their comparison. I did not check our stored rows.

**Cost.** Small to start, medium in full.

1. A `fetched_at` column on both raw tables. Existing rows stay NULL or take the documented load date, marked approximate.
2. A read-only script that refetches a stratified sample of newer-system reports and diffs the raw `content` against the stored copy. It measures drift since 14 October and decides whether step 3 is worth doing.
3. If drift is real: a new raw row for each changed body, never an update, with its fetch date. An ADR deciding which version feeds `Report` and the speech rows, a loss register row, and a refetch on a schedule. That is about 21,000 newer-system requests through the existing gateways.

**Risks.** The method is sourced by construction, because both sides of each diff are SPRS text. Their earlier copies are not downloadable, only shown as diffs, so versions before our first fetch are lost to us. Diff the raw `content`, not the markdown, so our own cleaning never reads as a revision. A revised report means new speech rows, and rebuilding stored reports is the planned, rehearsed write that vision.md describes. SPRS has also re-keyed items before (`bill-intro-1318#` came back as `budget-1318#`, coverage-gaps.md), so match a refetched item on date and title as well as id.

## 2. Offices held, by sitting

**Evidence.** Each member page has one `role` string, the current office. For [Zaqy Mohamad](https://www.sgparliament.com/mp/zaqy-mohamad) it is "Acting Minister-in-charge of Muslim Affairs, Senior Minister of State for Defence and Deputy Leader of the House". For David Marshall it is null. The `/career-trajectory` page asks "How fast do new MPs rise through office ranks from their parliamentary debut?" It ranks offices from 0 to 5, "Backbencher", "Parl. Secretary", "Sr Parl. Secretary", "Minister of State", "Sr Minister of State" and "Minister", for cohorts 12, 13, 14 and 15 only. That needs an office per member per date. Shared page code, `getSeniorityScore`, maps a role string to the rank by substring, and `/adjournment-motions` uses it for "Government Response Levels". Where the dated roles come from is behind `/api/`. The limit to Parliaments 12 to 15 fits the structured attendance list SPRS gives from 10 September 2012.

**Why a researcher wants it.** Whether a speaker held office, and which office, is one of the most common variables in legislative research. It separates front bench from back bench, follows a portfolio's answers across reshuffles, and dates a member's rise. Objective 4 fixes identity as name, party and Parliament, and office is the dated attribute it lacks. [peer-projects.md](../peer-projects.md) section F already notes that our `Speaker` row has no dated roles.

**What we hold.** The text, not the field. Every attendance entry prints the office after the constituency: "[Title] [Name] [(Constituency)][, Portfolio/role]" ([parsing.md](../parsing.md)). The newer list reads `{"mpName": "Mr K Shanmugam (Nee Soon), Minister for Home Affairs and Minister for Law.", ...}` (peer-projects.md), and a 1963 entry carries "Parliamentary Secretary to the Prime Minister" (data-loss-register.md). Stage 7 cuts each entry to a name and its first bracket (data-loss-register.md, the row on name entries). The post-2012 hand check says "long portfolio dropped" (`docs/report/post-2012-load/f_handcheck.md`). The printed text survives in `sitting.markdown_content` and `sitting.attendance_list` for the 1,333 older sittings with HTML and the 386 newer ones (vision.md). Our dated office tables are hand lists of Speakers, Deputy Speakers, Chief Ministers, Prime Ministers and heads of state (`populate/speaker_resolution_constants.py`, `utils/speaker_terms.py`). SPRS's `/search/fetchData` groups newer office labels by ministry in `ministryVOList[].portfolios`, for example "The Minister of State for Manpower" under MINISTRY OF MANPOWER. That gives a sourced map from office to ministry for the newer labels.

**Cost.** Medium, with no new fetch. Stage 7 keeps the office text it already parses, in an `office` column on `attendance` or in a small table keyed by speaker and sitting. It needs a loss register update and a count of entries with an office before and after. A rank like theirs is a separate view, built later if anyone needs it.

**Risks.** Sourced and checkable row by row against the printed list. Older lists carry OCR damage, such as the 1963 entry that begins "Tunah)" in the register, and offices wrap across lines: write #3 deleted 45 attendance rows that were office fragments read as names. The record gives an office only on sitting days, so start and end dates are bounded by sittings, not by the date of appointment. Their rank treats "Acting Minister" as Minister. Copy it only as a stated rule.

## 3. Government or opposition on each date

**Evidence.** The [About page](https://www.sgparliament.com/aboutus) says "All Opposition MPs" means members whose party was not in government at the time: "since 5 June 1959, every party but the PAP; from 1955 to 1959, every party but the Labour Front, the Alliance and the Singapore People's Alliance. Nominated Members, the 1955 Assembly's ex officio and nominated members, and the Speaker are on neither side." Shared page code (`/stats` and nine other pages) runs the rule as SQL against a table `sgp_government_parties` with `party`, `date_start` and `date_end`, joined to `sgp_party_affiliation` (`mp_id`, `party`, `date_start`, `date_end`) and `sgp_parliamentary_sittings`. `/adjournment-motions` uses it for the share of motions "moved by members whose party was not in government at the time".

**Why a researcher wants it.** After office, the side of the House is the most used control: opposition questions, the opposition's share of debate, how the 1955 to 1959 coalition differed from what came after. It changes what a researcher can query, not how a page looks.

**What we hold.** A member's party on any date: `speaker.party` holds the ballot party per Membership, and `partyaffiliation` holds the 92 sourced spans of the 39 Memberships with a change. We do not hold which parties formed the government on a date.

**Cost.** Small. A `data/` file of governing spans, each with a party, dates and a source, loaded into a table, plus a rule for members with no party side (Nominated, ex officio, the Speaker). It needs perhaps five spans.

**Risks.** Their rule is stated but cites nothing, and their table is not published. Two calls in it are contestable: whether the ex officio officials of 1955 to 1959 count as government, and how to treat Non-Constituency Members. Record each call with a source, as `data/party_affiliations.json` already does for party changes.

## 4. Spoken or written, by report type

**Evidence.** `/substantive-speeches` offers three measures, and "Spoken floor speech" leaves out written answers because they are "laid before the House as text, not read aloud". Its tooltip for the all-text measure warns that "a portfolio Minister's written answers are usually the larger share of their total, so this flatters front-benchers against back-benchers". `/participation` shows "Thousands of words of written PQ answers laid before the House but never spoken. Excluded from Airtime".

**Why a researcher wants it.** Any count of what members said, such as words per member or the speech Gini in the earlier report, is wrong if it includes text nobody said aloud. Ministers' written answers would dominate it.

**What we hold.** Partly. `report_type` marks `written-answer`, `written-answer-na` and `written-statement`, and the President's Address reports hold ministers' written addenda. Nothing says which types reach the record on paper. `kind` says what a row is, not how it got there.

**Cost.** Small. A table in `docs/data-dictionary.md` mapping each report type to spoken, written or mixed, and a derived column in a view if the app needs it.

**Risks.** Low. `president-address` is mixed: the address is spoken and the addenda are written. Mark it mixed rather than guess.

## 5. The question lifecycle, and three wrong definitions in our dictionary

**Evidence.** `/pq-explorer` splits questions three ways: "Filed for oral answer and answered on the floor", "Written Answers to Questions for Oral Answer" ("Questions intended for oral but answered in writing") and "Filed for written answer". It reports a "gov accession rate" ("Oral-intended questions that received oral answers") and an "MP Oral Intent Rate". Debate events carry `isQuestion` and `questionNo`, and 58 of the 64 question events in the sample had a number. It has no split for "all of the 11th Parliament and roughly a fifth of the 12th".

**The lifecycle.** A member files a question for oral answer or for written answer. A question filed for oral answer ends as `oral-answer` when Question Time reaches it, and as `written-answer-na` when it does not, with the minister's reply printed in writing. A question filed for written answer is `written-answer`. An office holder who corrects their earlier words does it aloud as a `clarification` or on paper as a `written-statement`.

**What we hold.** The split through `report_type`, for every Parliament from the 5th, when `written-answer-na` begins. SPRS's own section list (`/search/fetchData`, `orSectionList`) names `written-answer-na` "Written Answers to Questions for Oral Answer not Answered by End of Question Time" and `written-statement` "Corrections by Written Statements". [data-dictionary.md](../data-dictionary.md) got three types wrong until 19 October 2026. It called `written-answer-na` "A question for which no written answer was available", `written-statement` "A written ministerial statement tabled in the chamber", and `clarification` "A follow-up clarification to an oral or written answer", though every clarification is spoken and most correct earlier words. The earlier comparison counted `written-answer-na` with the written answers, but SPRS's label makes them oral questions. We drop question numbers ("Text dropped inside reports that have rows" in vision.md), and no row marks a question apart from its answer, though the first row of a written answer starts with "asked" (`docs/report/post-2012-load/e_verdict.md`).

**Checked against the record.** On 19 October 2026 I read the rows behind each definition on the replica, read-only. Its latest sitting is 8 April 2025.

| Check | Finding | Examples |
|---|---|---|
| `written-statement` is a written correction | Of the 74 reports, all 69 with text open "Written statement by ... circulated with leave of the Speaker", or of the Deputy Speaker in 3, "in accordance with Standing Order No 29(5)", and give the words as they "should read". Each corrects an office holder. The other 5 have no text, because SPRS answers HTTP 400 for them (data-loss-register.md) | 178, 4240, 12246; no text: 6640 |
| `clarification` is spoken | All 54 read as spoken in the chamber, and none cites Standing Order 29(5). 7 are not an office holder correcting the record: 3 titled "Clarification by Member", 1 "Clarification by Nominated Member of Parliament", 2 "Point of Order" (Leong Mun Wai, 2022) and the Government Whip on the speaking order | 46018, 242; members: 44377, 9045, 7392, 14353; points of order: 6990, 5692; whip: 14119 |
| `written-answer-na`, 2003 to 2011 | The 622 reports thought to have an empty `Section Name` do not. Their header puts the section on the line of the title, and the regex that counted them read to the end of the line. 621 read "Oral Answers to Questions Not Reached", 5 of them in the singular, and 1 reads "Oral Answers to Questions" (24867, a quirk below). The 20 I read, picked by hash, are each one numbered question and one written reply | 23343, 21348, 43280 |
| `written-answer` before 22 December 1981 | `for oral answer` matches 22 of 343. 19 open "The following Question for Oral Answer stood on the Order Paper", or its plural, from 1957 to 1969. The other 3 are addenda to oral answers of 1956 and 1957 and a 1958 question that mentions a question "not for oral answer". In the other 321, "stood on the Order Paper", "stood in the name", "not reached", "not being present" and "Standing Order" match nothing. Reading their openings found 2 more, "To ask" questions under the opening of 38545 on 7 June 1963. That makes 21: 14 cite Standing Order 16(2) or 20(2), and 7 went written because the minister or the member was absent | 37970, 38776, 39124; under 38545: 38559, 38569 |
| `oral-answer` of 1 June 1998 headed "Oral Answers to Questions Not Reached" | 29 reports. None holds a chair call, a "Sir" or a supplementary question. Each is one numbered question, two members' in 27227, and one written reply | 27290, 27197, 42783 |

**Source quirks.**

- No `written-answer-na` exists before 22 December 1981. The 21 earlier oral questions answered in writing are `written-answer`.
- 39 `oral-answer` reports hold no spoken exchange. 29 of 1 June 1998 and 5 of 16 October and 10 November 2003 are headed "Oral Answers to Questions Not Reached", and 5 of 16 October 2003 are headed "Written Answers to Questions". On 10 November 2003 the question "Internet Chatrooms" is stored twice with the types swapped: the written reply, 24876, is `oral-answer` and the spoken exchange, 24867, is `written-answer-na`. We keep SPRS's types.
- We drop the question number. The source prints "73 **Mr Melvin Yong Yik Chye** asked the Minister ..." in report 685, and our speech row starts at "asked the Minister" (data-loss-register.md, the rows on question numbers).

**Counts.** Reports and questions per Parliament, an estimate. "Questions" counts matches of `\*\*\s*asked (the|whether)` in `markdown_content`, because one report can hold several questions, and the regex misses other phrasings. The oral columns include the 39 unspoken `oral-answer` reports. "Share not reached" is not-reached questions over all oral questions.

| Parliament | Oral reports | Oral questions | Not-reached reports | Not-reached questions | Share not reached | Written reports | Written questions |
|---|---|---|---|---|---|---|---|
| 9 | 711 | 791 | 286 | 295 | 27% | 250 | 246 |
| 10 | 749 | 803 | 159 | 164 | 17% | 203 | 212 |
| 11 | 800 | 1,012 | 517 | 540 | 35% | 327 | 338 |
| 12 | 918 | 1,170 | 1,144 | 1,195 | 51% | 1,069 | 1,101 |
| 13 | 1,127 | 1,524 | 1,639 | 1,706 | 53% | 1,634 | 1,683 |
| 14 | 1,392 | 2,581 | 3,773 | 4,098 | 61% | 4,610 | 4,896 |

From the 12th Parliament on, about half or more of the questions filed for oral answer get a written reply instead.

**Cost.** Small for the three definitions, corrected on 19 October 2026. Small to medium for a question flag and the question number, which change the parser and so need a rehearsed write.

**Risks.** Their quota heatmap ("Each MP may file up to 5 questions per sitting day, of which up to 3 for oral answer") applies one cap to every term and cites no Standing Order. Leave it.

## 6. Debates followed across sittings

**Evidence.** On `/participation`, "MPs who spoke counts everyone who spoke in the debate, following it across sittings when it was adjourned and resumed. Two motions taken together share one debate." `/debate-topics` says "Title-match groups share identical titles; semantic groups are LLM-detected topic clusters."

**Why a researcher wants it.** A second reading spread over three sitting days is one debate. Counting its speakers, reading it in order or finding its outcome needs all three days.

**What we hold.** One `Report` per SPRS item, sometimes with a "(Continued)" subtitle (data-dictionary.md). Nothing joins them.

**Cost.** Medium. A link table grouping reports by title, report type and a date window, with the rule written down and a hand-checked sample.

**Risks.** The title rule is deterministic and checkable. Titles recur for unrelated items, such as "Adjournment" and the yearly Committee of Supply heads, so bound each match by type and date. Leave out their LLM groups.

## 7. Motion outcomes

**Evidence.** `/participation` lists the motions each member moved with "MPs who spoke", "Seconded by" and "Outcome". It leaves out "Bills, amendments to another member's motion, the daily adjournment, Committee of Supply $100 cut motions, business motions and routine statutory resolutions". Seconders appear "only where a Member said so on the floor", and "'not recorded' is the usual case and does not mean the motion went unseconded".

**Why a researcher wants it.** What the House decided belongs in the record: agreed, negatived, amended or withdrawn.

**What we hold.** The deciding lines, such as "Question put, and agreed to" and "Resolved", as PROCEDURAL rows with no speaker ([ADR 0007](../adr/0007-non-speech-lines-get-no-speaker.md), [ADR 0009](../adr/0009-speech-kind-column.md)). No outcome field.

**Cost.** Medium, and it depends on candidate 6, because the deciding line can fall on a later sitting.

**Risks.** How they derive the outcome is behind `/api/`. Build our own rule over the procedural rows and test it on a hand sample. Their seconder note is a good model for stating a limit in one sentence.

## 8. Their party histories as leads

**Evidence.** Each member page has `mp.partyHistory` with `party`, `from` and `to`, and `/mps` lists `parties` for 568 members, 42 of them with more than one. Our verification of 18 October dropped six spans for want of a readable source. Five of them appear in their histories with day dates. A. J. Braga and Mak Pak Shee joined the SPA on 1958-11-10, where we store Mak Pak Shee as Independent from 1959-04-25. Hoe Puay Choo joined the BS on 1962-08-11. Soh Ghee Soon was Independent from 1958-11-13. David Marshall was Independent from 1957-04-17. Their histories also blur what ours keeps apart: Chiam See Tong has one "SDA/SPP" label from 2001, hiding the 2011 move to the SPP that we store. Many spans start on the first sitting of a term (1955-04-22, 1959-07-01), so their dates are snapped to sittings rather than to events.

**Use.** Dated leads for a search of the Hansard for a citable line, never a source. Small, and it moves five spans.

## The earlier list, checked

1. Government side per sitting: confirmed and still worth it. The rule is in their code as a dated table. It is candidate 3.
2. Stated heuristics: confirmed. Maiden speeches are "The first substantive speech (≥4,000 chars, non-PQ)", and the participation and motion pages state their exclusions. This is a writing habit for the app, not data. Our ADRs already do it for the record.
3. Oral and written split: confirmed, with a correction. `written-answer-na` is oral-intended, by SPRS's own label, and our dictionary defines it wrongly. It is candidate 5.
4. Analyses: their speech Gini, vocabulary drift, `leave-pairs` co-absence and written-PQ share are queries we can run any time. Their numbers include the procedural lines their parser folds into turns, and any word-level measure now has to allow for Parliament's copy-editing (candidate 1). Not a borrow.
5. Public limits page: their [Disclaimer](https://www.sgparliament.com/disclaimer) covers only the LLM timelines, in four paragraphs. A limits page is still right for the app, but it is not something to copy from them.

## Considered and rejected

- **LLM output.** Timelines, semantic topic groups, Issue Provenance (match threshold 0.57), the "AI-generated briefing" on member pages, "What does the Speaker Care Most About", and the `mp-principles`, `logical-fallacy` and `discourse-analysis` endpoints named in the page code. None reports an evaluation.
- **`/pap-response`.** "Find and copy government front bench positions on any topic for wargaming." Outside this project's scope, which is the record itself.
- **`/sitting-predictions`.** Forecasts sitting days from past weekday slots. Not part of the record.
- **`/language` style metrics.** Flesch-Kincaid grade, "Heylighen formality F-score" and distinctive phrases, computed on text Parliament has since copy-edited and on turns that include procedural lines.
- **One constituency per member.** `mp.constituency` gives Marshall "Anson" only, though he sat for Cairnhill from 1955. `attendance.location_name` already gives ours by sitting.
- **Stable links to each utterance.** Their "#" button "copies a link to it". peer-projects.md section E already lists stable ids as a gap, and I could not test whether their event ids survive a re-parse.
- **`answeredInWriting`.** The field links an oral question not reached to its written answer. It was null on all 84 sampled debates.
- **Curated reference lists.** The page code names no by-elections, committees, division lists, bill outcomes or constituency boundaries, so there is nothing of that kind to take.

## What I could not find out

- What any `/api/parliament/` endpoint returns. Their robots.txt closes `/api/`, so the derivation of PQ ministries, motion outcomes, dated roles and the dates of their first copies is unknown.
- When Parliament made each revision. The diffs carry only `comparedOn`, 16 October 2026 on all 18.
- Whether our stored newer-system text equals what SPRS serves now. One item matches SPRS's revised wording on their side; our rows were not checked.
- Whether SPRS tags older-system items with a ministry. Its search takes `ministrySelected` and `portfolio` filters, but the 19 newer-system hits for 18 February 2019 returned `portfolio` and `memberName` as null. `hansardwebsiteresponse` keeps neither field, and the loss register lists only the dropped `resultHTML` fields `mpNames` and `footNote`.
- Where their per-sitting offices come from. The structured attendance list is the likely source, not a confirmed one.

## Sources

Fetched on 18 October 2026. Page bundles are from build `8Zil_7vxb7lmo2zPRFyyg` and change their hashed names with each build.

- About, Disclaimer and robots: https://www.sgparliament.com/aboutus, https://www.sgparliament.com/disclaimer, https://www.sgparliament.com/robots.txt
- Debate pages: https://www.sgparliament.com/debate/9496, /debate/8415, /debate/13701, /debate/9972, /debate/200
- Member pages: https://www.sgparliament.com/mp/zaqy-mohamad, /mp/david-marshall, /mp/a-j-braga, /mp/hoe-puay-choo, /mp/mak-pak-shee, /mp/soh-ghee-soon, /mp/s-v-lingam, /mp/chiam-see-tong
- Lists: https://www.sgparliament.com/mps, /sittings, /motions, /pqs
- Page code under https://www.sgparliament.com/_next/static/chunks/pages/: `debate/[id]-e75f0b4f7e49ed80.js`, `sgparliament-586bd3a762d23b63.js`, `career-trajectory-5da36938757699f3.js`, `pq-explorer-3d21b538983afad6.js`, `participation-7c39da4e72e72a3c.js`, `substantive-speeches-84e736943be795d9.js`, `debate-topics-5d0ed94fd66fd3d2.js`, `stats-25a37dc3affe12be.js`, `maiden-speeches-6583299d89e031f4.js`, `adjournment-motions-1efe02d18c953929.js`, `language-2ec6b83f7d6ab08e.js`, `pap-response-338a53f062045f8d.js`, `sitting-predictions-f3f41c51d45197d5.js`
- SPRS: `searchResult` for 18-02-2019, `getHansardTopic` for `oral-answer-1923`, and `https://sprs.parl.gov.sg/search/fetchData`

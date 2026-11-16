# Writing guide

This guide is for anyone who writes or rewrites a document in this repo, person or agent. It is adapted from the writing guide of the hansard site (`app/WRITING.md` in `roycehoe/hansard`) and keeps that guide's principle numbers, so a rule can be compared across the two repos by number. The readers here differ: they write code or study the data, so some of the site's rules are left out and others are added.

Work in this order. Find the document's reader, apply the nine principles, apply the mechanics, then run the checklist at the end on every document you change.

## Which documents this covers

The repo holds two kinds of document ([ADR 0021](adr/0021-living-docs-describe-the-current-state.md)).

- Living documents say how things stand now and are kept up to date: `CLAUDE.md`, `STYLE.md`, `README.md`, `CONTRIBUTING.md`, and the reference docs in `docs/` (`vision.md`, `data-loss-register.md`, `data-dictionary.md`, `scripts.md`, `refresh.md`, `parsing.md`, `coverage-gaps.md`, `office-dates.md`, `benchmark.md` and this guide). Every rule here applies to them.
- Dated records say what was known on their date: the reports in `docs/report/`, the ADRs in `docs/adr/`, and the refine-loop logs. Once written, their content is not rewritten. A new dated record follows this guide, except that it keeps the dates of what it reports.

## What you must not change

- Keep every fact, figure, record date, commit hash, file path, command, flag, table name, column name, enum value and rule. Don't add a claim the text you were given doesn't already make. When rule 3 or rule 9 asks for a who, a when or a scope that the text doesn't state, don't supply it from memory. List the question in your reply instead.
- Keep Parliament's printed words exactly as the record prints them, including speaker labels such as "Mr Speaker" and "The Chairman", and keep any quote from an outside source, such as a website's terms of use, word for word.
- Keep figures exactly as the script that produced them logs them: "515,789 / 521,752 = 98.86%" stays in that form. Keep sample sizes, confidence limits and Wilson intervals. Here they are the point.
- Keep links working. When a heading changes, update every link to its anchor (`git grep '#old-anchor'`).
- If you cut a fact, list it in your reply with the document it belongs in. Earlier figures go to `docs/report/figures-history.md`. A fact about a table goes to `docs/data-dictionary.md`, and a fact about a script to `docs/scripts.md`.

## Who reads each document

| Reader | Documents | What they already know |
|---|---|---|
| An agent or contributor writing code here | `CLAUDE.md`, `STYLE.md`, `docs/scripts.md` | Python, Postgres, SQLModel and Alembic. Not Hansard, Singapore's Parliament, or how this archive was built. |
| The maintainers, deciding what to work on next | `docs/vision.md` | Everything about the project. They want the current state of each objective, the open gaps, and the figures that measure them. |
| A contributor or researcher who wants to know what the data holds and what it loses | `docs/data-loss-register.md`, `docs/data-dictionary.md`, `docs/refresh.md`, `docs/parsing.md`, `docs/coverage-gaps.md`, `docs/office-dates.md`, `docs/benchmark.md` | Databases and, often, how Parliament works. Not this archive's words or its pipeline. |
| Someone opening the repo for the first time | `README.md`, `CONTRIBUTING.md` | Nothing about the project. |

`CLAUDE.md` is loaded into every agent session, so every word in it costs something each time. It holds what an agent must do and must not do, and links to the documents that hold the reference lists.

## Principles

### 1. Answer the question first

The first sentence under a heading answers the heading's question. Background, history and caveats come after it, or not at all. A document's first paragraph says what the document is for.

- Before: "### The three numbers" followed by "`scripts/attribution_text_share.py` prints all three for Parliaments 0 to 11."
- After: "Three numbers measure how much of the record is linked to a member: the ADR 0001 rate, the all-rows rate, and text share. `scripts/attribution_text_share.py` prints all three for Parliaments 0 to 11."

### 2. Define a term the first time, or use a plain word

Assume the reader has never met a word that belongs to Parliament, to this archive, or to the project's own working shorthand. Where such a word first appears in a document, explain it in that sentence or the next, link to the document that defines it, or replace it with a plain word. The project's shorthand counts: a report type such as `atbp`, a label such as "DS-04" or "R20", a round or write number, "Tier A", "the replica". A short name for something the document has not named yet is a new term too.

- Before: "Otherwise the report type decides: the speaker line of an atbp report, ..."
- After: "Otherwise the report type decides: the speaker line of an atbp report (Assent to Bills Passed, the record that the President has assented to Bills), ..."
- Kept as it is, because it defines its term where it first appears: "Tier A errors (wrong speaker, lost or duplicated text, a chamber event or a first reading credited to a speaker)".

When a shorthand label such as "DS-04" names a past piece of work and the text you were given doesn't say what it did, don't guess. List it as a question.

### 3. Answer the next question

After each sentence, ask what this document's reader would ask next. Usually it is who does this, when, where, or what makes it happen. Answer it in the text when the text you were given already holds the answer, and list the question in your reply when it doesn't. Every sentence names who or what acts: a script, a stage, a module, a person. "It", "this" and a bare passive don't tell the reader which.

- Before: "Stores the result in `HansardSittingDateResponse`."
- After: "`populate/hansard_sitting_dates.py` stores the result in `HansardSittingDateResponse`."
- Listed, not answered: "The previous rows live in the `pg_dump` taken before each loop write. Those dumps sit outside git." The next question is where they sit. The text doesn't say, so the writer keeps the sentence and lists the question.

Answer only what this reader would ask. Rule 4 cuts the rest.

### 4. Cut what the reader doesn't need or can work out

Ask two things of every sentence. Would this document's reader miss it if it went? Could they work it out from what the document already says? If they wouldn't miss it, or could work it out, cut it. A paragraph so long that nobody will read it to the end gets cut or broken into a list until someone will.

- Before: "`scripts/attribution_text_share.py` prints the attribution figures by Parliament group and by report type when it is run, with the zero-row reports and single-speaker collapses, and `--output` keeps a copy in a file. `CLAUDE.md` asks for it before and after every parsing or linking change. These tools make it possible to audit specific failure categories without re-running the full pipeline."
- After: the same paragraph without its last sentence, which the reader can work out from the two before it.

### 5. Say how many, then mark each item

When a section covers several kinds of a thing, several steps or several ways to do something, say how many before the first one. Steps that must run in order are a numbered list. Items with no order are bullets.

- Before: "Structural limits that apply by design:" followed by four bullets.
- After: "Four structural limits apply by design:" followed by the same four bullets.
- Kept as it is: "Two things are not recoverable from the raw layer alone, and each says so below:" followed by two bullets.

### 6. Give parallel things the same shape

When two sentences, list items, table rows or headings do the same job, write them the same way, with the same kind of subject, the same opening and the same order. A reader who has read the first can then predict the second. In a list of scripts, each entry opens with the script's name, a colon and a verb in the present tense.

- Before: "`diagnose.py` — inspect parsing failures across the corpus" beside "`fill_sitting_numbers.py`: fills empty `report.sitting_number` ..."
- After: "`diagnose.py`: inspects parsing failures across the corpus" beside "`fill_sitting_numbers.py`: fills empty `report.sitting_number` ..."

### 7. Show one real case, by its id

Explain the rule in your own words first. Then, where a real case makes it concrete, give one, with the id that lets a reader find it: a report id, a row id, a sitting date or a commit hash. Take the case from what the repo already records, never from memory. One case is enough. Don't retell it at length, and don't make the case do the explaining.

- Before: "Sometimes the record prints a column number that cannot be right."
- After: "Sometimes the record prints a column number that cannot be right. Report 21556 prints 3653 between 3562 and 3564." The case comes from [ADR 0013](adr/0013-store-what-the-record-prints.md).

### 8. Keep to the document's subject

Each document has one subject, and a fact that belongs to another document's subject goes there, with a link left behind if the reader needs it. `CLAUDE.md` says what an agent must do. The tables belong in `docs/data-dictionary.md`, the scripts in `docs/scripts.md`, and the daily refresh in `docs/refresh.md`. Say a thing in one place and link to it from the others, because two copies drift apart.

- Before: a paragraph of about 600 words in `CLAUDE.md` listing every table the daily refresh writes, which `docs/refresh.md` lists again as numbered steps.
- After: "`refresh.py` runs once a day and adds the sittings, reports and speech rows SPRS has published since the last stored sitting. It only adds rows, apart from the exceptions listed in `docs/refresh.md`, so a parser fix reaches stored rows only through a supervised write. `docs/refresh.md` lists each step."
- Moved: "The corpus holds 41,801 reports" sat in `vision.md` under "Iterative parsing refinement", a strategy that has nothing to do with the size of the corpus. It goes to the section that counts the corpus.

### 9. Say exactly what is true

Check the scope of each claim. Name the module, script or table that actually acts, and include every case the claim covers. Don't widen a claim to make it simpler, or narrow it to make it tidier. When two documents disagree, the code decides, and the writer lists the disagreement in their reply. If you think a claim is wrong but nothing in the repo says what is right, list it and leave the claim as it is.

- Before: "Both pre- and post-August 2015 API formats are handled faithfully."
- After: "Both formats of the sitting date API are handled: the flat body of sittings before 10 September 2012, and the nested body from that date." `gateway/hansard_report.py` picks the format by the shape of the body, and the nested format starts on 10 September 2012, not in August 2015 (`STYLE.md`, sweep ruling 13).

## Mechanics

### Time and names

These rules come from [ADR 0021](adr/0021-living-docs-describe-the-current-state.md) and apply to living documents.

- Name no person. Where a document must say that a person decided, as the data loss register's Decided column does, write "the maintainers". Elsewhere, state the rule itself and leave out who set it.
- Give no date for when something was decided, and no history of how the project got here. Git, `docs/report/figures-history.md` and the dated records hold the history.
- Keep dates that describe the record or the data, such as "sittings before 10 September 2012" or "Parliaments 7 and 8 (1988 to 1996)", and keep dated file names such as `docs/figures/2026-11-02-write13.txt`.
- A figure that will change says what it was measured after: a write number, with a link to that write's figures file only when the file prints the figure. A figures file holds the three numbers and their breakdowns, so a count of bills, search timings or attendance rows names the write without a link. When the source gives only a date for a count, keep it as "counted on 6 November 2026", because the date says which state of the data the figure describes. Never add a date or a link the source does not give.
- Write numbers ("write #13") stay, without their dates, because the figures files, the data loss register and the dated reports name each write by its number.
- In the register's Decided column, a cell opens with "Maintainers" or "No recorded decision", and may go on to say what was decided. A commit hash in the cell stays.

Examples:

- Before: "Every step that changes or drops source content between the raw API responses and any derived table, with its cost and the reason for it. Since 17 October 2026 this is a project requirement (`CLAUDE.md`, "Data loss register")"
- After: "This register lists every step that changes or drops source content between the raw API responses and any derived table, with its cost and the reason for it. `CLAUDE.md` requires a row for each such step."
- Before: "The Speaker writes and signs it, so its words are his. The maintainers ruled to keep it on 1 Nov 2026, after the accuracy sample counted one as an error."
- After: "The Speaker writes and signs it, so its words are his, and the credit stays even when an accuracy sample counts it as an error."
- Before: "Since 12 November 2026 a row with no label and a `speaker_id` counts as linked in the all-rows rate and the text share"
- After: "A row with no label and a `speaker_id` counts as linked in the all-rows rate and the text share"
- Before: "| Stored, 2 Nov 2026, after write #13 |"
- After: "| Stored after write #13 ([figures](figures/2026-11-02-write13.txt)) |"
- Before: "22 Oct 2026, user: drop the suffix and do not add it to the other Parliaments. Written on the remote on 22 Oct 2026."
- After: "Maintainers: drop the suffix and do not add it to the other Parliaments."

### Sentences

- Split a sentence that a reader has to read twice, and keep the linking word ("because", "but", "so", "which") when you split. A sentence that strings three clauses together with semicolons is three sentences or a list.
- Write paragraphs, not telegrams. Vary sentence length, let some sentences run past 20 words, and keep the word that links one sentence to the next. A run of short sentences of one length with nothing joining them reads as machine-written ([Wikipedia, Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)).
- In `CLAUDE.md` and `CONTRIBUTING.md`, an instruction is an imperative: "Run `poetry run pytest` before every push."
- Use the active voice and name the actor (rule 3). A passive is fine only when the actor is unknown or doesn't matter.

### Punctuation and formatting

- Use the Oxford comma in every list of three or more.
- No em dashes, and no en dash used as one. Use a full stop, a comma or a colon before a list.
- Straight quotes.
- Sentence case for headings: "## Data model", not "## Data Model". A table name or proper noun keeps its capitals.
- Code, paths, commands, table and column names, enum values and flags go in backticks.
- Bold marks a term at the point it is defined, or a list item's name when new detail follows it. Don't bold for emphasis.
- Don't join a term and its plain meaning with "or", because "or" tells the reader they are two different things. Use brackets or a new sentence.
- Use footnotes sparingly. Fix the explanation in the main text first. A footnote holds only an exception the reader doesn't need to follow the document, in two sentences or fewer.

### Terms

- Use one word for one thing, and repeat it. A document that says "speech row" in one sentence, "utterance" in the next and "record" in the third has the reader wondering whether they are three things.
- Keep the archive's words as they are, because each names something specific: report, sitting, speech row, label (the speaker name as the record prints it), link (a `speaker_id` set on a row), credit, kind, Membership (a `Speaker` row, one person in one Parliament), Person (one human, who may hold several Memberships), the older system (`sprs2`, sittings before 10 September 2012) and the newer system (`sprs3`), and Parliament 0 (the Legislative Assembly, 1955 to 1965).
- (from rule 2) Describe the thing first, then give its name, when the name is new to the reader.
- Write a body's full name the first time in each document: the Elections Department, the Attorney-General's Chambers, Singapore Statutes Online (SSO).

### Numbers

- Give a rate as the script logs it, with its numerator and denominator where the script prints them.
- Give a confidence bound with its method and its sample: "999 of 1,000 credited rows right, Wilson 99.44% to 99.98%".
- Write numbers of 1,000 or more with a comma, even where the script prints them without one.

### Voice

- Write plain statements in the third person. Never "I", and never "we", because the reader can't tell who "we" is.
- The software keeps its own name as subject: "the parser", "stage 8", "`scripts/apply_fresh_parse.py`".
- Keep the reason the reader can't work out alone. A rule with its "because" is easier to follow and harder to break by accident. Cut a reason the document already makes plain.

## Checklist

Run this on each document you change, in order, and fix what fails before you move on.

1. Name the document's reader from the table. If the document isn't in the table, stop and ask.
2. Does the first paragraph say what the document is for? Under each heading, does the first sentence answer the heading?
3. Mark every word this reader might not know, the project's shorthand included. Is each defined where it first appears, linked to the document that defines it, or replaced by a plain word?
4. Does any sentence leave its actor, its trigger, or where it happens open? Name them when the text you were given does. Otherwise list the question.
5. For each sentence, would the reader miss it, and could they work it out from what the document already says? Cut it if they wouldn't miss it or could work it out.
6. Before a list of kinds, steps or ways, does a sentence say how many? Are ordered steps numbered?
7. Do sentences, list items and table rows that do the same job start the same way?
8. Is each case real, taken from the repo, and given with the id that finds it?
9. Does any paragraph belong to another document's subject? Move it there and link to it.
10. Does any claim name a bigger or smaller group than the one that acts, or leave out cases it covers? Does it agree with the code?
11. Is there any personal name, any date of a decision, or any sentence of history? Are record dates, dated file names, write numbers and measurement points kept?
12. Does every list of three or more have the Oxford comma? Is there any em dash, curly quote, title-case heading, or bold used for emphasis?
13. Is it third person, with no "I" or "we"? Read each paragraph aloud. If it sounds like a telegram, join the sentences that share a subject or a cause. If a sentence needs reading twice, split it.
14. Is every fact, figure, path, command, hash, quote and link target unchanged, and does every link still resolve? List every fact you cut, with the document it belongs in, and every question you couldn't answer from the text.

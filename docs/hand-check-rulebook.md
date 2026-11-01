# Hand check rulebook

This rulebook sets the rules for the hand check of 1,000 credited paragraphs (the site's ADR 0009 and this repo's ADR 0015). One Sonnet reader and one Opus reader judge the credited speaker of every packet against it, and a script compares the words. Royce reads every row either reader or the text script flags, and his verdict is final. A row both readers and the script pass is never read by a person. An AI reader can add a flag but never clear one. Sections 1 to 9 state the rules and say where each comes from. Section 10 is the reader prompt, word for word. If section 10 and sections 1 to 9 disagree, sections 1 to 9 win, and section 10 gets a fix in its own commit. This file is committed before the pilot.

Brief decisions and plan items cited below are in the site repo's `plans/human-hand-check-brief.md` and `plans/human-hand-check.md`, which are not committed.

## 1. Terms

- Credited row: a speech row with a speaker id.
- Snapshot: the row as stored at the draw. Every verdict judges the snapshot, never the live page.
- Packet: one page per row, built by script. It carries no verdict.
- Speaker verdict: `RIGHT`, `WRONG` or `RECORD_DOES_NOT_SAY`. It is the only verdict a reader gives.
- Text verdict: `MATCHES`, `LISTED_CHANGE`, `SUBSTANTIVE_ERROR` or `COSMETIC_ERROR`. Only Royce gives it.
- Difference class: `LISTED_CHANGE`, `SUBSTANTIVE` or `COSMETIC`. A Sonnet reader suggests one for each difference the script found. It is a hint for Royce and clears nothing.
- Flag: a row sent to Royce (section 8).
- Stored copy: the Official Report as the scraper stored it from SPRS. Every packet's source text comes from it (section 6).
- Live check: the comparison of the stored copy with today's SPRS text for 50 reports (section 4, rule 9).
- Tier A, B, C: section 7.

Source: Royce's decisions of 1 Nov 2026 (brief terminology), site ADR 0009.

## 2. The speaker rule

1. The speaker verdict judges the credit: the person the database credits against what the Official Report prints. The answer is `RIGHT`, `WRONG` or `RECORD_DOES_NOT_SAY`.
2. The row's speaker is the person named by the label printed at the start of its paragraph, or, when the paragraph has no label of its own, by the nearest label above it. The packet's context runs from that label down to the paragraph.
3. `RIGHT`: the record names the credited person. The same person under a spelling variant, another title or a missing initial is right. A typo the record prints is not an error. Sources: site ADR 0006, scraper ADR 0013.
4. `WRONG`: the credit names the wrong person, or the record names no one. A Resolved line, a caption, a procedural line (a first reading, "Question put", "Adjourned accordingly"), a chamber event, a heading or a time stamp credited to a member is wrong. So is a chamber event left inside the member's own paragraph ("[Applause]", "[Interruption]", "rose"), which credits the member with a direction as speech. So is a credit linked to another person: when `Credited to:` names the person the record names but `Linked person:` names someone else, the credit is wrong (Tier A, by rule 5). Sources: brief decision 12 and scenario 4; register lines 60 to 66 (procedural lines and first readings), 82 (inline events), 94 and 95 (Resolved lines), 96 (appendix link captions); stopping rule boundary cases at lines 26 and 27.
5. Tier: a heading or a bare time stamp is Tier C; every other wrong credit is Tier A. Source: brief decision 12, stopping rule line 28.
6. `RIGHT` by ruling, four cases:
   1. A signed notice of assent credited to the Speaker is right (Royce, 1 Nov 2026, `docs/vision.md:60`; the attribution chain is at `:54-58`). The Speaker writes and signs it, so its words are his.
   2. A bracketed vernacular pointer inside a member's paragraph, such as "[Please refer to Vernacular Speech.]", is right (Royce, 18 Oct 2026, `docs/vision.md:201`, `docs/report/speech-fidelity-loop.md:781`; scope widened to every bracketed "Please refer to" pointer at `:870-871`). Underscores left around the pointer are a text matter, cosmetic and Tier C. This ruling replaces the "not decided" paragraph at line 107 of `reader_prompt_r5.md` and `reader_prompt_r6.md`, both under the gitignored `plans/done-tests/`.
   3. Table lines inside a minister's written answer are the minister's (brief decision 12; register line 56, a table row of the current speaker). A caption on a line of its own that names a table or an appendix and ends on a printed column range, such as "(Cols. 1053-1054)", is not a table line; credited to a member it is wrong (register line 96).
   4. A paragraph credited from the report's header or signature. A single-speaker report is credited to the one name its `MPs Speaking` field lists, or to the person who signs it (`docs/vision.md:55-58`; register lines 37 and 38). When no labelled paragraph sits above the match, the packet's context starts at the top of the report and includes its header table. The credit is right when the header field or the signature names the credited person. If the field lists several names or none and nothing else in the report names the speaker, the answer is `RECORD_DOES_NOT_SAY`.
7. `RECORD_DOES_NOT_SAY`: the packet cannot settle who spoke. It takes no tier. It counts as wrong when results are counted, so a reader uses it only when the packet cannot settle the credit, and says why in the note. Source: brief decisions 12 and 13.
8. Role labels ("Mr Speaker", "The Chairman", a ministerial title) are judged by section 3.

## 3. Role credits

Source for every rule here: [ADR 0015](adr/0015-hand-check-role-credits.md), brief decision 13, and the independent review of 1 Nov 2026 that stood in for Royce. Royce can overturn it before the report is published. A change after publication means judging the role credits again.

1. A role label is one of two kinds.
2. An office label names an office with one holder on the sitting date: "Mr Speaker", "Mdm Speaker", "The Prime Minister", "The Chief Minister", a head of state, a Deputy Speaker on a day with one holder or with one holder matching the printed Mr or Mdm, or a ministerial title. The by-date office-holder table decides it. The packet's role section lists the table entries for that office on that date (holder, form of address, first and last day, source). The credit is `RIGHT` when the credited person is the holder. A holder who is someone else makes it `WRONG`, Tier A. No entry makes it `RECORD_DOES_NOT_SAY`. When the table lists more than one holder of the office on the sitting date, the holder is the one whose form of address matches the printed Mr or Mdm. If that leaves more than one, or none, the table does not settle it: write `RECORD_DOES_NOT_SAY`. The ADR rules on chair labels. This reading of office labels is the rulebook's own.
3. A chair label names the chair, which is not an office: "The Chairman", "Mr Chairman", or a bare "Mr Deputy Speaker" on a day with two Deputy Speakers. The sitting's own chair marks decide it: the last mark before the row and the first after it, from the same sitting (an earlier report of that sitting when the row's own report has none), and any suspension or resumption line between them. The packet's role section for a chair label lists those marks, each ending with the title of the report it came from, and also lists the Speaker and Deputy Speaker table entries for the sitting date, so that a mark naming an office can be settled by the table.
4. A chair mark is a "[X in the Chair]" note; an "X left the Chair" or "Thereupon ... the Chair" line; a label of the Speaker or of a Deputy Speaker that names one holder, such as "Mr Speaker:"; or the report's `MPs Speaking` tag of a chair role, which never overrides a nearer mark.
5. A mark that names a person settles the credit. A mark that names an office, such as "[Mr Speaker in the Chair]", goes through the table (the entries the role section lists). The credit is `RIGHT` when the governing mark, read this way, gives the credited person. When the table lists more than one holder of that office on the sitting date, the holder is the one whose form of address matches the printed Mr or Mdm in the mark. If that leaves more than one, or none, the table does not settle it: write `RECORD_DOES_NOT_SAY`.
6. Anything else is `RECORD_DOES_NOT_SAY` and counts as wrong: no mark; a mark voided by a line between it and the row; marks before and after that name different people; a mark that contradicts the credit or the label. A conflict is never `RIGHT` on the table alone.
7. The table is built from cited outside sources (parliament.gov.sg, the Prime Minister's Office and Cabinet pages, the Singapore government directory, and Wikipedia only where it cites a primary source). It is not copied from `SPEAKER_TERMS` or `DEPUTY_SPEAKER_TERMS`, because stage 8 credited rows with those. Any disagreement with them is logged as a finding. The form of address ("Mr" or "Mdm", stored as `MR` or `MDM`) is a cited field of each entry, not read from `DEPUTY_SPEAKER_WOMEN`.
8. The report gives three counts: credits settled by a chair mark, credits settled by the table, and `RECORD_DOES_NOT_SAY`. The check cannot see a change of chair the record does not print, the limit that the 17 Oct 2026 amendment to ADR 0002 accepts for linking.
9. "The Chairman" is not an office, so a table cannot settle a chair label. On 26 Oct 2026, 10,089 chairman-label rows and 4,579 bare "Mr Deputy Speaker" rows were credited (register line 167), about 15 in a sample of 1,000, and read as table-only they would all count as wrong and lift the wrong-speaker ceiling from 0.30% to at least 1.69% ([ADR 0015](adr/0015-hand-check-role-credits.md)).

## 4. The text rule

Readers give no text verdict (plan item P22). The text script finds the differences, every row with a difference goes to Royce, and Royce gives the text verdict. A Sonnet reader suggests a class for each difference the script shows it, as a hint. The rules below are what Royce applies and what each class rests on.

1. Royce's text verdict compares the snapshot transcript with the Official Report's text for the same paragraph, taken from the stored copy (rule 9). He judges the whole paragraph, however long (brief decision 16).
2. The printed speaker label and its colon are not part of either text; they are judged under section 2. Anything printed before the label, such as a question number, stays in the compared text. Source: register lines 85, 86 and 48, where a label leaves the row's text.
3. An error is any difference from the Official Report that section 5 does not list, and that the methods page does not list. A typo the Official Report itself prints is not an error (site ADR 0006, scraper ADR 0013). Source: brief decision 14.
4. Substantive errors make the headline: a word, number or name lost, added or changed; words glued or split; a paragraph cut or merged where no listed change allows it; a passage duplicated or reordered. Cosmetic errors are reported beside the headline: stray markup or stray spacing. Source: brief decision 14.
5. Royce's four text verdicts: `MATCHES` (no difference beyond what the script ignores); `LISTED_CHANGE` (every difference is in section 5 and nothing else differs); `SUBSTANTIVE_ERROR`; `COSMETIC_ERROR`. When a paragraph has both a listed change and an error, the verdict is the error. A Sonnet reader's classes rest on the same rules, one class per script difference: `LISTED_CHANGE` for a difference in section 5, `SUBSTANTIVE` for one that rule 4 names, `COSMETIC` for one that rule 6 names. A class is a hint and decides nothing.
6. "Stray markup": a doubled marker (`__`, `**`), an unmatched `_` or `*`, a marker where the source has no emphasis, a backslash, `](`, `&amp;`, or a space before a comma or full stop. A matched pair of single underscores around text the source prints in italics is the markdown form of that italics and is not an error, except around a vernacular pointer, where the underscores are cosmetic by the 18 Oct 2026 ruling. This is the rulebook's reading of the brief's "stray `**` or `__`"; register line 97 records that the parser keeps emphasis markers and is not an approval of stray ones. The text script drops `**` and every `_` before it compares (section 8), so a stray `__` or `**` never shows as a word difference, and readers give no text verdict. The script counts them apart: each row whose stored text holds a `**` or `__` that its matched SPRS paragraph does not is marked in the text output, and the report gives the total beside the cosmetic figure as a Tier C side figure. The count is not a flag reason, so it sends no row to Royce, and Royce may still mark a stray marker he sees in a flagged row (Royce, 1 November 2026).
7. A footnote number: "[1]" for a raised 1 is a listed change (register line 71). A raised number run into the word with no brackets (2481 for 248 and a raised 1) is a glue error. The packet shows raised numbers raised so a reader or Royce can tell (section 8).
8. Joined paragraphs: two or more source paragraphs stored as one row are a listed change when a Column or Page marker, a preformatted line wrap, an adjournment or suspension line split over source blocks, or a bracketed note cut by a marker sits between them (register lines 36, 74 to 77), or when the report is a single-speaker report whose body is one row (lines 37 and 38). Any other join is a substantive error, Tier B.
9. The source copy and a later SPRS edit. Every packet is built from the stored copy of the Official Report, the raw SPRS answer the scraper stored. Its source text, match status and word differences all come from that copy, and the build fetches nothing from SPRS for them. For 50 reports chosen by a fixed seed from the sampled reports, the build also fetches today's SPRS text and compares it with the stored copy. A packet of a checked report carries a live check note that says whether today's text equals the stored copy. When it differs, the note also gives the row's match status against today's text, and every row of that report goes to Royce. The report states "stored copy matched live SPRS in x of 50". Royce judges the snapshot against the stored copy the packet shows, so the verdict rules do not change. A difference caused by a later edit to an older report is still an error. Register line 129 ("keeps its first text") covers only reports the daily refresh stored, from 18 Oct 2026, and nobody should stretch it. The note tells Royce whether to blame the parser or SPRS. This is the check's own rule. Source: plan items P12 and P30 and the triage ruling of 1 Nov 2026 on them.
10. Tiers for text errors: section 7.

## 5. Listed changes

The `Name` column is the name this rulebook, the report and Royce's page use for the change. A reader's class for any of them is `LISTED_CHANGE`.

| Name | What the row shows | Register |
|---|---|---|
| `nbsp_space` | a non-breaking space, or an emphasis tag holding only one, is an ordinary space | 25 |
| `character_reference` | an en dash, curly quote or accented letter kept as printed; in reports 20889, 43635, 22063, 22624, 23133, 23268, 23325 and 24685 the row keeps the ASCII fold ("-" for an en dash, "'" for a curly quote) | 26 |
| `lost_closing_quote` | "�?" after a Latin letter, digit or punctuation mark is a closing curly quote | 27 |
| `mojibake_repair` | a run of broken characters re-read as UTF-8 ("faÃ§ade" is "façade") | 28 |
| `lost_character_restored` | a lost character restored where one answer fits ("entrep�t" is "entrepôt"; "�" before a digit is "£") | 29 |
| `byte_order_mark` | a U+FEFF removed | 30 |
| `newer_system_cleanup` | an empty emphasis tag becomes a space, a `(proc text)` marker is removed, an inline image is removed | 32, 33 |
| `column_page_marker` | a Column or Page marker paragraph absent | 34 |
| `joined_across_break` | one row for a paragraph cut by a marker, wrapped `<pre>` prose, an adjournment or suspension line split over blocks, or a bracketed note cut by a marker | 36, 74, 75, 76, 77 |
| `single_speaker_collapse` | header fields, table rules, heading markers and the leading title absent; lines joined by a space; paragraph breaks lost | 37, 38 |
| `html2text_escape` | a backslash escape undone | 39 |
| `bare_ampersand` | a bare "&" kept as "&" ("R&D") | 40 |
| `link_url_dropped` | link text kept, URL gone; the space before a link inside emphasis moved inside the link | 41, 47 |
| `bold_merge` | consecutive bold lines, or a bold line wrapped over a break, merged with a space | 49 |
| `no_row_line` | a heading, bare time stamp, section title, "[Mr Speaker in the Chair]" note, image, table rule or question number absent from the row | 51, 52, 54, 87, 88, 89, 90 |
| `doubled_paragraph` | the first copy of a paragraph the source prints twice around a stray tag absent | 78 |
| `footnote_marker` | a raised footnote number written "[N]" | 71 |
| `chamber_event_cut` | a bracketed direction taken out of the paragraph and set in the next row; one space where the text joins | 82 |
| `language_note` | "(In Mandarin):" and its close mark removed from the label or the start of the text | 84, 85 |
| `nul_replacement` | U+FFFD where the source held a NUL byte | 125 |

Line numbers are those of `docs/data-loss-register.md` at the commit before this one.

Lines 96 (lower-case appendix captions still credited) and 97 (emphasis markers kept) record a state the parser is in, not an approval, so neither makes a fault right. A difference the table does not list is an error.

## 6. The source copy and the match status

1. Every packet's source text comes from the stored copy of the Official Report (section 4, rule 9), so every packet has a source to compare with.
2. A taken-down report needs no replacement, because the snapshot is judged. Readers are never told which reports are taken down. The report never names a taken-down slug (`docs/takedown.md` in the site repo).
3. Match status `not found`: no source run was found, and the row goes to Royce. He judges from the context. If the row's words appear there in another form, he judges the difference. If they appear nowhere, the text verdict is `SUBSTANTIVE_ERROR`, Tier A. A reader judges the speaker from the context as usual and gives no class, because the packet shows no word differences. Match status `inexact`: the packet shows the closest run, and each source line the row lacks appears as a deletion. Royce judges the whole run, and a Sonnet reader gives a class to each numbered difference.

## 7. Tiers

The tiers are the speech fidelity stopping rule's (`docs/speech-fidelity-stopping-rule.md:17-21`). These are the classes from its table that a hand check can carry:

| Tier | Classes |
|---|---|
| A | `wrong_speaker`, `lost_text`, duplicated or reordered text, a chamber event credited to a speaker, a first reading credited to its presenter |
| B | `glue`, `split`, a paragraph cut across rows at a column, page or preformatted line break (F4) |
| C | `markup_residue`, `mangled_label` where the label still names the right person, a heading or bare time stamp credited to a speaker |

Its boundary cases (`:23-28`) that bear on the hand check: F4 goes in Tier B, because the text survives under the right speaker, in order. A `mangled_label` that names the wrong person is `wrong_speaker`, Tier A. A chamber event credited to a speaker is Tier A. A first reading collapsed under its presenter is Tier A. A heading or a bare time stamp credited to a speaker is Tier C.

The mapping:

- Speaker: heading or bare time stamp credited, Tier C; every other wrong credit, Tier A. A `mangled_label` that names the wrong person is `WRONG`, Tier A.
- Text (Royce's verdict): lost, added, changed, duplicated or reordered text is Tier A. These are the stopping rule's `lost_text`, duplicated and reordered text; an added or changed word is a lost word plus a gained one, which the stopping rule does not list by name. Glued or split words, and a paragraph cut at a column, page or line break or merged where section 4 rule 8 allows no join, are Tier B (`glue`, `split`, F4). Stray markup and spacing are Tier C (`markup_residue`).
- Each error carries its tier so the result can be set beside the earlier AI Tier A figure. A reader gives a tier only to a wrong speaker. Royce gives the tier of a text error.

## 8. What the text script does and the flag rule

These are the script's published rules. They freeze after the pilot, as do the draw script and the flag rule.

1. Text normalisation is, in the order the operations run: turn `<br>` into a space, drop tags, decode HTML character references, drop the markdown markers `**` and every `_` (a lone `*` stays), fold runs of whitespace to one space (a decoded `&nbsp;` and U+00A0 count as whitespace), trim both ends. It never deletes a space. Tags are dropped before references are decoded, so an escaped `&lt;b&gt;` stays text. Decoding character references counts as reading the HTML, not cleaning it. A stray `__` or `**` is erased by this step, so no word difference shows it; the script counts it apart (section 4, rule 6). It is applied to both texts.
2. The compared source text of a turn's first paragraph starts after its printed label and the colon that ends it; anything printed before the label stays.
3. A row matches exactly when its normalised text equals the normalised text of one or more consecutive whole source paragraphs joined by a space. That covers a row the parser joined across a column break, and a single-speaker collapse only when nothing inside it was dropped. Anything else is inexact or not found. The closest run of an inexact row is the span from the source paragraph holding its first words to the one holding its last words, every paragraph between included.
4. The word diff lists each deleted, inserted or replaced run of words between source and row. `delete` is source words the row lacks; `insert` is row words the source lacks; `replace` is source words that the row has as different words. The packet record keeps the diff for every row. A Sonnet reader's packet shows it, numbered, only when the match is inexact and the diff is not empty; an Opus reader's packet never shows it.
5. Footnote markers, repaired mojibake, cut-out chamber events and question numbers survive normalisation, so they show as differences and flag their rows. The script is a pointer; Royce judges.
6. The packet shows bold, italic, superscript and subscript (as `<B>`, `<I>`, `<SUP>` and `<SUB>`) in text copied from the Official Report, so a reader or Royce sees a raised footnote number raised. The diff still uses the normalised text.
7. The gap check is information, not a flag reason and not a verdict. It skips source paragraphs the register says get no row (markdown headings, bare time stamps, chair annotations, column and page markers, markup-only lines) and reports whether the next remaining paragraph starts the next site row.
8. Flag rule: a sampled row is flagged when either reader's speaker verdict is not `RIGHT`, the text script finds any difference, the match is not exact, or its report is one of the 50 checked against today's SPRS and today's text differs from the stored copy. Readers give no text verdict: when the script finds no difference after normalisation the row equals the source, and when it finds one the row is already flagged. A gap check, a role section and a live check that matches add no flag. (Brief decisions 9 and 11; plan item P22.)

Sources for this section: plan items P16 to P19, P22, P24 and P28.

## 9. The verdict line

A reader writes one JSON object per line in `verdicts.jsonl`. Its keys are those of `HandCheckVerdict` in `schemas/hand_check_verdict.py`:

- `packet_id`: twelve lowercase hex digits, as the packet heading prints them.
- `speaker_verdict`: `RIGHT`, `WRONG` or `RECORD_DOES_NOT_SAY`.
- `speaker_tier`: `"A"` or `"C"` with `WRONG`, else `null`.
- `note`: a string.
- `difference_classes`: a list of `LISTED_CHANGE`, `SUBSTANTIVE` or `COSMETIC`.

The line says nothing about the words of the paragraph beyond those classes, because readers judge the speaker only. The flag script checks the number of classes against the packet. A Sonnet line on a packet whose match status is `INEXACT` and that has differences carries exactly one class per numbered difference, in number order. Every other line carries `[]`, and an Opus line always does. The schema gives `difference_classes` an empty default, but the reader instructions ask for the key on every line. The values are written exactly as listed, in upper case. A line is invalid if it has an extra key, a missing key, a word outside the lists, a tier on a verdict that is not `WRONG`, no tier on `WRONG`, or the wrong number of classes. A batch with an invalid line is run again.

An example line:

`{"packet_id": "3f9a1c07b2de", "speaker_verdict": "WRONG", "speaker_tier": "A", "note": "The label is Mr Lim, but the paragraph is credited to Mr Tan.", "difference_classes": []}`

## 10. Reader instructions

You check Hansard paragraphs against the Official Report. Each packet in your batch holds one paragraph of the Singapore Parliament record exactly as a database stores it, with the Official Report's own text for the same paragraph. For every packet you decide one thing: whether the paragraph is credited to the right person. A historian will search this table by speaker, so a wrong speaker is the worst fault. A script compares the words of each paragraph, and a person reads every paragraph it flags, so you do not judge the words. Your one text task is to give a class to each word difference a packet shows, as set out under "Classes for word differences".

The first line of this message is `BATCH_DIR = ` followed by the path of your batch directory. That directory is your whole world. It holds one file, `packets.md`.

### Rules for the work

- Read only your batch directory. Do not open a database, the repository, a website, another batch, another reader's files, or any earlier check of these rows. Open nothing outside `BATCH_DIR`.
- Judge the snapshot. A packet shows the paragraph as it was stored on the day of the draw. The live site is not your concern and you have no need of it.
- Read every packet whole, from its heading to its last line. Read each paragraph in full, however long it is. Do not skim, and do not stop at the first fault you find.
- Write no code and no keyword filter. Do not write a script, a regular expression or a search to find faults, compare text or sort packets. View `packets.md` with the Read tool, in chunks. Where a packet shows word differences, they come from a script. Treat them as a pointer and read the two texts yourself, because the script can show a difference that is not one.
- Do not edit `packets.md`. Write only `verdicts.jsonl`, in `BATCH_DIR`.
- Use only what the packet shows. Do not use outside knowledge of who held an office or sat in the chair.

### What a packet shows

Each packet starts with a heading `## Packet <packet id>`. A legend at the top of `packets.md` says that in text copied from the Official Report `<B>...</B>` marks bold, `<I>...</I>` italic, `<SUP>...</SUP>` raised text and `<SUB>...</SUB>` lowered text, and that snapshot text is shown as the database stores it, with its own markers. The Official Report text in a packet comes from the stored copy of the report, the raw answer the official site (SPRS) gave when it was stored. Nothing is fetched when a packet is built. A packet holds these parts, each under a `###` heading of the same name. Three appear only on some packets: Word differences, Role section and Live check note.

- **Label and credited person**: `Label:` is the label the record prints for the paragraph (`(none)` when the paragraph has no label of its own), `Credited to:` is the person the database credits with it, and `Linked person:` is the person that credit is linked to (`(none)` when there is no link).
- **Report**: its title, then `Sitting date:` and `Report type:`.
- **Snapshot text**: the paragraph as stored. This is what you judge.
- **Context**: the Official Report's paragraphs from the nearest label above the matched paragraph down to it, one per line, and then a line `After the paragraph:` with the one paragraph after it. When no label sits above, the context starts at the top of the report and includes its header table. It reads `Not available.` when no source text was matched.
- **Match status and Matched source**: a `Status:` line, then the Official Report's text for the paragraph, with its printed label and colon removed. The status is `exact` (the snapshot equals one or more whole source paragraphs joined by a space, once tags, bold and italic markers, non-breaking spaces and runs of spaces are ignored), `inexact` (the closest run of source paragraphs is shown, and each source line the snapshot lacks appears as a deletion) or `not found` (no run of source paragraphs was found).
- **Word differences**: present only on some packets. When it is present, it is a script's numbered list of the words deleted, inserted or replaced between the source and the snapshot, after it ignores tags, bold and italic markers, non-breaking spaces and runs of spaces. Each line reads `1. delete: source "...", snapshot "..."`, numbered from 1, with `insert` or `replace` in place of `delete` where they apply. `delete` is a source word the snapshot lacks. `insert` is a snapshot word the source lacks. `replace` is source words that the snapshot has as different words. A packet without this part has nothing for you to classify.
- **Gap check**: information only. Do not judge it.
- **Role section**: present only when the label is a role. It holds office-holder table entries, and for a chair label also chair marks. The next section describes it.
- **Official record link**: for Royce's use. Do not open it.
- **Live check note**: present only for a report that was also checked against today's SPRS text, which is 50 reports chosen by a fixed seed. It says either `Today's SPRS text equals the stored copy this packet is built from.` or `Today's SPRS text differs from the stored copy this packet is built from.` In the second case a line follows: `Against today's SPRS text the match status is` and a status. It changes none of the rules below.

### The speaker verdict

Write one of three values in `speaker_verdict`: `RIGHT`, `WRONG` or `RECORD_DOES_NOT_SAY`.

`RIGHT`: the record names the credited person as the speaker of this paragraph. The person is named by the label printed at the start of the paragraph, or by the nearest label above it in the context when the paragraph has none of its own. The same person under a spelling variant, another title or a missing initial is right. A typo the record prints is not an error.

`WRONG`: the credit names the wrong person, or the record names no one. A credit linked to another person is wrong too: if `Credited to:` names the person the record names but `Linked person:` names someone else, write `WRONG`. Each of these credited to a member is wrong: a caption, a Resolved line, a procedural line (a bill's first reading, "Question put", "Adjourned accordingly"), a chamber event, a heading, a time stamp. A chamber event left inside the member's own paragraph, such as [Applause], [Interruption] or "rose", is wrong too. Give `speaker_tier` "C" when the paragraph is a heading or a bare time stamp, and "A" for every other wrong credit.

`RECORD_DOES_NOT_SAY`: the packet cannot settle who spoke, for example because the role rules below leave a role label open. It takes no tier. It counts as wrong when results are counted, so use it only when the packet really cannot settle the credit, and say why in `note`.

Four cases are `RIGHT` by ruling:

- A signed notice of assent credited to the Speaker is right (Royce, 1 November 2026). The Speaker writes and signs it, so its words are his.
- A bracketed vernacular pointer inside a member's paragraph, such as [Please refer to Vernacular Speech.], is right (Royce, 18 October 2026). Any bracketed "Please refer to" pointer counts. Stray underscores left around the pointer are a text matter and not yours to judge.
- Table lines inside a minister's written answer are the minister's. A caption on a line of its own that names a table or an appendix and ends on a printed column range, such as (Cols. 1053-1054), is not a table line, and is wrong if credited to a member.
- A paragraph credited from the report's header or signature. A single-speaker report is credited to the one name its `MPs Speaking` field lists, or to the person who signs it. The credit is right when the header field or the signature names the credited person. If the field lists several names or none and nothing else in the report names the speaker, write `RECORD_DOES_NOT_SAY`.

### Role labels

A role label has a role section in its packet. There are two kinds.

An office label names an office with one holder on the sitting date: Mr Speaker, Mdm Speaker, The Prime Minister, The Chief Minister, a head of state, a Deputy Speaker on a day with one holder or with one holder matching the printed Mr or Mdm, or a ministerial title. The role section starts `Office label:` and the office, and lists the table entries for that office on the sitting date, one line each: holder, form of address, first and last day (or `no end date`), source. If the credited person is the holder, write `RIGHT`. If the holder is someone else, write `WRONG` with `speaker_tier` "A". If the section says `No entry in the table.`, write `RECORD_DOES_NOT_SAY`. When the table lists more than one holder of the office on the sitting date, the holder is the one whose form of address matches the printed Mr or Mdm. If that leaves more than one, or none, the table does not settle it: write `RECORD_DOES_NOT_SAY`.

A chair label names the chair and not an office: The Chairman, Mr Chairman, or a bare Mr Deputy Speaker on a day with two Deputy Speakers. The role section starts `Chair label.` and lists the table entries for the Speaker and the Deputy Speaker on the sitting date, in the same form (or `No entry in the table.`). Then, under `Chair marks:`, it lists the marks: the last mark before the row (`Last mark before the row:`), any suspension or resumption line between that mark and the row (`Between that mark and the row:`), any such line between the row and the next mark (`Between the row and the next mark:`), and the first mark after the row (`First mark after the row:`). Each line ends with the title of the report it came from, in the form `(report: <title>)`. When the row's own report has no mark before the row, the last mark may come from an earlier report of the same sitting. `No chair mark found.` means there is none. A mark is a "[X in the Chair]" note, an "X left the Chair" or "Thereupon ... the Chair" line, a label of the Speaker or of a Deputy Speaker that names one holder, such as "Mr Speaker:", or the report's `MPs Speaking` tag of a chair role. That tag never overrides a nearer mark.

- A mark that names a person settles the credit.
- A mark that names an office, such as "[Mr Speaker in the Chair]", goes through the table: the table's holder of that office on the sitting date, from the entries the role section lists, is the chair. When the table lists more than one holder of that office on the sitting date, the holder is the one whose form of address matches the printed Mr or Mdm in the mark. If that leaves more than one, or none, the table does not settle it: write `RECORD_DOES_NOT_SAY`.
- Write `RIGHT` only when the governing mark gives the credited person.
- In every other case write `RECORD_DOES_NOT_SAY`: there is no mark; a suspension, resumption or "left the Chair" line between the mark and the row voids it; the marks before and after name different people; or a mark contradicts the credit or the label. A conflict is never right on the table alone.

### Classes for word differences

You do not judge whether the words of a paragraph match the record. A script does that, and a person reads every paragraph it flags.

If a packet shows a Word differences part, give one class for each numbered difference: LISTED_CHANGE, SUBSTANTIVE or COSMETIC. Write the classes in `difference_classes`, in the order the differences are numbered, one class for each number. If a packet shows no Word differences part, write an empty list. A class is a hint for the person who reads the row. It clears nothing and flags nothing.

For each numbered difference, compare the snapshot text with the matched source, word by word. The printed label and its colon are not part of either text; you judged them under the speaker verdict. A question number printed before the label stays in the compared text.

`LISTED_CHANGE`: the difference is one of the listed changes below.

`SUBSTANTIVE`: a word, number or name lost, added or changed; words glued together, or one word split in two; a paragraph cut or merged where no listed change allows it; a passage duplicated or reordered.

`COSMETIC`: stray markup or stray spacing and nothing worse. Stray markup is a doubled marker (`__` or `**`), an unmatched `_` or `*`, a marker where the source has no emphasis, a backslash, `](` or `&amp;`. Stray spacing is a space before a comma or a full stop. A matched pair of single underscores around text the source prints in italics is the markdown form of that italics and is not a fault. The one exception is a vernacular pointer: underscores left around it are cosmetic even as a matched pair (Royce, 18 October 2026). The script erases `__` and `**` before it compares, so it never shows one as a difference, and Royce may still mark one he sees in a flagged row.

A footnote number written [1] where the source prints a raised 1 is `LISTED_CHANGE`. A raised number run into its word with no brackets (2481 for 248 and a raised 1) is `SUBSTANTIVE`.

Two or more source paragraphs stored as one row are `LISTED_CHANGE` when a Column or Page marker, a line wrap inside preformatted text, an adjournment or suspension line split over source blocks, or a bracketed note cut by a marker sits between them, or when the report is a single-speaker report whose whole body is one row. Any other join is `SUBSTANTIVE`.

If the live check note says today's SPRS text differs from the stored copy, the snapshot may have been right when it was stored. That changes nothing for you. Give each class against the source shown, which comes from the stored copy. Every row of such a report goes to Royce whatever you write.

### Listed changes

A difference that is one of these has the class `LISTED_CHANGE`. The names on the left are for your reading: write the class, not the name.

- `nbsp_space`: a non-breaking space, or an emphasis tag holding only one, is an ordinary space.
- `character_reference`: an en dash, curly quote or accented letter is kept as printed. In some older reports the row keeps the plain form instead ("-" for an en dash, "'" for a curly quote); that is also listed.
- `lost_closing_quote`: the broken pair "�?" after a letter, digit or punctuation mark is a closing curly quote.
- `mojibake_repair`: a run of broken characters is re-read as UTF-8, so "faÃ§ade" is "façade".
- `lost_character_restored`: a lost character is restored where one answer fits, so "entrep�t" is "entrepôt" and "�" before a digit is "£".
- `byte_order_mark`: a byte-order mark is removed.
- `newer_system_cleanup`: an empty emphasis tag becomes a space, a `(proc text)` marker is removed, an inline image is removed.
- `column_page_marker`: a Column or Page marker paragraph is absent.
- `joined_across_break`: one row for a paragraph cut by a marker, wrapped preformatted prose, an adjournment or suspension line split over blocks, or a bracketed note cut by a marker.
- `single_speaker_collapse`: header fields, table rules, heading markers and the leading title are absent, lines are joined by a space, and paragraph breaks are lost.
- `html2text_escape`: a backslash escape is undone.
- `bare_ampersand`: a bare "&" is kept as "&", as in "R&D".
- `link_url_dropped`: link text is kept and the web address is gone; the space before a link inside emphasis has moved inside the link.
- `bold_merge`: consecutive bold lines, or a bold line wrapped over a break, are merged with a space.
- `no_row_line`: a heading, bare time stamp, section title, chair note such as "[Mr Speaker in the Chair]", image, table rule or question number is absent from the row.
- `doubled_paragraph`: the first copy of a paragraph that the source prints twice around a stray tag is absent.
- `footnote_marker`: a raised footnote number is written [N].
- `chamber_event_cut`: a bracketed direction is taken out of the paragraph and set in the next row, and one space joins the text on both sides.
- `language_note`: "(In Mandarin):" or a like note, and the close mark it leaves, is removed from the label or the start of the text.
- `nul_replacement`: the replacement character stands where the source held a null byte.

A difference that is not on this list is `SUBSTANTIVE` or `COSMETIC`. Two entries on it record a state of the data, not an approval: a lower-case appendix caption credited to a member is still wrong, and stray emphasis markers are still `COSMETIC`.

### When the match is not exact

If the match status is `not found`, no run of source paragraphs was found. Judge the speaker from the context, as always. The packet shows no Word differences part, so you give no class.

If the match status is `inexact`, the matched source is the closest run. Read the whole run when you judge the speaker. If the packet shows a Word differences part, give a class to each numbered difference.

### The verdict line

Write `verdicts.jsonl` in `BATCH_DIR` with exactly one line per packet and no blank lines. Each line is one JSON object with exactly these five keys.

A packet that shows no Word differences part:

`{"packet_id": "3f9a1c07b2de", "speaker_verdict": "WRONG", "speaker_tier": "A", "note": "The label is Mr Lim, but the paragraph is credited to Mr Tan.", "difference_classes": []}`

A packet that shows two numbered word differences:

`{"packet_id": "8c21d4e0a95f", "speaker_verdict": "RIGHT", "speaker_tier": null, "note": "", "difference_classes": ["LISTED_CHANGE", "COSMETIC"]}`

The values of `speaker_verdict`, `speaker_tier` and the classes are written exactly as below, in upper case.

- `packet_id`: copied exactly from the packet's heading.
- `speaker_verdict`: `RIGHT`, `WRONG` or `RECORD_DOES_NOT_SAY`.
- `speaker_tier`: "A" or "C" with `WRONG`, otherwise null.
- `note`: one or two sentences, 40 words at most, quoting the label and the mark you relied on. It may be an empty string when the verdict is `RIGHT`.
- `difference_classes`: a list of `LISTED_CHANGE`, `SUBSTANTIVE` or `COSMETIC`, one for each numbered difference in the packet's Word differences part, in number order. It is `[]` when the packet shows no such part.

A line with a missing key, an extra key, a word outside these lists, a tier that does not fit its verdict, or a number of classes that differs from the number of numbered differences makes the whole batch invalid, and another reader runs it again.

### Before you finish

- Every packet in `packets.md` has exactly one line in `verdicts.jsonl`, and no packet has two.
- Every `packet_id` is copied exactly from `packets.md`.
- A packet that shows a Word differences part has one class for each numbered difference. Every other packet has `[]`.
- Every line is valid JSON with the five keys, and there are no blank lines.

### Your reply

Reply in 100 words or fewer: the number of packets, the count of each `speaker_verdict` value, and anything you could not judge. Do not paste verdicts. They are in the file.

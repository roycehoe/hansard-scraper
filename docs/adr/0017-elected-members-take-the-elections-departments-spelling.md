# 0017. Elected members take the Elections Department's spelling

Status: accepted, 6 November 2026. Royce set the rule after the review of all 573 person names. It replaces [ADR 0016](0016-person-name-is-the-correct-name.md).

Context. `person.canonical_name` is the name the site shows and the name readers search for. It came from Parliament's member list, so a slip there became the person's name. That list prints Koo Yong, Lai Tai Chai and Chew Chin Harn, where Hansard prints Young, Tha and Han in those members' years. ADR 0016 said a person takes the correct name, but it named no test for correct, and it left person 513 on a spelling the department never printed.

Decision. An elected member's name takes the Elections Department's spelling.

- It changes spelling only. Bin stays where the site has it, and no name becomes longer or shorter to match the department's form. Copying the table word for word would rename about 115 people, and this rule does not.
- The table comes first: "Parliamentary General Election Results by Candidate", `d_581a30bee57fa7d8383d6bc94739ad00` on data.gov.sg, 1,609 rows, general elections only. The department's own pages fill in where the table has no row, as its 1967 by-election page does for Chew Chin Han.
- When the table disagrees with itself, the spelling printed in the most elections wins, and a tie goes to the latest. This renames nobody today. It keeps Jek Yeun Thong, Rahmat Bin Kenap and Yaacob Bin Mohamed.
- People who never stood, such as Nominated Members and colonial officials, have no such entry. Their names still come from Parliament's list and the hand-kept files in `data/`.
- Low Por Tuck keeps that name. The department printed Lau Peter in 1959, which is a different form of name and not a spelling of this one.

Eight people are renamed: Koo Young, Lai Tha Chai, Zulkifli Bin Mohammed, Ahmad Khalis bin Abdul Ghani, Abdul Nasser Bin Kamaruddin, Baharudin Bin Mohamed Ariff, Chew Chin Han and Lim Ching Siong. The first six and Chew have `name` entries in `data/person_decisions.json`. Lim has none, because the rule's name from `speaker.name` is already the department's spelling.

Other spellings are kept with their sources. `data/person_name_spellings.json` holds one entry per person and spelling, each with a note that links who prints it, and stage 9 loads it into `personnamespelling`. The site reads that table. Fourteen people have a note: the eight above, Jek Yeun Thong, Rahmat Bin Kenap, Yaacob Bin Mohamed, Seet Ai Mee, Mohamad Maidin and Low Por Tuck. Shorter and longer forms of a name get no note.

The record keeps what it prints, as [ADR 0013](0013-store-what-the-record-prints.md) requires. `speech.speaker`, `speech.transcript` and `speaker.name` do not change. Attendance is a different case: stage 7 stores `canonical_name or name`, the name it resolves from the `speaker` rows, so an attendance row does not always keep the print. ADR 0016 said it did, and that line was wrong. Keeping the print on attendance is a separate change with its own column and rewrite.

Lim Ching Siong. PJ Thum asked for Lim Chin Siong, and ADR 0016 recorded that spelling. Royce overrode that request: the department printed Lim Ching Siong in 1955, and the rule holds for him as for every other elected member. The spelling note lists Chin with NLB Infopedia and the National Archives, and says the two are transliterations of the same name. The site names no historian.

Consequences. Each rename changes a page address, and the old address redirects by person id. Stage 8 reads `speaker.name` and never `person`, so a rename moves no link. A report can show a printed label beside a credit link with another spelling: all of Baharudin's Hansard labels print two d. The People section of search, the people list and the person filter find every spelling in the note, while word search stays literal. A new member's name still comes from Parliament's list, and nothing compares it with the table until someone reruns the check.

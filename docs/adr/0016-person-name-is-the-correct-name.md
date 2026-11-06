# 0016. A person's name is the correct name

Status: accepted, 6 November 2026. Royce set the rule while reviewing person 513, stored as "Lim Ching Siong". It replaces the ruling of 17 October 2026 to take the Official Report's form for a person's name.

Context. `person.canonical_name` is the name the site shows and the name readers search for. It came from the printed or scraped spelling, so a misprint in the record became the person's name. The record prints "Lim Ching Siong" in all 91 speech labels and 105 attendance rows, and NLB Infopedia and the National Archives print "Lim Chin Siong".

Decision. In Royce's words:

> If the hansard misprints his name, we follow the misprint. However, his name in our people table, his canonical name which we render when people search MPs by name, would contain the correct name.

`speech`, `attendance` and `speaker.name` keep what the record prints, as [ADR 0013](0013-store-what-the-record-prints.md) requires. A `name` entry in `data/person_decisions.json` gives the person the correct name, and its `source` cites the outside sources and says where they disagree. The site needs no change: it lists `speaker.name` as a name variant, so people search still finds the printed form.

Consequences. A correction changes the page address, and the old address redirects by person id. Stage 8 reads `speaker.name` and never `person`, so a correction moves no link. The spellings of a record and of a person can now differ on one page, and a word search of the text for the correct name does not find a row that prints the misprint.

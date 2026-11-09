# 0018. Printed offices and ministry groups

Status: accepted, 9 November 2026. The number is a placeholder: another feature in the same build may take it, and the master renumbers this record when it lands.

Context. Hansard prints the office a Member holds in three places: the attendance entry, the label of a speaker in a question report, and the words of a question ("asked the Minister for Health"). The record prints no date on which a Member took or left an office. Two questions follow: when a Member held a title, and which titles belong to a ministry. The titles are printed in different spellings and forms, and the record uses different ministry names over time.

Decision.

1. Dates are first and last prints. A printed office range holds the first and last sittings of an unbroken run in which the Member's attendance entry printed one title. The page for the dates says they are not appointment or resignation dates.
2. Ministries are groups of printed titles. A closed list of ministry names holds the names. A rule, and a hand-kept list for the titles the rule cannot read, puts each exact printed title under one or more of those names. A row claims no ministry of that name existed.

Why. The record prints a title at a sitting. It does not print when the title began. A range built from prints states only what the record shows, and a reader can follow it back to the printed line. A group of exact titles lets a ministry page list what the record prints without deciding that two ministries were the same.

Consequences.

- A range ends or starts a new one when the title changes, when no office is printed, or when the Member is not listed.
- A late sitting writes no range for its month. A supervised run rebuilds the ranges.
- A title with an unresolved clause gets no ministry row until the hand-kept list names it.
- A renamed ministry stays as two rows. A see-also link needs an official source.

Alternatives.

- Merge titles under one key to find a Member's office. A merged key would hide that the record prints different words, and it would join ministries that were renamed.
- Match ministry names with a free rule. A free rule would place titles by guess. The closed list makes each placement checkable.
- Infer the office a question was put to from the Member who answered. An answerer may hold two offices, or answer for another Member. The record names the office in the question, so the table stores that.
